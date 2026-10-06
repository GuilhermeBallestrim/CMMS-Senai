"""Diagnóstico de conexão com o Postgres/Supabase.

Uso (na pasta do projeto):
    .\\.venv\\Scripts\\python.exe scripts\\check_db.py

Ele não escreve nada: apenas testa DNS, TLS, autenticação, permissões e se o
schema do Alembic já foi aplicado. Rode antes do `alembic upgrade head`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.database import Base, engine  # noqa: E402
from backend import models  # noqa: F401,E402

EXPECTED_TABLES = {
    "sectors",
    "unit_settings",
    "users",
    "equipment",
    "notifications",
    "purchase_requests",
    "maintenance_calls",
    "work_orders",
}

ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    ok = ok and passed
    mark = "OK  " if passed else "FALHA"
    print(f"[{mark}] {label}" + (f" -> {detail}" if detail else ""))


url = settings.database_url
print("Configuração")
print(f"  CMMS_DATABASE_URL scheme : {url.split('://')[0]}")
print(f"  host                     : {url.split('@')[-1].split('/')[0] or '(sqlite)'}")
print(f"  pool                     : {settings.db_pool_size} + {settings.db_max_overflow}")
print()

if url.startswith("sqlite"):
    print("AVISO: CMMS_DATABASE_URL aponta para SQLite.")
    print("       Para validar o Supabase, defina CMMS_DATABASE_URL com a URI do pooler.")
    print("       (Settings -> Database -> Connection string -> URI, porta 5432)")
    print()
    with engine.connect() as connection:
        check("conexão local", True)
        found = set(inspect(engine).get_table_names())
    check("tabelas do modelo presentes", EXPECTED_TABLES <= found,
          f"faltando: {sorted(EXPECTED_TABLES - found) or 'nenhuma'}")
    sys.exit(0 if ok else 1)

print("Conectando ao Postgres")
try:
    with engine.connect() as connection:
        check("conexão + autenticação", True)
        version = connection.execute(text("select version()")).scalar_one()
        check("servidor", True, version.split(" on ")[0])

        with connection.begin():
            connection.execute(text("create temporary table _cmms_probe (id int)"))
            connection.execute(text("insert into _cmms_probe values (1)"))
            connection.execute(text("drop table _cmms_probe"))
        check("transações", True)

        current_schema = connection.execute(text("select current_schema()")).scalar_one()
        check("schema de trabalho", True, current_schema)

        found = set(inspect(engine).get_table_names())
        check("schema aplicado pelo Alembic", EXPECTED_TABLES <= found,
              f"faltando: {sorted(EXPECTED_TABLES - found) or 'nenhuma'}" if EXPECTED_TABLES - found
              else "todas as 8 tabelas presentes")

        if "alembic_version" in found:
            revision = connection.execute(text("select version_num from alembic_version")).scalar_one_or_none()
            check("alembic_version", True, str(revision))
        else:
            print("[INFO ] alembic_version ausente: execute `alembic upgrade head`.")
except Exception as exc:  # noqa: BLE001
    print(f"[FALHA] {type(exc).__name__}: {exc}")
    print()
    print("Causas comuns:")
    print("  - host/regiao errados na URI (use a regiao que aparece no painel)")
    print("  - senha com caractere especial sem encoding: troque @ por %40, : por %3A, / por %2F")
    print("  - firewall corporativo bloqueando a saida; teste o modo transacional (porta 6543)")
    sys.exit(1)

print()
print("Tudo certo." if ok else "Ha pendencias acima.")
sys.exit(0 if ok else 1)
