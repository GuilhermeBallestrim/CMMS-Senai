"""Shared helpers for web routes.

Code identifiers are in English. User-facing messages (flash notices) remain
in Portuguese. URL paths are kept in Portuguese.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
import secrets
from hmac import compare_digest

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.database import db
from backend.models import (
    TABLE_EQUIPMENT, TABLE_EQUIPMENT_MAINTENANCE_TYPES, TABLE_MAINTENANCE_CALLS,
    TABLE_NOTIFICATIONS, TABLE_PURCHASE_REQUESTS, TABLE_SECTORS,
    TABLE_UNIT_SETTINGS, TABLE_USERS, TABLE_WORK_ORDERS,
)
from backend.rate_limit import check_rate_limit
from backend.security import hash_password, verify_password
from backend.services import log_audit, notify_administrators, notify_user
from backend.storage import file_path, save_image, save_pdf

# ---------------------------------------------------------------------------
# Table aliases (short names used across web routes)
# ---------------------------------------------------------------------------
C = TABLE_MAINTENANCE_CALLS
E = TABLE_EQUIPMENT
EMT = TABLE_EQUIPMENT_MAINTENANCE_TYPES
OS = TABLE_WORK_ORDERS
N = TABLE_NOTIFICATIONS
U = TABLE_USERS
S = TABLE_SECTORS
SC = TABLE_PURCHASE_REQUESTS
US = TABLE_UNIT_SETTINGS

# ---------------------------------------------------------------------------
# Timezone offsets (fallback when ZoneInfo data is unavailable)
# ---------------------------------------------------------------------------
TZ_OFFSETS = {
    "America/Sao_Paulo": -3, "America/Manaus": -4, "America/Belem": -3,
    "America/Fortaleza": -3, "America/Recife": -3, "America/Rio_Branco": -5, "UTC": 0,
}

templates: Jinja2Templates | None = None


def init_templates(tpl: Jinja2Templates) -> None:
    """Called by main.py after creating the Jinja2Templates instance."""
    global templates
    templates = tpl
    templates.env.filters["fmt"] = fmt_date
    templates.env.globals["local_datetime"] = format_local_datetime
    templates.env.globals["status_class"] = status_class


# ---------------------------------------------------------------------------
# Date / formatting helpers
# ---------------------------------------------------------------------------
def fmt_date(value, fmt="%d/%m/%Y"):
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    try:
        return value.strftime(fmt)
    except Exception:
        return str(value)


def format_local_datetime(value: datetime | None, zone_name: str, pattern: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return "—"
    try:
        raw = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "—"
    utc_value = raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw.astimezone(timezone.utc)
    local_zone = timezone(timedelta(hours=TZ_OFFSETS.get(zone_name, -3)))
    return utc_value.astimezone(local_zone).strftime(pattern)


def status_class(value: str) -> str:
    return {
        "Aberto": "status--gray", "Em análise": "status--blue", "Em manutenção": "status--orange",
        "Aguardando peça": "status--yellow", "Concluído": "status--green", "Concluída": "status--green",
        "Cancelado": "status--red", "Aguardando início": "status--blue", "Em execução": "status--orange",
        "Aprovada": "status--green", "Recusada": "status--red",
    }.get(value, "status--gray")


# ---------------------------------------------------------------------------
# CSRF / session helpers
# ---------------------------------------------------------------------------
def validate_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="Sessão expirada. Atualize a página e tente novamente.")


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def render_template(request: Request, template: str, *, notice: str | None = None, status_code: int = 200, context: dict | None = None):
    if templates is None:
        raise RuntimeError("Templates not initialized. Call web.common.init_templates() from main.py.")
    csrf_token = request.session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "notice": notice or request.query_params.get("notice", ""),
            "csrf_token": csrf_token,
            "current_user": request.session.get("user"),
            "notification_count": get_unread_notifications_count(request.session.get("user_id")),
            "unit_settings": get_unit_preferences(),
            **(context or {}),
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# Page access control (login + role)
# ---------------------------------------------------------------------------
def require_page(request: Request, template: str, *, role: str | None = None, roles: list | None = None, context: dict | None = None):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    if not resp.data or not resp.data[0].get("is_active"):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    user = {
        "id": resp.data[0]["id"],
        "name": resp.data[0]["name"],
        "email": resp.data[0]["email"],
        "role": resp.data[0]["role"],
    }
    request.session["user"] = user
    allowed = roles if roles is not None else ([role] if role else None)
    if allowed and user["role"] not in allowed:
        return RedirectResponse("/dashboard?notice=Acesso%20restrito.", status_code=303)
    return render_template(request, template, context=context)


# ---------------------------------------------------------------------------
# Data helpers (pre-loaded maps to avoid N+1)
# ---------------------------------------------------------------------------
def get_unit_preferences() -> dict:
    resp = db.client.table(US).select("*").eq("id", 1).execute()
    if resp.data:
        return resp.data[0]
    return {"unit_name": "SENAI — São Paulo", "timezone_name": "America/Sao_Paulo"}


def get_unread_notifications_count(user_id: int | None) -> int:
    if not user_id:
        return 0
    resp = db.client.table(N).select("id").eq("user_id", user_id).eq("is_read", False).execute()
    return len(resp.data)


def get_call_with_equipment(call_id: int | None):
    if not call_id:
        return None, None
    cr = db.client.table(C).select("*").eq("id", call_id).execute()
    call = cr.data[0] if cr.data else None
    equip = None
    if call and call.get("equipment_id"):
        er = db.client.table(E).select("*").eq("id", call["equipment_id"]).execute()
        equip = er.data[0] if er.data else None
    return call, equip


def get_order_call_equipment(order):
    if not order or not order.get("call_id"):
        return None, None
    return get_call_with_equipment(order["call_id"])


def order_snippet(o):
    call, eq = get_order_call_equipment(o)
    resp = db.client.table(U).select("*").eq("id", o.get("responsible_id")).execute().data if o.get("responsible_id") else []
    responsible = resp[0] if resp else None
    if call is not None:
        call = {**call, "equipment": eq, "_equipment": eq}
    return {**o, "call": call, "equipment": eq, "responsible": responsible,
            "_equipment_name": eq["name"] if eq else "?", "_equipment_id": eq["id"] if eq else None,
            "_call_number": call["number"] if call else "?", "_call_id": call["id"] if call else None,
            "_call_description": call["description"] if call else "",
            "_call_priority": call["priority"] if call else "",
            "_call_created_at": call["created_at"] if call else None}


def purchase_snippet(r):
    requester = db.client.table(U).select("*").eq("id", r["requester_id"]).execute().data
    requester_obj = requester[0] if requester else None
    return {**r, "_requester": requester_obj, "requester": requester_obj or {}}