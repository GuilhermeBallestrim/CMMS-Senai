from __future__ import annotations

import os
import secrets
import warnings
from dataclasses import dataclass
from pathlib import Path


def load_local_env() -> None:
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


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    session_secret: str
    session_https_only: bool
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
    return Settings(
        supabase_url=os.getenv("CMMS_SUPABASE_URL", ""),
        supabase_key=os.getenv("CMMS_SUPABASE_KEY", ""),
        session_secret=secret,
        session_https_only=environment == "production",
        debug=_as_bool(os.getenv("CMMS_DEBUG"), False),
    )


settings = load_settings()
