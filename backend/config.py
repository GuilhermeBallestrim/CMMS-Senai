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


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    session_https_only: bool


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
        database_url=os.getenv("CMMS_DATABASE_URL", "sqlite:///./cmms.db"),
        session_secret=secret,
        session_https_only=environment == "production",
    )


settings = load_settings()
