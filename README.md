# SENAI CMMS

Sistema web de gestão de manutenção industrial. O projeto usa FastAPI, Jinja2 e Supabase (PostgreSQL) como única fonte de persistência.

## Banco de dados

O schema é versionado pelo arquivo `supabase_schema.sql` (PostgreSQL/Supabase). Não há SQLite local nem Alembic: em todos os ambientes a aplicação conecta ao Supabase.

### Configuração do Supabase

1. Crie o projeto em [supabase.com](https://supabase.com).
2. Abra **Settings → API** e copie a **Project URL** e a **service_role key** (nunca a anon key).
3. Abra **Settings → SQL Editor → New query**, cole o conteúdo de `supabase_schema.sql` e execute. Isso cria as 9 tabelas (sectors, users, unit_settings, equipment, maintenance_calls, work_orders, purchase_requests, notifications, audit_logs) e os dados iniciais.
4. No `.env`:

   ```dotenv
   CMMS_ENV=production
   CMMS_SUPABASE_URL=https://SEU_PROJETO.supabase.co
   CMMS_SUPABASE_KEY=cole-aqui-a-service-role-key
   CMMS_SESSION_SECRET=<chave aleatória>
   ```

Para validar a conexão e o schema sem escrever nada:

```powershell
python scripts\check_db.py
```

## Configuração no Windows

Pré-requisitos: Python 3.12 (ou compatível com as dependências em `requirements.txt`).

No PowerShell, na pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Defina `CMMS_SUPABASE_URL`, `CMMS_SUPABASE_KEY` e `CMMS_SESSION_SECRET` em `.env` (gere a chave com `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Sem `CMMS_SESSION_SECRET`, o servidor emite um aviso a cada boot e todas as sessões expiram ao reiniciar.

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
- **Técnico:** consulta equipamentos e setores, visualiza a fila de chamados e ordens de serviço, e registra a execução (diagnóstico, causa, solução, peças) nas ordens a ele atribuídas.
- **Administrador:** pode tudo que os demais perfis podem; além disso, gerencia usuários/equipamentos/setores, aprova chamados e solicitações, atribui técnicos às ordens de serviço e consulta histórico/indicadores.

Os papéis aceitos são somente `professor` e `administrator` (apresentado na interface como Administrador). As APIs sob `/api` exigem sessão, aplicam autorização no servidor e protegem alterações com token CSRF. A documentação interativa fica em `/docs`.

## Rotas principais da API

- `GET /api/health`, `/api/auth/csrf`, `/api/auth/me`; `POST /api/auth/login` e `/api/auth/logout`
- `GET/POST /api/users`, `PATCH /api/users/{id}/active` (administrador)
- `GET/POST /api/sectors` (criação por administrador)
- `GET/POST/PATCH /api/equipment`, `GET /api/equipment/{id}`, `GET /api/equipment/{id}/historico` (criação/edição por administrador)
- `GET/POST /api/calls`, `GET/PATCH /api/calls/{id}`, `POST /api/calls/{id}/approve`, `POST /api/calls/{id}/atribuicoes`, `POST /api/calls/{id}/photo`
- `GET/PATCH /api/work-orders`, `GET /api/work-orders/{id}`
- `GET/POST /api/purchase-requests`, `PATCH /api/purchase-requests/{id}`
- `GET /api/history` e `/api/indicators` (indicadores para administrador)
- `GET /api/notifications`, `POST /api/notifications/read-all`, `PATCH /api/notifications/{id}/read`
- `GET/PUT /api/unit-settings` (administrador)
- `GET /api/audit-logs` (administrador)
- `POST /api/equipment/{id}/files`; arquivos servidos por rotas autenticadas

## Telas conectadas

Chamados, equipamentos, solicitações de compra, ordens de serviço, histórico, indicadores e configurações de usuários/setores usam os registros do banco. O professor vê e altera seus próprios chamados e pedidos; o administrador também pode cadastrar usuários/equipamentos/setores, aprovar chamados e pedidos e atualizar ordens de serviço.

Notificações são criadas para chamados, atualizações de ordens e decisões de compras. As preferências da unidade salvam nome, fuso horário e aviso administrativo de novos chamados. Fotos aceitam JPEG, PNG ou WebP (até 10 MB); manuais aceitam PDF (até 20 MB). Os uploads ficam na pasta ignorada `uploads/` e exigem sessão para leitura.

## Verificação

Execute a verificação de sintaxe e os testes unitários antes de enviar alterações:

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py backend
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

O teste de auditoria (`tests/test_audit.py`) é um teste de integração contra o Supabase e é automaticamente pulado quando não há conectividade de rede com o projeto configurado.