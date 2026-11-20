"""Equipment routes (web interface)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from backend.database import db
from backend.services import log_audit
from backend.storage import file_path, save_image, save_pdf
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


@router.get("/equipamentos")
async def equipamentos(request: Request, page_num: int = 1, equipment_search: str | None = None):
    PAGE_SIZE = 20
    page_num = max(page_num, 1)
    items = db.client.table(E).select("*").order("name").execute().data
    if equipment_search:
        term = equipment_search.strip().lower()
        items = [e for e in items if term in e["name"].lower() or term in e.get("asset_tag", "").lower()]
    sector_ids = {e.get("sector_id") for e in items if e.get("sector_id")}
    responsible_ids = {e.get("responsible_id") for e in items if e.get("responsible_id")}
    sector_map = {}
    if sector_ids:
        rows = db.client.table(S).select("*").in_("id", list(sector_ids)).execute().data
        sector_map = {s["id"]: s for s in rows}
    user_map = {}
    if responsible_ids:
        rows = db.client.table(U).select("*").in_("id", list(responsible_ids)).execute().data
        user_map = {u["id"]: u for u in rows}
    for e in items:
        e["_sector"] = sector_map.get(e.get("sector_id"))
        e["_responsible"] = user_map.get(e.get("responsible_id"))
    total = len(items)
    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page_num = min(page_num, total_pages)
    start = (page_num - 1) * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    return require_page(
        request,
        "equipamentos/lista.html",
        context={
            "equipment_items": page_items,
            "page": page_num,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page_num > 1,
            "has_next": page_num < total_pages,
            "equipment_search": equipment_search or "",
        },
    )


@router.get("/equipamentos/novo")
async def novo_equipamento(request: Request):
    sectors = db.client.table(S).select("*").order("name").execute().data
    return require_page(request, "equipamentos/novo.html", role="administrator", context={"sectors": sectors})


@router.post("/equipamentos")
async def create_equipment(
    request: Request,
    name: str = Form(...),
    sector_id: int = Form(...),
    model_name: str = Form(""),
    serial_number: str = Form(""),
    acquired_at: str = Form(""),
    asset_tag: str = Form(...),
    state: str = Form("Disponível"),
    csrf_token: str = Form(...),
    photo: UploadFile | None = File(None),
    manual: UploadFile | None = File(None),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar equipamentos.")
    if state not in {"Disponível", "Em manutenção", "Indisponível"} or not 2 <= len(name.strip()) <= 120 or not 1 <= len(asset_tag.strip()) <= 80:
        raise HTTPException(422, "Estado inválido.")
    try:
        acquired_date = date.fromisoformat(acquired_at).isoformat() if acquired_at else None
    except ValueError:
        raise HTTPException(422, "Data de aquisição inválida.") from None
    if not db.client.table(S).select("id").eq("id", sector_id).execute().data:
        raise HTTPException(422, "Setor não encontrado.")
    photo_name, photo_mime = await save_image(photo, "equipment")
    manual_name, manual_mime = await save_pdf(manual, "equipment")
    resp = db.client.table(E).insert({
        "name": name.strip(), "sector_id": sector_id, "model": model_name.strip() or None,
        "serial_number": serial_number.strip() or None, "acquired_at": acquired_date,
        "asset_tag": asset_tag.strip(), "state": state, "photo_name": photo_name,
        "photo_mime": photo_mime, "manual_name": manual_name, "manual_mime": manual_mime,
    }).execute()
    if resp.data:
        log_audit(user["id"], "created", "equipment", resp.data[0]["id"], f"Cadastrou o equipamento {asset_tag.strip()} pela web.")
    return RedirectResponse("/equipamentos?notice=Equipamento%20cadastrado.", status_code=303)


@router.get("/equipamentos/detalhe")
async def equipment_detail(request: Request, id: int | None = None):
    resp = db.client.table(E).select("*").eq("id", id).execute() if id else None
    equipment = resp.data[0] if resp and resp.data else None
    if not equipment:
        return RedirectResponse("/equipamentos?notice=Equipamento%20não%20encontrado.", status_code=303)
    sec = db.client.table(S).select("*").eq("id", equipment["sector_id"]).execute().data
    equipment["_sector"] = sec[0] if sec else None

    prefs = get_unit_preferences()
    unit_tz = prefs.get("timezone_name", "America/Sao_Paulo")

    calls = db.client.table(C).select("*").eq("equipment_id", id).order("created_at", desc=True).execute().data or []
    history = []
    for c in calls:
        wo = db.client.table(OS).select("*").eq("call_id", c["id"]).execute().data
        order = wo[0] if wo else None
        status_display = c["status"]
        if order and order.get("status") == "Concluída":
            status_display = "Concluído"
        elif order and order.get("status"):
            status_display = order["status"]
        req = db.client.table(U).select("*").eq("id", c["requester_id"]).execute().data
        requester_name = req[0]["name"] if req else "?"
        history.append({
            "call_id": c["id"],
            "call_number": c.get("number", ""),
            "description": c.get("description", "")[:80],
            "problem_type": c.get("problem_type") or "—",
            "status": status_display,
            "priority": c.get("priority", "—"),
            "created_at": format_local_datetime(c.get("created_at"), unit_tz, "%d/%m/%Y %H:%M") if c.get("created_at") else "?",
            "requester": requester_name,
            "solution": order.get("solution") if order else None,
            "finished_at": format_local_datetime(order.get("finished_at"), unit_tz, "%d/%m/%Y %H:%M") if order and order.get("finished_at") else None,
        })
    equipment["_history"] = history

    completed_orders = db.client.table(OS).select("*").eq("status", "Concluída").execute().data or []
    mttr_hours = []
    last_finished = None
    for o in completed_orders:
        call = db.client.table(C).select("*").eq("id", o["call_id"]).execute().data
        if not call or call[0].get("equipment_id") != id:
            continue
        started = o.get("started_at")
        finished = o.get("finished_at")
        if not started or not finished:
            continue
        try:
            started_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            finished_dt = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            mttr_hours.append((finished_dt - started_dt).total_seconds() / 3600)
            if last_finished is None or finished_dt > last_finished:
                last_finished = finished_dt
        except Exception:
            pass

    equipment["_mttr_avg"] = round(sum(mttr_hours) / len(mttr_hours), 1) if mttr_hours else 0
    equipment["_mttr_count"] = len(mttr_hours)
    equipment["_last_finished"] = format_local_datetime(last_finished, unit_tz, "%d/%m/%Y %H:%M") if last_finished else "—"

    concluded_calls = []
    for c in calls:
        if c.get("status") == "Concluído" and c.get("created_at"):
            try:
                concluded_calls.append(datetime.fromisoformat(str(c["created_at"]).replace("Z", "+00:00")))
            except Exception:
                pass
    concluded_calls.sort()
    mtbf_intervals = []
    for i in range(1, len(concluded_calls)):
        mtbf_intervals.append((concluded_calls[i] - concluded_calls[i - 1]).total_seconds() / 3600)
    equipment["_mtbf_avg"] = round(sum(mtbf_intervals) / len(mtbf_intervals), 1) if mtbf_intervals else 0

    return require_page(request, "equipamentos/detalhe.html", context={"equipment": equipment})


@router.get("/equipamentos/{equipment_id}/editar")
async def edit_equipment_page(request: Request, equipment_id: int):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    equipment = resp.data[0] if resp.data else None
    if not equipment:
        return RedirectResponse("/equipamentos?notice=Equipamento%20não%20encontrado.", status_code=303)
    sectors = db.client.table(S).select("*").order("name").execute().data
    return require_page(request, "equipamentos/editar.html", role="administrator", context={"equipment": equipment, "sectors": sectors})


@router.post("/equipamentos/{equipment_id}/editar")
async def edit_equipment(
    request: Request,
    equipment_id: int,
    name: str = Form(...),
    sector_id: int = Form(...),
    model_name: str = Form(""),
    serial_number: str = Form(""),
    acquired_at: str = Form(""),
    asset_tag: str = Form(...),
    state: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem editar equipamentos.")
    if state not in {"Disponível", "Em manutenção", "Indisponível"} or not 2 <= len(name.strip()) <= 120 or not 1 <= len(asset_tag.strip()) <= 80:
        raise HTTPException(422, "Dados do equipamento inválidos.")
    try:
        acquired_date = date.fromisoformat(acquired_at).isoformat() if acquired_at else None
    except ValueError:
        raise HTTPException(422, "Data de aquisição inválida.") from None
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    equipment = resp.data[0] if resp.data else None
    if not equipment or not db.client.table(S).select("id").eq("id", sector_id).execute().data:
        raise HTTPException(404, "Equipamento ou setor não encontrado.")
    if state != equipment.get("state"):
        calls = db.client.table(C).select("id").eq("equipment_id", equipment_id).execute().data
        call_ids = [c["id"] for c in calls]
        active_order = False
        if call_ids:
            orders = db.client.table(OS).select("id,status").in_("call_id", call_ids).execute().data
            active_order = any(o.get("status") != "Concluída" for o in orders)
        if active_order:
            return RedirectResponse(
                f"/equipamentos/{equipment_id}/editar?notice=O%20estado%20é%20controlado%20pela%20ordem%20de%20servi%C3%A7o%20ativa.",
                status_code=303,
            )
    update = {
        "name": name.strip(), "sector_id": sector_id, "model": model_name.strip() or None,
        "serial_number": serial_number.strip() or None, "acquired_at": acquired_date,
        "asset_tag": asset_tag.strip(), "state": state,
    }
    try:
        db.client.table(E).update(update).eq("id", equipment_id).execute()
    except Exception:
        return RedirectResponse(f"/equipamentos/{equipment_id}/editar?notice=Patrim%C3%B4nio%20j%C3%A1%20cadastrado.", status_code=303)
    log_audit(user["id"], "updated", "equipment", equipment_id, f"Atualizou o equipamento {asset_tag.strip()}.")
    return RedirectResponse(f"/equipamentos/detalhe?id={equipment_id}&notice=Equipamento%20atualizado.", status_code=303)


@router.get("/files/calls/{call_id}/photo")
def view_call_photo(call_id: int, request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=401, detail="Autenticação necessária.")
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    call = resp.data[0] if resp.data else None
    user = request.session.get("user")
    if not call or not call.get("photo_name") or (user and user.get("role") == "professor" and call["requester_id"] != user["id"]):
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(file_path("calls", call["photo_name"]), media_type=call.get("photo_mime") or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/files/equipment/{equipment_id}/{kind}")
def view_equipment_file(equipment_id: int, kind: str, request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=401, detail="Autenticação necessária.")
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    equipment = resp.data[0] if resp.data else None
    user = request.session.get("user")
    if not equipment or kind not in {"photo", "manual"}:
        raise HTTPException(404, "Arquivo não encontrado.")
    filename = equipment.get("photo_name") if kind == "photo" else equipment.get("manual_name")
    mime = equipment.get("photo_mime") if kind == "photo" else equipment.get("manual_mime")
    if not filename:
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(file_path("equipment", filename), media_type=mime or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})