"""Maintenance call routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from backend.database import db
from backend.services import (
    approve_call as service_approve_call,
    cancel_call as service_cancel_call,
    log_audit,
    make_number,
    notify_administrators,
)
from backend.storage import save_image
from web.common import (
    C, E, OS, S, U,
    format_local_datetime,
    get_unit_preferences,
    render_template,
    require_page,
    status_class,
    validate_csrf,
)

router = APIRouter()


@router.get("/chamados")
async def chamados(request: Request, page_num: int = 1):
    PAGE_SIZE = 20
    page_num = max(page_num, 1)
    items = db.client.table(C).select("*").order("created_at", desc=True).execute().data
    user = request.session.get("user")
    if user and user["role"] == "professor":
        items = [c for c in items if c["requester_id"] == user["id"]]

    # Pre-load maps to avoid N+1 queries.
    equip_ids = {c.get("equipment_id") for c in items if c.get("equipment_id")}
    requester_ids = {c.get("requester_id") for c in items if c.get("requester_id")}
    equip_map = {}
    if equip_ids:
        rows = db.client.table(E).select("*").in_("id", list(equip_ids)).execute().data
        equip_map = {e["id"]: e for e in rows}
    requester_map = {}
    if requester_ids:
        rows = db.client.table(U).select("*").in_("id", list(requester_ids)).execute().data
        requester_map = {u["id"]: u for u in rows}

    def _call_snippet(c):
        equip = equip_map.get(c.get("equipment_id"))
        requester_obj = requester_map.get(c.get("requester_id"))
        return {**c, "_equipment_name": equip["name"] if equip else "?",
                "_requester": requester_obj, "requester": requester_obj or {}}

    items = [_call_snippet(c) for c in items]
    counts = {s: 0 for s in ("Aberto", "Em análise", "Em manutenção", "Aguardando peça", "Concluído")}
    for call in items:
        if call["status"] in counts:
            counts[call["status"]] += 1
    total = len(items)
    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page_num = min(page_num, total_pages)
    start = (page_num - 1) * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    return require_page(
        request,
        "chamados/lista.html",
        context={
            "calls": page_items,
            "call_counts": counts,
            "status_class": status_class,
            "page": page_num,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page_num > 1,
            "has_next": page_num < total_pages,
        },
    )


@router.get("/chamados/novo")
async def novo_chamado(request: Request):
    equipment = db.client.table(E).select("*").order("name").execute().data
    types = db.client.table("equipment_maintenance_types").select("*").eq("is_active", True).execute().data or []
    equipment_maintenance = {eq["name"]: [] for eq in equipment}
    equip_by_id = {eq["id"]: eq["name"] for eq in equipment}
    for t in types:
        name = equip_by_id.get(t.get("equipment_id"))
        if name is not None:
            equipment_maintenance.setdefault(name, []).append(t.get("name"))
    return require_page(
        request,
        "chamados/novo.html",
        context={
            "equipment_items": equipment,
            "equipment_maintenance_types": equipment_maintenance,
        },
    )


@router.post("/chamados")
async def create_call(
    request: Request,
    equipment_id: int = Form(...),
    description: str = Form(...),
    priority: str = Form(...),
    problem_type: str = Form(""),
    problem_other: str = Form(""),
    noise_vibration: str = Form("false"),
    overheating: str = Form("false"),
    other_symptoms: str = Form(""),
    csrf_token: str = Form(...),
    photo: UploadFile | None = File(None),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    if priority not in {"Baixa", "Média", "Alta", "Crítica"} or not 10 <= len(description.strip()) <= 5000:
        return RedirectResponse("/chamados/novo?notice=Confira%20a%20descri%C3%A7%C3%A3o%20e%20a%20prioridade.", status_code=303)
    if not db.client.table(E).select("id").eq("id", equipment_id).execute().data:
        return RedirectResponse("/chamados/novo?notice=Equipamento%20n%C3%A3o%20encontrado.", status_code=303)
    photo_name, photo_mime = await save_image(photo, "calls")
    dados_chamado = {
        "number": make_number("CH"),
        "equipment_id": equipment_id,
        "requester_id": user["id"],
        "description": description.strip(),
        "priority": priority,
        "photo_name": photo_name,
        "photo_mime": photo_mime,
    }
    dados_diagnostico = {
        "problem_type": problem_type.strip() or None,
        "problem_other": problem_other.strip() or None,
        "noise_vibration": noise_vibration == "true",
        "overheating": overheating == "true",
        "other_symptoms": other_symptoms.strip() or None,
    }
    try:
        resp = db.client.table(C).insert({**dados_chamado, **dados_diagnostico}).execute()
    except Exception:
        resp = db.client.table(C).insert(dados_chamado).execute()
    call = resp.data[0]
    prefs = get_unit_preferences()
    if prefs.get("notify_admin_new_call"):
        kind = "warning" if priority in {"Alta", "Crítica"} else "info"
        notify_administrators("Novo chamado", f"{call['number']}: prioridade {priority}.", f"/chamados/detalhe?id={call['id']}", kind)
    log_audit(user["id"], "created", "maintenance_call", call["id"], f"Abriu o chamado {call['number']} pela web.")
    return RedirectResponse("/chamados?notice=Chamado%20registrado%20com%20sucesso.", status_code=303)


@router.get("/chamados/detalhe")
async def call_detail(request: Request, id: int | None = None):
    cr = db.client.table(C).select("*").eq("id", id).execute() if id else None
    call = cr.data[0] if cr and cr.data else None
    user = request.session.get("user")
    if not call or (user and user["role"] == "professor" and call["requester_id"] != user["id"]):
        return RedirectResponse("/chamados?notice=Chamado%20n%C3%A3o%20encontrado.", status_code=303)
    eq_resp = db.client.table(E).select("*").eq("id", call["equipment_id"]).execute()
    equipment = eq_resp.data[0] if eq_resp.data else None
    sector = None
    if equipment:
        sec_resp = db.client.table(S).select("*").eq("id", equipment["sector_id"]).execute()
        sector = sec_resp.data[0] if sec_resp.data else None
    requester_resp = db.client.table(U).select("*").eq("id", call["requester_id"]).execute()
    requester = requester_resp.data[0] if requester_resp.data else None
    wo_resp = db.client.table(OS).select("*").eq("call_id", call["id"]).execute()
    work_order = wo_resp.data[0] if wo_resp.data else None
    call["_equipment"] = equipment
    call["_sector"] = sector
    call["_requester"] = requester
    call["requester"] = requester or {}
    call["_work_order"] = work_order
    return require_page(
        request,
        "chamados/detalhe.html",
        context={"call": call, "status_class": status_class(call["status"])},
    )


@router.post("/chamados/{call_id}/aprovar")
async def approve_call(request: Request, call_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem aprovar chamados.")
    try:
        service_approve_call(call_id, user["id"])
    except HTTPException as exc:
        return RedirectResponse(f"/chamados/detalhe?id={call_id}&notice={exc.detail}", status_code=303)
    return RedirectResponse(f"/chamados/detalhe?id={call_id}&notice=Ordem%20de%20servi%C3%A7o%20gerada.", status_code=303)


@router.post("/chamados/{call_id}/cancelar")
async def cancel_call(request: Request, call_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    try:
        service_cancel_call(call_id, user["id"], user["role"])
    except HTTPException:
        raise
    return RedirectResponse("/chamados?notice=Chamado%20cancelado.", status_code=303)