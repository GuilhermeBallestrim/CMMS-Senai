"""Serviços de notificação no Supabase."""
from __future__ import annotations

from backend.database import db
from backend.models import TABLE_NOTIFICATIONS, TABLE_USERS


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
