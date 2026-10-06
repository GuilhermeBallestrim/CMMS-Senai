# SENAI CMMS

Sistema web de gestão de manutenção industrial. O projeto usa FastAPI, Jinja2 e PostgreSQL (Supabase em produção, SQLite local em desenvolvimento).

## Banco de dados

O schema é versionado pelo Alembic. Em desenvolvimento o SQLite cria as tabelas sozinho; em produção o schema vem das migrações.

### Desenvolvimento (SQLite, sem configuração)

```powershell
python -m alembic upgrade head   # opcional: o uvicorn também cria o schema no SQLite
python -m backend.cli create-admin
python -m uvicorn main:app --reload
```

### Produção (Supabase/PostgreSQL)

1. Crie o projeto em [supabase.com](https://supabase.com) e abra **Settings → Database → Connection string → URI**.
2. Copie a URI **do session pooler (porta 5432)**. No `.env`:

   ```dotenv
   CMMS_ENV=production
   CMMS_DATABASE_URL=postgresql://postgres.PROJECT_REF:SENHA@aws-0-REGIAO.pooler.supabase.com:5432/postgres
   CMMS_SESSION_SECRET=<chave aleatória>
   ```

   A URI pode ser colada como aparece no painel: o backend converte `postgresql://` para `postgresql+psycopg://`. Se a senha tiver caractere especial (`@ : / # ?`), ela precisa estar codificada em URL (`%40`, `%3A`, `%2F`).

3. Aplique as migrações e valide:

   ```powershell
   python -m alembic upgrade head
   python scripts\check_db.py
   ```

O `check_db.py` testa DNS, TLS, autenticação, transações e se as 8 tabelas existem, sem escrever nada.

**Sobre o pool.** `CMMS_DB_POOL_SIZE` e `CMMS_DB_MAX_OVERFLOW` controlam as conexões abertas; a soma não deve passar do limite do seu plano, porque o pooler do Supabase é o gargalo. `pool_recycle` já está em 1800s para descartar conexões ociosas que o pooler fecha.

Em `CMMS_ENV=production` o servidor **recusa** subir se o schema não existir, em vez de tentar criá-lo — assim não há duas fontes de verdade sobre o formato do banco.

## Configuração no Windows

Pré-requisitos: Python 3.12 (ou compatível com as dependências em `requirements.txt`) e espaço livre para instalar os pacotes.

No PowerShell, na pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Defina `CMMS_SESSION_SECRET` em `.env` com um valor aleatório privado (por exemplo, gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Sem essa variável, o servidor emite um aviso a cada boot e todas as sessões expiram ao reiniciar.

Em seguida crie o primeiro administrador de forma interativa e inicie o servidor:

```powershell
python -m backend.cli create-admin
python -m uvicorn main:app --reload
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000). Não há credenciais predefinidas; use o e-mail e a senha informados ao criar o administrador.

Se a ativação do ambiente for bloqueada pelo PowerShell, execute diretamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.cli create-admin
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

## Perfis e permissões

- **Professor:** consulta equipamentos e setores, abre e acompanha os próprios chamados e solicitações de compra.
- **Administrador:** pode tudo que o professor pode; além disso, gerencia usuários/equipamentos/setores, aprova chamados e solicitações, atualiza ordens de serviço e consulta histórico/indicadores.

Os papéis aceitos são somente `professor` e `administrator` (apresentado na interface como Administrador). As APIs sob `/api` exigem sessão, aplicam autorização no servidor e protegem alterações com token CSRF. A documentação interativa fica em `/docs`.

## Rotas principais da API

- `GET /api/health`, `/api/auth/csrf`, `/api/auth/me`; `POST /api/auth/login` e `/api/auth/logout`
- `GET/POST /api/users`, `PATCH /api/users/{id}/active` (administrador)
- `GET/POST /api/sectors` (criação por administrador)
- `GET/POST /api/equipment`, `GET /api/equipment/{id}` (criação por administrador)
- `GET/POST /api/calls`, `GET/PATCH /api/calls/{id}`, `POST /api/calls/{id}/approve`
- `GET/PATCH /api/work-orders`, `GET /api/work-orders/{id}`
- `GET/POST /api/purchase-requests`, `PATCH /api/purchase-requests/{id}`
- `GET /api/history` e `/api/indicators` (indicadores para administrador)
- `GET /api/notifications`, `POST /api/notifications/read-all`, `PATCH /api/notifications/{id}/read`
- `GET/PUT /api/unit-settings` (administrador)
- `POST /api/calls/{id}/photo`, `POST /api/equipment/{id}/files`; arquivos servidos por rotas autenticadas

## Telas conectadas

Chamados, equipamentos, solicitações de compra, ordens de serviço, histórico, indicadores e configurações de usuários/setores usam os registros do banco. O professor vê e altera seus próprios chamados e pedidos; o administrador também pode cadastrar usuários/equipamentos/setores, aprovar chamados e pedidos e atualizar ordens de serviço.

Notificações são criadas para chamados, atualizações de ordens e decisões de compras. As preferências da unidade salvam nome, fuso horário e aviso administrativo de novos chamados. Fotos aceitam JPEG, PNG ou WebP (até 10 MB); manuais aceitam PDF (até 20 MB). Os uploads ficam na pasta ignorada `uploads/` e exigem sessão para leitura.
