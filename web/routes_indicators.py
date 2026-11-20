"""Indicators routes (web interface)."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from backend.database import db
from web.common import C, E, OS, format_local_datetime, get_unit_preferences, render_template, require_page

router = APIRouter()


@router.get("/indicadores")
async def indicators(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        return RedirectResponse("/dashboard?notice=Acesso%20restrito%20aos%20indicadores.", status_code=303)

    calls = db.client.table(C).select("*").execute().data or []
    open_calls = [c for c in calls if c.get("status") not in ("Concluído", "Cancelado")]
    equipment = db.client.table(E).select("*").execute().data or []
    equipment_map = {e["id"]: e for e in equipment}
    unavailable = [e for e in equipment if e.get("state") == "Indisponível"]
    orders = db.client.table(OS).select("*").execute().data or []
    completed = [o for o in orders if o.get("status") == "Concluída"]

    # MTTR: tempo médio de reparo (início -> conclusão da OS).
    repair_durations = []
    for o in orders:
        s, e = o.get("started_at"), o.get("finished_at")
        if s and e:
            try:
                repair_durations.append(
                    (datetime.fromisoformat(str(e).replace("Z", "+00:00"))
                     - datetime.fromisoformat(str(s).replace("Z", "+00:00")))
                    .total_seconds() / 3600
                )
            except Exception:
                pass
    mttr = round(sum(repair_durations) / len(repair_durations), 1) if repair_durations else None

    # MTBF: tempo médio entre falhas (por equipamento, média dos intervalos entre chamados).
    calls_by_equip = {}
    for c in calls:
        calls_by_equip.setdefault(c.get("equipment_id"), []).append(c)
    mtbf_per_equip = []
    for eq_id, eq_calls in calls_by_equip.items():
        if len(eq_calls) < 2:
            continue
        eq_calls.sort(key=lambda x: x.get("created_at") or "")
        intervals = []
        for i in range(1, len(eq_calls)):
            try:
                a = datetime.fromisoformat(str(eq_calls[i - 1].get("created_at")).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(eq_calls[i].get("created_at")).replace("Z", "+00:00"))
                intervals.append((b - a).total_seconds() / 3600)
            except Exception:
                pass
        if intervals:
            mtbf_per_equip.append(sum(intervals) / len(intervals))
    mtbf = round(sum(mtbf_per_equip) / len(mtbf_per_equip), 1) if mtbf_per_equip else None

    availability = None
    if mtbf is not None and mttr is not None and (mtbf + mttr) > 0:
        availability = round(mtbf / (mtbf + mttr) * 100, 1)

    lead_times = []
    order_by_call = {o.get("call_id"): o for o in orders}
    for c in calls:
        o = order_by_call.get(c["id"])
        if o and o.get("finished_at") and c.get("created_at"):
            try:
                a = datetime.fromisoformat(str(c["created_at"]).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(o["finished_at"]).replace("Z", "+00:00"))
                lead_times.append((b - a).total_seconds() / 3600)
            except Exception:
                pass
    avg_lead_time = round(sum(lead_times) / len(lead_times), 1) if lead_times else None

    completion_rate = round(len(completed) / len(orders) * 100, 1) if orders else None

    calls_per_equip = []
    for eq_id, eq_calls in calls_by_equip.items():
        eq = equipment_map.get(eq_id, {})
        calls_per_equip.append({
            "equipment_id": eq_id,
            "equipment_name": eq.get("name", "?"),
            "count": len(eq_calls),
        })
    calls_per_equip.sort(key=lambda x: x["count"], reverse=True)
    top_failing = calls_per_equip[:5]

    prefs = get_unit_preferences()
    unit_tz = prefs.get("timezone_name", "America/Sao_Paulo")

    return require_page(
        request,
        "indicadores/lista.html",
        role="administrator",
        context={
            "calls_total": len(calls),
            "backlog": len(open_calls),
            "equipment_total": len(equipment),
            "unavailable": len(unavailable),
            "mttr": mttr,
            "mtbf": mtbf,
            "availability": availability,
            "completion_rate": completion_rate,
            "avg_lead_time": avg_lead_time,
            "calls_per_equipment": calls_per_equip,
            "top_failing": top_failing,
            "insufficient_data": not bool(repair_durations) or not orders,
            "unit_settings": prefs,
        },
    )