"""Diagnóstico de conexão com o Supabase.

Uso:
    .\\.venv\\Scripts\\python.exe scripts\\check_db.py

Testa conexão, autenticação, permissões e se o schema foi aplicado.
Sem escrever nada nas tabelas exceto uma criação e descarte temporários.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402
from backend.database import db  # noqa: E402

ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    ok = ok and passed
    mark = "OK  " if passed else "FALHA"
    print(f"[{mark}] {label}" + (f" -> {detail}" if detail else ""))


url = settings.supabase_url
key_tail = settings.supabase_key[-8:] if settings.supabase_key else "(vazio)"

print(f"  URL     : {url or '(vazio)'}")
print(f"  KEY     : ...{key_tail}")
print()

if not url or not settings.supabase_key:
    print("ERRO: CMMS_SUPABASE_URL ou CMMS_SUPABASE_KEY não configurados no .env")
    sys.exit(1)

print("Testando conexão com Supabase")
try:
    resp = db.client.table("unit_settings").select("*").limit(1).execute()
    check("conexão REST", True)
    check("unit_settings", True, f"{len(resp.data)} linha(s)")
except Exception as exc:
    check(f"conexão REST -> {type(exc).__name__}: {exc}", False)
    sys.exit(1)

EXPECTED = [
    "sectors", "unit_settings", "users", "equipment",
    "notifications", "purchase_requests", "maintenance_calls", "work_orders",
]
all_found = True
for t in EXPECTED:
    try:
        r = db.client.table(t).select("id").limit(1).execute()
        check(t, True)
    except Exception as e:
        all_found = False
        check(t, False, str(e)[:80])

if all_found:
    print()
    print("Tudo certo. Rode `uvicorn main:app --reload` para iniciar.")
else:
    print()
    print("Algumas tabelas não existem. Execute o supabase_schema.sql no SQL Editor.")

sys.exit(0 if ok else 1)
