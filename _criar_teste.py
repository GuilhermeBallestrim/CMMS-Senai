import sys
sys.path.insert(0, '.')
from backend.database import db
from backend.security import hash_password

# Criar usuário de teste para validar rotas
email = "teste@teste.com"
senha = "Teste12345678"

# Verificar se já existe
resp = db.client.table("users").select("*").eq("email", email).execute()
if resp.data:
    print(f"Usuário {email} já existe (id={resp.data[0]['id']})")
else:
    resp = db.client.table("users").insert({
        "name": "Usuário Teste",
        "email": email,
        "password_hash": hash_password(senha),
        "role": "administrator",
        "is_active": True,
    }).execute()
    print(f"Usuário criado: {resp.data[0]['id']} - {email}")
    print(f"Senha: {senha}")

# Listar todos os usuários
resp = db.client.table("users").select("id, name, email, role, is_active").execute()
print(f"\nUsuários no banco ({len(resp.data)}):")
for u in resp.data:
    print(f"  {u['email']} - {u['role']} - ativo={u['is_active']}")
