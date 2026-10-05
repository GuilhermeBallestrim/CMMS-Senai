from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('professor', 'administrator')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    notifications: Mapped[list[Notification]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id", ondelete="RESTRICT"), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120))
    asset_tag: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100))
    acquired_at: Mapped[date | None] = mapped_column(Date)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(30), default="Disponível", nullable=False)
    photo_name: Mapped[str | None] = mapped_column(String(255))
    manual_name: Mapped[str | None] = mapped_column(String(255))
    photo_mime: Mapped[str | None] = mapped_column(String(40))
    manual_mime: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    sector: Mapped[Sector] = relationship()
    responsible: Mapped[User | None] = relationship()


class MaintenanceCall(Base):
    __tablename__ = "maintenance_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Aberto", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    photo_name: Mapped[str | None] = mapped_column(String(255))
    photo_mime: Mapped[str | None] = mapped_column(String(40))

    equipment: Mapped[Equipment] = relationship()
    requester: Mapped[User] = relationship()
    work_order: Mapped[WorkOrder | None] = relationship(back_populates="call", uselist=False)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    call_id: Mapped[int] = mapped_column(ForeignKey("maintenance_calls.id", ondelete="RESTRICT"), unique=True, nullable=False)
    responsible_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Aguardando início", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    defect: Mapped[str | None] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    parts: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    call: Mapped[MaintenanceCall] = relationship(back_populates="work_order")
    responsible: Mapped[User] = relationship()


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    item: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="Em análise", nullable=False)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    href: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="info", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="notifications")


class UnitSettings(Base):
    __tablename__ = "unit_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    unit_name: Mapped[str] = mapped_column(String(160), default="SENAI — São Paulo", nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(80), default="America/Sao_Paulo", nullable=False)
    notify_admin_new_call: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
