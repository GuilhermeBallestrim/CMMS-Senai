"""History routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from backend.database import db
from web.common import OS, get_order_call_equipment, order_snippet, require_page

router = APIRouter()


@router.get("/historico")
async def history(request: Request, equipment_search: str | None = None):
    items = db.client.table(OS).select("*").eq("status", "Concluída").order("finished_at", desc=True).execute().data
    if equipment_search:
        term = equipment_search.strip().lower()
        filtered = []
        for o in items:
            call_eq = get_order_call_equipment(o)
            equip = call_eq[1] if call_eq else None
            if equip and (term in equip.get("name", "").lower() or term in equip.get("asset_tag", "").lower()):
                filtered.append(o)
        items = filtered
    items = [order_snippet(o) for o in items]
    return require_page(
        request,
        "historico/lista.html",
        roles=["administrator", "tecnico"],
        context={
            "completed_orders": items,
            "equipment_search": equipment_search or "",
        },
    )