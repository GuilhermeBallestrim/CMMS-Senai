from __future__ import annotations

import os
import secrets
import warnings
from dataclasses import dataclass
from pathlib import Path



def load_local_env() -> None:
    """Load simple KEY=VALUE settings without requiring python-dotenv."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(str(value).strip()))
    except (TypeError, ValueError):
        return default


POSTGRES_SCHEMES = {
    "postgres": "postgresql+psycopg",
    "postgresql": "postgresql+psycopg",
    "postgresql+psycopg2": "postgresql+psycopg",
    "postgresql+psycopg2binary": "postgresql+psycopg",
}


def normalize_database_url(url: str) -> str:
    """Accept the postgres:// form Supabase shows and map it to a SQLAlchemy driver.

    The Supabase dashboard displays `postgresql://user:pass@host:port/db`, but SQLAlchemy
    needs an explicit `+psycopg` driver. Only Postgres URLs are rewritten; anything else
    (notably `sqlite:///`, whose triple slash is significant) is returned untouched.
    """
    raw = url.strip()
    scheme = raw.split("://", 1)[0].lower() if "://" in raw else ""
    if scheme in POSTGRES_SCHEMES:
        return POSTGRES_SCHEMES[scheme] + raw[len(scheme):]
    return raw


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    session_https_only: bool
    db_pool_size: int
    db_max_overflow: int
    debug: bool


def load_settings() -> Settings:
    load_local_env()
    environment = os.getenv("CMMS_ENV", "development").lower()
    secret = os.getenv("CMMS_SESSION_SECRET")
    if not secret:
        if environment == "production":
            raise RuntimeError("CMMS_SESSION_SECRET é obrigatório em produção.")
        secret = secrets.token_urlsafe(48)
        warnings.warn(
            "CMMS_SESSION_SECRET não configurado; sessões serão invalidadas ao reiniciar o servidor.",
            RuntimeWarning,
            stacklevel=2,
        )
    database_url = normalize_database_url(
        os.getenv("CMMS_DATABASE_URL", "sqlite:///./cmms.db")
    )
    if environment == "production" and database_url.startswith("sqlite"):
        raise RuntimeError("CMMS_DATABASE_URL deve apontar para o Postgres em produção.")
    return Settings(
        database_url=database_url,
        session_secret=secret,
        session_https_only=environment == "production",
        db_pool_size=_as_int(os.getenv("CMMS_DB_POOL_SIZE"), 5),
        db_max_overflow=_as_int(os.getenv("CMMS_DB_MAX_OVERFLOW"), 5),
        debug=_as_bool(os.getenv("CMMS_DEBUG"), False),
    )


settings = load_settings()
