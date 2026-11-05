import sys
sys.path.insert(0, '.')
from backend.database import db
from backend.models import TABLE_EQUIPMENT as E, TABLE_SECTORS as S, TABLE_USERS as U, TABLE_MAINTENANCE_CALLS as C

print("=== Testando conexao direta com Supabase ===")

# Testar equipment
try:
    resp = db.client.table(E).select("*").execute()
    print(f"equipment: {len(resp.data)} linhas")
    for row in resp.data[:3]:
        print(f"  {row}")
except Exception as e:
    print(f"equipment ERRO: {type(e).__name__}: {e}")

# Testar sectors
try:
    resp = db.client.table(S).select("*").execute()
    print(f"\nsectors: {len(resp.data)} linhas")
    for row in resp.data[:3]:
        print(f"  {row}")
except Exception as e:
    print(f"sectors ERRO: {type(e).__name__}: {e}")

# Testar users
try:
    resp = db.client.table(U).select("*").execute()
    print(f"\nusers: {len(resp.data)} linhas")
    for row in resp.data[:3]:
        print(f"  {row.get('email', '?')}")
except Exception as e:
    print(f"users ERRO: {type(e).__name__}: {e}")

# Testar maintenance_calls
try:
    resp = db.client.table(C).select("*").execute()
    print(f"\nmaintenance_calls: {len(resp.data)} linhas")
except Exception as e:
    print(f"maintenance_calls ERRO: {type(e).__name__}: {e}")
