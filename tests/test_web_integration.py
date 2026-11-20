"""Testes de integração para rotas web.

Usam TestClient com mock do Supabase, sem exigir rede nem banco configurado.
Cobrem login, chamados, equipamentos, ordens de serviço, solicitações
de compra e configurações.
"""
from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import main as main_module
from backend.database import db
from backend.security import hash_password


def _fake_client(rows_by_table: dict) -> MagicMock:
    """Mock encadeável do cliente Supabase a partir de {tabela: [linhas]}."""
    client = MagicMock()

    def table(name: str) -> MagicMock:
        builder = MagicMock()
        builder._eq_filters = []
        builder._in_filters = []
        builder._insert_payload = None
        builder._update_payload = None
        builder._delete = False
        builder._order_args = None
        builder._range_args = None
        builder._limit_n = None

        def _current_rows():
            return rows_by_table.setdefault(name, [])

        def select(*args, **kwargs):
            return builder

        def eq(col, value):
            builder._eq_filters.append((col, value))
            return builder

        def in_(col, values):
            builder._in_filters.append((col, list(values)))
            return builder

        def order(*args, **kwargs):
            builder._order_args = (args, kwargs)
            return builder

        def limit(n):
            builder._limit_n = n
            return builder

        def range_(start, end):
            builder._range_args = (start, end)
            return builder

        def insert(payload):
            builder._insert_payload = payload
            return builder

        def update(payload):
            builder._update_payload = payload
            return builder

        def delete():
            builder._delete = True
            return builder

        def execute():
            rows = list(_current_rows())
            for col, value in builder._eq_filters:
                rows = [r for r in rows if r.get(col) == value]
            for col, values in builder._in_filters:
                rows = [r for r in rows if r.get(col) in values]
            if builder._order_args:
                args, kwargs = builder._order_args
                desc = kwargs.get("desc", False)
                col = args[0] if args else "id"
                rows = sorted(rows, key=lambda r: r.get(col, ""), reverse=desc)
            if builder._limit_n is not None:
                rows = rows[: builder._limit_n]
            if builder._range_args is not None:
                start, end = builder._range_args
                rows = rows[start : end + 1]
            if builder._delete:
                rows_by_table[name][:] = []
                return MagicMock(data=[])
            if builder._update_payload is not None:
                for r in rows:
                    r.update(builder._update_payload)
                return MagicMock(data=rows)
            if builder._insert_payload is not None:
                payload = builder._insert_payload
                if isinstance(payload, list):
                    _current_rows().extend(payload)
                    return MagicMock(data=payload)
                new_id = max([r.get("id", 0) for r in _current_rows()], default=0) + 1
                row = dict(payload)
                row["id"] = new_id
                row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                _current_rows().append(row)
                return MagicMock(data=[row])
            return MagicMock(data=rows)

        builder.select = select
        builder.eq = eq
        builder.in_ = in_
        builder.order = order
        builder.limit = limit
        builder.range = range_
        builder.insert = insert
        builder.update = update
        builder.delete = delete
        builder.execute = execute
        return builder

    client.table = table
    client.rpc = MagicMock(side_effect=Exception("RPC indisponível"))
    return client


def _login(client: TestClient, email: str, password: str = "SenhaForte123") -> str:
    """Faz login pelo endpoint da API (define o cookie de sessão).

    Retorna o csrf_token da sessão para uso em requisições web POST.
    """
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login falhou: {resp.status_code} {resp.text}"
    # Extraímos o csrf_token de uma página que o renderiza.
    page = client.get("/chamados", follow_redirects=False)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
    return m.group(1) if m else ""


def _reset_rate_limit():
    """Limpa o rate limiter em memória entre testes."""
    from backend.rate_limit import _attempts

    _attempts.clear()


class WebIntegrationTests(unittest.TestCase):
    def setUp(self):
        _reset_rate_limit()
        self.app = main_module.app
        self.rows = {}
        db._client = _fake_client(self.rows)

        # Cria usuários no banco mock.
        self.rows["users"] = [
            {
                "id": 1,
                "name": "Admin",
                "email": "admin@example.com",
                "password_hash": hash_password("SenhaForte123"),
                "role": "administrator",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": 2,
                "name": "Tecnico",
                "email": "tec@example.com",
                "password_hash": hash_password("SenhaForte123"),
                "role": "tecnico",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": 3,
                "name": "Professor",
                "email": "prof@example.com",
                "password_hash": hash_password("SenhaForte123"),
                "role": "professor",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ]
        self.rows["sectors"] = [
            {"id": 1, "name": "Usinagem"},
            {"id": 2, "name": "Elétrica"},
        ]
        self.rows["equipment"] = [
            {"id": 1, "name": "Torno 01", "sector_id": 1, "asset_tag": "TO-01",
             "state": "Disponível", "responsible_id": None},
        ]
        self.rows["maintenance_calls"] = [
            {
                "id": 10,
                "number": "CH-2026-AAAAAA",
                "equipment_id": 1,
                "requester_id": 3,
                "description": "Chamado de teste",
                "priority": "Média",
                "status": "Aberto",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        ]
        self.rows["work_orders"] = [
            {
                "id": 1,
                "number": "OS-2026-AAAAAA",
                "call_id": 10,
                "responsible_id": 2,
                "status": "Aguardando início",
                "started_at": None,
                "finished_at": None,
                "solution": None,
                "defect": None,
                "cause": None,
                "parts": None,
                "notes": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ]
        self.rows["notifications"] = []
        self.rows["audit_logs"] = []
        self.rows["purchase_requests"] = []
        self.rows["unit_settings"] = [
            {"id": 1, "unit_name": "SENAI Teste", "timezone_name": "America/Sao_Paulo",
             "notify_admin_new_call": True}
        ]

        self.client = TestClient(self.app)

    def tearDown(self):
        _reset_rate_limit()
        db._client = None
        self.client.cookies.clear()

    # ------------------------------------------------------------------
    # Login / Logout
    # ------------------------------------------------------------------
    def test_login_page(self):
        resp = self.client.get("/login", follow_redirects=False)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_login_api(self):
        csrf = _login(self.client, "admin@example.com")
        self.assertIsNotNone(csrf)

    def test_login_invalid_credentials(self):
        resp = self.client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "senha_errada"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_logout(self):
        _login(self.client, "admin@example.com")
        resp = self.client.post(
            "/logout",
            data={"csrf_token": _login(self.client, "admin@example.com")},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)

    # ------------------------------------------------------------------
    # Chamados
    # ------------------------------------------------------------------
    def test_calls_list_requires_login(self):
        resp = self.client.get("/chamados", follow_redirects=False)
        self.assertEqual(resp.status_code, 303, resp.text)
        self.assertEqual(resp.headers["location"], "/login")

    def test_calls_list_admin(self):
        _login(self.client, "admin@example.com")
        resp = self.client.get("/chamados")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_create_call_professor(self):
        csrf = _login(self.client, "prof@example.com")
        resp = self.client.post(
            "/chamados",
            data={
                "equipment_id": 1,
                "description": "Descricao do novo chamado com mais de dez caracteres.",
                "priority": "Alta",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        self.assertIn("/chamados", resp.headers["location"])

    # ------------------------------------------------------------------
    # Aprovar chamado
    # ------------------------------------------------------------------
    def test_approve_call_admin(self):
        csrf = _login(self.client, "admin@example.com")
        resp = self.client.post(
            "/chamados/10/aprovar",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        # Verifica que a OS foi criada.
        self.assertTrue(
            any(o.get("call_id") == 10 for o in self.rows["work_orders"]),
            "Nenhuma ordem de serviço foi gerada.",
        )

    # ------------------------------------------------------------------
    # Cancelar chamado
    # ------------------------------------------------------------------
    def test_cancel_call_professor_owner(self):
        csrf = _login(self.client, "prof@example.com")
        resp = self.client.post(
            "/chamados/10/cancelar",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        call = self.rows["maintenance_calls"][0]
        self.assertEqual(call["status"], "Cancelado")

    def test_cancel_call_professor_not_owner(self):
        self.rows["maintenance_calls"][0]["requester_id"] = 1
        csrf = _login(self.client, "prof@example.com")
        resp = self.client.post(
            "/chamados/10/cancelar",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    # ------------------------------------------------------------------
    # Equipamentos
    # ------------------------------------------------------------------
    def test_equipment_list_admin(self):
        _login(self.client, "admin@example.com")
        resp = self.client.get("/equipamentos")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_create_equipment_admin(self):
        csrf = _login(self.client, "admin@example.com")
        resp = self.client.post(
            "/equipamentos",
            data={
                "name": "Fresa 02",
                "sector_id": 1,
                "model_name": "",
                "serial_number": "",
                "acquired_at": "",
                "asset_tag": "FR-02",
                "state": "Disponível",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        self.assertTrue(
            any(e.get("asset_tag") == "FR-02" for e in self.rows["equipment"]),
            "Equipamento não foi criado.",
        )

    # ------------------------------------------------------------------
    # Ordens de serviço
    # ------------------------------------------------------------------
    def test_work_order_list_tecnico(self):
        _login(self.client, "tec@example.com")
        resp = self.client.get("/ordens-servico")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_update_work_order_status_tecnico(self):
        csrf = _login(self.client, "tec@example.com")
        resp = self.client.post(
            "/ordens-servico/1",
            data={
                "status": "Em execução",
                "solution": "",
                "notes": "",
                "defect": "",
                "cause": "",
                "parts": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        order = self.rows["work_orders"][0]
        self.assertEqual(order["status"], "Em execução")
        self.assertIsNotNone(order["started_at"])

    def test_update_work_order_diagnostic_tecnico(self):
        csrf = _login(self.client, "tec@example.com")
        # Primeiro move para Em execução.
        self.client.post(
            "/ordens-servico/1",
            data={
                "status": "Em execução",
                "solution": "",
                "notes": "",
                "defect": "",
                "cause": "",
                "parts": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        # Depois atualiza diagnóstico.
        resp = self.client.post(
            "/ordens-servico/1",
            data={
                "status": "Em execução",
                "solution": "Troca de rolamentos.",
                "notes": "Observacao de teste.",
                "defect": "Rolamento gasto.",
                "cause": "Desgaste natural.",
                "parts": "Rolamento 6204.",
                "csrf_token": _login(self.client, "tec@example.com"),
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        order = self.rows["work_orders"][0]
        self.assertEqual(order["solution"], "Troca de rolamentos.")
        self.assertEqual(order["notes"], "Observacao de teste.")
        self.assertEqual(order["defect"], "Rolamento gasto.")
        self.assertEqual(order["cause"], "Desgaste natural.")
        self.assertEqual(order["parts"], "Rolamento 6204.")

    def test_conclude_work_order_tecnico(self):
        csrf = _login(self.client, "tec@example.com")
        # Registra solução prévia.
        self.rows["work_orders"][0]["solution"] = "Diagnostico prévio."
        resp = self.client.post(
            "/ordens-servico/1",
            data={
                "status": "Concluída",
                "solution": "Conclusao final.",
                "notes": "",
                "defect": "",
                "cause": "",
                "parts": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        order = self.rows["work_orders"][0]
        self.assertEqual(order["status"], "Concluída")
        self.assertIsNotNone(order["finished_at"])
        # Chamado deve estar Concluído.
        call = self.rows["maintenance_calls"][0]
        self.assertEqual(call["status"], "Concluído")

    def test_tecnico_cannot_update_other_work_order(self):
        self.rows["work_orders"][0]["responsible_id"] = 1  # outro usuário
        csrf = _login(self.client, "tec@example.com")
        resp = self.client.post(
            "/ordens-servico/1",
            data={
                "status": "Em execução",
                "solution": "",
                "notes": "",
                "defect": "",
                "cause": "",
                "parts": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    # ------------------------------------------------------------------
    # Solicitações de compra
    # ------------------------------------------------------------------
    def test_create_purchase_request(self):
        csrf = _login(self.client, "prof@example.com")
        resp = self.client.post(
            "/solicitacoes",
            data={
                "item_type": "Peças e componentes",
                "item": "Filtro de oleo",
                "quantity": 5,
                "justification": "Necessario para manutencao preventiva.",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        self.assertTrue(
            any(r.get("item") == "Filtro de oleo" for r in self.rows["purchase_requests"]),
            "Solicitacao de compra nao foi criada.",
        )

    def test_decide_purchase_request_admin(self):
        self.rows["purchase_requests"] = [
            {
                "id": 1,
                "number": "SC-2026-AAAAAA",
                "requester_id": 3,
                "item_type": "Peças e componentes",
                "item": "Filtro",
                "quantity": 1,
                "justification": "Teste.",
                "status": "Em análise",
                "reviewed_by_id": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        csrf = _login(self.client, "admin@example.com")
        resp = self.client.post(
            "/solicitacoes/1/decidir",
            data={"decision": "Aprovada", "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        pr = self.rows["purchase_requests"][0]
        self.assertEqual(pr["status"], "Aprovada")

    # ------------------------------------------------------------------
    # Configurações
    # ------------------------------------------------------------------
    def test_create_user_admin(self):
        csrf = _login(self.client, "admin@example.com")
        resp = self.client.post(
            "/configuracoes/usuarios",
            data={
                "name": "Novo Usuario",
                "email": "novo@example.com",
                "password": "SenhaForte123",
                "role": "tecnico",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        self.assertTrue(
            any(u.get("email") == "novo@example.com" for u in self.rows["users"]),
            "Usuario nao foi criado.",
        )

    def test_create_sector_admin(self):
        csrf = _login(self.client, "admin@example.com")
        resp = self.client.post(
            "/configuracoes/setores",
            data={"name": "Novo Setor", "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303, resp.text)
        self.assertTrue(
            any(s.get("name") == "Novo Setor" for s in self.rows["sectors"]),
            "Setor nao foi criado.",
        )

    # ------------------------------------------------------------------
    # Rate limiting no login
    # ------------------------------------------------------------------
    def test_login_rate_limiting(self):
        for i in range(12):
            resp = self.client.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "errada"},
            )
        self.assertEqual(resp.status_code, 429, resp.text)


if __name__ == "__main__":
    unittest.main()