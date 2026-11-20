"""Notification routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend.database import db
from web.common import N, U, render_template, require_page, validate_csrf

router = APIRouter()


@router.get("/notificacoes")
async def notifications(request: Request, page_num: int = 1):
    PAGE_SIZE = 20
    page_num = max(page_num, 1)
    user = request.session.get("user")
    items = []
    total = 0
    if user:
        total_resp = db.client.table(N).select("id", count="exact").eq("user_id", user["id"]).execute()
        total = total_resp.count or 0
        start = (page_num - 1) * PAGE_SIZE
        items = (
            db.client.table(N)
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
        )
    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page_num = min(page_num, total_pages)
    return require_page(
        request,
        "notificacoes/lista.html",
        context={
            "notifications": items,
            "page": page_num,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page_num > 1,
            "has_next": page_num < total_pages,
        },
    )


@router.post("/notificacoes/ler-todas")
async def mark_all_read(request: Request, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    db.client.table(N).update({"is_read": True}).eq("user_id", user["id"]).eq("is_read", False).execute()
    return RedirectResponse("/notificacoes?notice=Notificações%20marcadas%20como%20lidas.", status_code=303)


@router.post("/notificacoes/{notification_id}/ler")
async def mark_one_read(request: Request, notification_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    resp = db.client.table(N).select("*").eq("id", notification_id).execute()
    item = resp.data[0] if resp.data else None
    if not item or item["user_id"] != user["id"]:
        raise HTTPException(404, "Notificação não encontrada.")
    db.client.table(N).update({"is_read": True}).eq("id", notification_id).execute()
    return RedirectResponse(item["href"], status_code=303)