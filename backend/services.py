"""Serviços de notificação no Supabase."""
from __future__ import annotations

<<<<<<< HEAD
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AuditLog, Notification, User
=======
from backend.database import db
from backend.models import TABLE_NOTIFICATIONS, TABLE_USERS
>>>>>>> 763faa02520857295d80a222e5a2a365debda955


def notify_user(user_id: int, title: str, message: str, href: str, kind: str = "info") -> None:
    db.client.table(TABLE_NOTIFICATIONS).insert({
        "user_id": user_id,
        "title": title,
        "message": message,
        "href": href,
        "kind": kind,
    }).execute()


<<<<<<< HEAD
def notify_administrators(db: Session, title: str, message: str, href: str, kind: str = "info") -> None:
    ids = db.scalars(select(User.id).where(User.role == "administrator", User.is_active.is_(True))).all()
    for user_id in ids:
        notify_user(db, user_id, title, message, href, kind)


def log_audit(
    db: Session, actor_id: int | None, action: str, entity_type: str, entity_id: int | None, details: str,
) -> None:
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details[:500],
    ))
=======
def notify_administrators(title: str, message: str, href: str, kind: str = "info") -> None:
    admins = db.client.table(TABLE_USERS).select("id").eq("role", "administrator").eq("is_active", True).execute()
    for admin in admins.data:
        notify_user(admin["id"], title, message, href, kind)
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
