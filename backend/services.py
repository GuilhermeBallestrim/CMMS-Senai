from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Notification, User


def notify_user(db: Session, user_id: int, title: str, message: str, href: str, kind: str = "info") -> None:
    db.add(Notification(user_id=user_id, title=title, message=message, href=href, kind=kind))


def notify_administrators(db: Session, title: str, message: str, href: str, kind: str = "info") -> None:
    ids = db.scalars(select(User.id).where(User.role == "administrator", User.is_active.is_(True))).all()
    for user_id in ids:
        notify_user(db, user_id, title, message, href, kind)
