"""Dashboard routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from backend.database import db
from web.common import (
    C, E, OS, S, U,
    get_call_with_equipment,
    get_unit_preferences,
    format_local_datetime,
    render_template,
    require_page,
    status_class,
)

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request):
    user = request.session.get("user")
    q = db.client.table(C).select("*").order("created_at", desc=True)
    calls = q.execute().data
    if user and user["role"] == "professor":
        calls = [c for c in calls if c["requester_id"] == user["id"]]
    open_count = sum(1 for c in calls if c["status"] not in ("Concluído", "Cancelado"))
    analysis_count = sum(1 for c in calls if c["status"] in ("Aberto", "Em análise"))
    completed_count = sum(1 for c in calls if c["status"] == "Concluído")

    prefs = get_unit_preferences()
    unit_tz = prefs.get("timezone_name", "America/Sao_Paulo")

    # Pre-load maps to avoid N+1 queries.
    equipment_ids = {c.get("equipment_id") for c in calls if c.get("equipment_id")}
    equipment_map = {}
    if equipment_ids:
        rows = db.client.table(E).select("*").in_("id", list(equipment_ids)).execute().data
        equipment_map = {e["id"]: e for e in rows}
    sector_ids = {e.get("sector_id") for e in equipment_map.values() if e.get("sector_id")}
    sector_map = {}
    if sector_ids:
        rows = db.client.table(S).select("*").in_("id", list(sector_ids)).execute().data
        sector_map = {s["id"]: s for s in rows}
    call_ids = [c["id"] for c in calls]
    orders_by_call = {}
    if call_ids:
        rows = db.client.table(OS).select("*").in_("call_id", call_ids).execute().data
        for o in rows:
            orders_by_call.setdefault(o.get("call_id"), o)
    responsible_ids = set()
    for o in orders_by_call.values():
        if o.get("responsible_id"):
            responsible_ids.add(o["responsible_id"])
    for e in equipment_map.values():
        if e.get("responsible_id"):
            responsible_ids.add(e["responsible_id"])
    user_map = {}
    if responsible_ids:
        rows = db.client.table(U).select("*").in_("id", list(responsible_ids)).execute().data
        user_map = {u["id"]: u for u in rows}

    open_calls_detail = []
    for c in calls:
        if c["status"] in ("Concluído", "Cancelado"):
            continue
        e = equipment_map.get(c.get("equipment_id"))
        if not e:
            continue
        sec_name = "?"
        if e.get("sector_id"):
            sec = sector_map.get(e["sector_id"])
            sec_name = sec["name"] if sec else "?"
        trabalho = c.get("problem_type") or c.get("description", "")[:60]
        tipo = "Preventiva" if c.get("problem_type") else "Corretiva"
        prioridade = c.get("priority", "Média")
        status = c.get("status", "Aberto")
        resp_name = "Não definido"
        wo = orders_by_call.get(c["id"])
        if wo and wo.get("responsible_id"):
            u = user_map.get(wo["responsible_id"])
            if u:
                resp_name = u["name"]
        elif e.get("responsible_id"):
            u = user_map.get(e["responsible_id"])
            if u:
                resp_name = u["name"]
        open_calls_detail.append({
            "equipment": e["name"],
            "sector": sec_name,
            "trabalho": trabalho,
            "tipo": tipo,
            "prioridade": prioridade,
            "status": status,
            "solicitado_em": format_local_datetime(c.get("created_at"), unit_tz, "%d/%m/%Y") if c.get("created_at") else "?",
            "responsavel": resp_name,
            "_call_id": c["id"],
            "_call_number": c.get("number", ""),
        })

    return require_page(
        request,
        "dashboard.html",
        context={
            "open_count": open_count,
            "analysis_count": analysis_count,
            "completed_count": completed_count,
            "total_calls": len(calls),
            "status_class": status_class,
            "open_calls_detail": open_calls_detail,
        },
    )