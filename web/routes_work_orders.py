"""Work order routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from backend.database import db
from backend.services import (
    conclude_work_order,
    update_work_order_diagnostic,
    update_work_order_status,
)
from web.common import (
    C, E, OS, U,
    get_order_call_equipment,
    order_snippet,
    render_template,
    require_page,
    validate_csrf,
)

router = APIRouter()


@router.get("/ordens-servico")
async def ordens_servico(request: Request, page_num: int = 1):
    PAGE_SIZE = 20
    page_num = max(page_num, 1)
    items = db.client.table(OS).select("*").order("id", desc=True).execute().data
    items = [order_snippet(o) for o in items]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("Aguardando início", "Em execução", "Concluída")}
    total = len(items)
    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page_num = min(page_num, total_pages)
    start = (page_num - 1) * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    return require_page(
        request,
        "ordens_servico/lista.html",
        roles=["administrator", "tecnico"],
        context={
            "work_orders": page_items,
            "order_counts": counts,
            "page": page_num,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page_num > 1,
            "has_next": page_num < total_pages,
        },
    )


@router.get("/ordens-servico/detalhe")
async def work_order_detail(request: Request, id: int | None = None):
    resp = db.client.table(OS).select("*").eq("id", id).execute() if id else None
    order = resp.data[0] if resp and resp.data else None
    if not order:
        return RedirectResponse("/ordens-servico?notice=Ordem%20de%20servi%C3%A7o%20n%C3%A3o%20encontrada.", status_code=303)
    order = order_snippet(order)
    return require_page(
        request,
        "ordens_servico/detalhe.html",
        roles=["administrator", "tecnico"],
        context={"order": order},
    )


@router.post("/ordens-servico/{order_id}")
async def save_work_order(
    request: Request,
    order_id: int,
    status: str = Form(...),
    solution: str = Form(""),
    notes: str = Form(""),
    defect: str = Form(""),
    cause: str = Form(""),
    parts: str = Form(""),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] not in ("administrator", "tecnico"):
        raise HTTPException(403, "Apenas administradores e técnicos podem atualizar ordens de serviço.")
    if status not in {"Em execução", "Aguardando peça", "Concluída"}:
        raise HTTPException(422, "Status inválido.")

    if status == "Concluída":
        # Delegates to centralized service (RPC with sequential fallback).
        conclude_work_order(order_id, solution or "", user["id"])
        return RedirectResponse(f"/ordens-servico/detalhe?id={order_id}&notice=Ordem%20atualizada.", status_code=303)

    # Atualiza status (Em execução / Aguardando peça) via serviço centralizado.
    update_work_order_status(order_id, status, user["id"], user["role"])

    # Atualiza campos de diagnóstico via serviço centralizado (só se houver algo).
    diag_payload = {
        "solution": solution.strip() or None,
        "notes": notes.strip() or None,
        "defect": defect.strip() or None,
        "cause": cause.strip() or None,
        "parts": parts.strip() or None,
    }
    diag_payload = {k: v for k, v in diag_payload.items() if v is not None}
    if diag_payload:
        update_work_order_diagnostic(order_id, diag_payload, user["id"], user["role"])
    return RedirectResponse(f"/ordens-servico/detalhe?id={order_id}&notice=Ordem%20atualizada.", status_code=303)