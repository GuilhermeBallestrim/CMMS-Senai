"""Purchase request routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend.database import db
from backend.services import log_audit, make_number, notify_administrators, notify_user
from web.common import SC, U, purchase_snippet, render_template, require_page, status_class, validate_csrf

router = APIRouter()


@router.get("/solicitacoes")
async def solicitacoes(request: Request, page_num: int = 1):
    PAGE_SIZE = 20
    page_num = max(page_num, 1)
    items = db.client.table(SC).select("*").order("created_at", desc=True).execute().data
    user = request.session.get("user")
    if user and user["role"] == "professor":
        items = [r for r in items if r["requester_id"] == user["id"]]
    items = [purchase_snippet(r) for r in items]
    total = len(items)
    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page_num = min(page_num, total_pages)
    start = (page_num - 1) * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    return require_page(
        request,
        "solicitacoes/lista.html",
        context={
            "purchase_requests": page_items,
            "status_class": status_class,
            "page": page_num,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page_num > 1,
            "has_next": page_num < total_pages,
        },
    )


@router.get("/solicitacoes/nova")
async def nova_solicitacao(request: Request):
    return require_page(request, "solicitacoes/nova.html")


@router.post("/solicitacoes")
async def create_purchase_request(
    request: Request,
    item_type: str = Form(...),
    item: str = Form(...),
    quantity: int = Form(...),
    justification: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    if item_type not in {"Novas máquinas", "Ferramentas", "Peças e componentes"} or quantity < 1 or not 10 <= len(justification.strip()) <= 5000 or not 2 <= len(item.strip()) <= 180:
        return RedirectResponse("/solicitacoes/nova?notice=Confira%20os%20dados%20da%20solicita%C3%A7%C3%A3o.", status_code=303)
    db.client.table(SC).insert({
        "number": make_number("SC"),
        "item_type": item_type, "item": item.strip(), "quantity": quantity,
        "justification": justification.strip(), "requester_id": user["id"],
    }).execute()
    notify_administrators("Nova solicitação de compra", f"{item.strip()} ({quantity}).", "/solicitacoes", "info")
    log_audit(user["id"], "created", "purchase_request", None, f"Criou solicitação de compra: {item.strip()}.")
    return RedirectResponse("/solicitacoes?notice=Solicitação%20registrada.", status_code=303)


@router.post("/solicitacoes/{request_id}/decidir")
async def decide_purchase_request(request: Request, request_id: int, decision: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem analisar solicitações.")
    if decision not in {"Aprovada", "Recusada"}:
        raise HTTPException(422, "Decisão inválida.")
    resp = db.client.table(SC).select("*").eq("id", request_id).execute()
    purchase = resp.data[0] if resp.data else None
    if not purchase:
        raise HTTPException(404, "Solicitação não encontrada.")
    if purchase["status"] != "Em análise":
        raise HTTPException(409, "Esta solicitação já foi analisada.")
    db.client.table(SC).update({"status": decision, "reviewed_by_id": user["id"]}).eq("id", request_id).execute()
    notify_user(purchase["requester_id"], "Solicitação analisada", f"{purchase['number']}: {decision.lower()}.", "/solicitacoes")
    return RedirectResponse("/solicitacoes?notice=Decisão%20registrada.", status_code=303)


@router.get("/solicitacoes/detalhe")
async def purchase_detail(request: Request, id: int | None = None):
    resp = db.client.table(SC).select("*").eq("id", id).execute() if id else None
    purchase = resp.data[0] if resp and resp.data else None
    user = request.session.get("user")
    if not purchase or (user and user["role"] == "professor" and purchase["requester_id"] != user["id"]):
        return RedirectResponse("/solicitacoes?notice=Solicitação%20não%20encontrada.", status_code=303)
    requester = db.client.table(U).select("*").eq("id", purchase["requester_id"]).execute().data
    purchase["_requester"] = requester[0] if requester else None
    purchase["requester"] = purchase["_requester"] or {}
    if purchase.get("reviewed_by_id"):
        rb = db.client.table(U).select("*").eq("id", purchase["reviewed_by_id"]).execute().data
        purchase["reviewed_by"] = rb[0] if rb else None
    else:
        purchase["reviewed_by"] = None
    return require_page(request, "solicitacoes/detalhe.html", context={"purchase": purchase, "status_class": status_class})