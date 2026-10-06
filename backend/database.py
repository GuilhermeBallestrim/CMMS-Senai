from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    pass


def _engine_options() -> dict:
    options: dict = {"pool_pre_ping": True, "future": True}
    if settings.database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        # O Supabase encerra conexões ociosas do pooler; o pool precisa ser
        # descartável e nunca deve exceder o limite do plano (PgBouncer).
        options["pool_size"] = settings.db_pool_size
        options["max_overflow"] = settings.db_max_overflow
        options["pool_recycle"] = 1800
        options["pool_timeout"] = 10
        # prepare_threshold=None mantém o driver sem prepared statements; é o
        # ajuste mais seguro caso o pooler seja trocado pelo modo transacional.
        options["connect_args"] = {"prepare_threshold": None, "application_name": "senai-cmms"}
    return options


engine = create_engine(settings.database_url, **_engine_options())


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
