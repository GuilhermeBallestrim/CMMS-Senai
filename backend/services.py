"""Serviços de notificação e auditoria no Supabase."""
from __future__ import annotations

from backend.database import db
from backend.models import TABLE_AUDIT_LOGS, TABLE_NOTIFICATIONS, TABLE_USERS


def notify_user(user_id: int, title: str, message: str, href: str, kind: str = "info") -> None:
    db.client.table(TABLE_NOTIFICATIONS).insert({
        "user_id": user_id,
        "title": title,
        "message": message,
        "href": href,
        "kind": kind,
    }).execute()


def notify_administrators(title: str, message: str, href: str, kind: str = "info") -> None:
    admins = db.client.table(TABLE_USERS).select("id").eq("role", "administrator").eq("is_active", True).execute()
    for admin in admins.data:
        notify_user(admin["id"], title, message, href, kind)


def log_audit(actor_id: int | None, action: str, entity_type: str, entity_id: int | None, details: str) -> None:
    """Registra uma entrada na trilha de auditoria (RF-13)."""
    try:
        db.client.table(TABLE_AUDIT_LOGS).insert({
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": (details or "")[:500],
        }).execute()
    except Exception:
        # A auditoria não deve derrubar a operação principal (§7.3).
        pass