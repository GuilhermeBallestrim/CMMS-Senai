from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
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


def migrate_schema() -> None:
    """Add nullable columns introduced after the initial SQLite prototype."""
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "equipment": {"photo_mime": "VARCHAR(40)", "manual_mime": "VARCHAR(40)"},
        "maintenance_calls": {"photo_name": "VARCHAR(255)", "photo_mime": "VARCHAR(40)"},
    }
    existing_tables = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspect(engine).get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
