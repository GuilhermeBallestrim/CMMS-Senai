"""Testes de rotas da API para ordens de serviço e chamados.

Usam TestClient do FastAPI com mock do cliente Supabase, sem exigir rede nem
banco configurado. Cobrem os cenários críticos de negócio de ordens de
serviço (RF-09 a RF-12) e aprovação de chamados.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from backend.api import router, csrf_header
from backend.database import db
from backend.dependencies import get_current_user


def _fake_client(rows_by_table: dict) -> MagicMock:
    """Mock encadeável do cliente Supabase a partir de {tabela: [linhas]}."""
    client = MagicMock()

    def table(name: str) -> MagicMock:
        # Acumula filtros e só os aplica em execute(), sem modificar os
        # dados permanentes do dicionário ao vivo.
        builder = MagicMock()
        builder._eq_filters = []
        builder._in_filters = []
        builder._insert_payload = None
        builder._update_payload = None
        builder._delete = False

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
            return builder

        def limit(n):
            return builder

        def range_(start, end):
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
    # Simula ambiente sem as funções RPC no Supabase: forca o fallback sequencial.
    client.rpc = MagicMock(side_effect=Exception("RPC indisponível"))
    return client


class _RouteTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI

        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="test-secret")
        self.app.include_router(router)
        self.rows = {}
        db._client = _fake_client(self.rows)

        self.user = {"id": 1, "name": "Admin", "email": "admin@test.test",
                     "role": "administrator", "is_active": True}
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[csrf_header] = lambda: None
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _login_as(self, role: str):
        user = next(u for u in self.rows["users"] if u["role"] == role)
        self.user = user
        self.app.dependency_overrides[get_current_user] = lambda: user


class WorkOrderFlowTests(_RouteTests):
    """Cenários críticos de ordem de serviço."""

    NOW = datetime.now(timezone.utc).isoformat()

    def setUp(self):
        super().setUp()
        self.rows["users"] = [
            {"id": 1, "name": "Admin", "email": "admin@test.test",
             "role": "administrator", "is_active": True,
             "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": 2, "name": "Tecnico", "email": "tec@test.test",
             "role": "tecnico", "is_active": True,
             "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": 3, "name": "Prof", "email": "prof@test.test",
             "role": "professor", "is_active": True,
             "created_at": "2026-01-01T00:00:00+00:00"},
        ]
        self.rows["maintenance_calls"] = [
            {
                "id": 10, "number": "CH-2026-AAAAAA", "equipment_id": 1,
                "requester_id": 3, "status": "Em análise", "priority": "Alta",
                "description": "Chamado de teste",
                "created_at": self.NOW, "updated_at": self.NOW,
            }
        ]
        self.rows["work_orders"] = [
            {
                "id": 1, "number": "OS-2026-AAAAAA", "call_id": 10,
                "responsible_id": 2, "status": "Aguardando início",
                "started_at": None, "finished_at": None, "solution": None,
                "defect": None, "cause": None, "parts": None, "notes": None,
            }
        ]

    def test_tecnico_atualiza_propria_os_para_em_execucao(self):
        self._login_as("tecnico")
        resp = self.client.patch("/api/work-orders/1", json={"status": "Em execução"})
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "Em execução")
        self.assertIsNotNone(data["started_at"])

    def test_tecnico_nao_consegue_mudar_responsavel(self):
        # O tecnico nao pode reatribuir: o campo e ignorado, o responsavel nao muda.
        self._login_as("tecnico")
        resp = self.client.patch(
            "/api/work-orders/1",
            json={"status": "Em execução", "responsible_id": 1},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["responsible_id"], 2)

    def test_administrador_pode_reatribuir_responsavel(self):
        self._login_as("administrator")
        resp = self.client.patch(
            "/api/work-orders/1",
            json={"status": "Em execução", "responsible_id": 1},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["responsible_id"], 1)

    def test_concluir_os_sem_solucao_previa_retorna_422(self):
        # WorkOrderUpdate nao tem campo solution; a solucao deve ja estar registrada.
        self._login_as("tecnico")
        resp = self.client.patch("/api/work-orders/1", json={"status": "Concluída"})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_concluir_os_com_solucao_previa_sucesso(self):
        self.rows["work_orders"][0]["solution"] = "Diagnostico prévio registrado."
        self._login_as("tecnico")
        resp = self.client.patch("/api/work-orders/1", json={"status": "Concluída"})
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "Concluída")
        self.assertEqual(data["solution"], "Diagnostico prévio registrado.")
        self.assertIsNotNone(data["finished_at"])

    def test_os_ja_concluida_nao_pode_ser_alterada(self):
        self.rows["work_orders"][0]["status"] = "Concluída"
        self._login_as("tecnico")
        resp = self.client.patch("/api/work-orders/1", json={"status": "Em execução"})
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_professor_nao_pode_atualizar_os(self):
        self._login_as("professor")
        resp = self.client.patch("/api/work-orders/1", json={"status": "Em execução"})
        self.assertEqual(resp.status_code, 403, resp.text)


class CallApprovalTests(_RouteTests):
    """Aprovacao de chamado e geracao de ordem de servico."""

    NOW = datetime.now(timezone.utc).isoformat()

    def setUp(self):
        super().setUp()
        self.rows["users"] = [
            {"id": 1, "name": "Admin", "email": "admin@test.test",
             "role": "administrator", "is_active": True},
        ]
        self.rows["maintenance_calls"] = [
            {
                "id": 20, "number": "CH-2026-BBBBBB", "equipment_id": 1,
                "requester_id": 1, "status": "Aberto", "priority": "Média",
                "description": "Outro chamado",
                "created_at": self.NOW, "updated_at": self.NOW,
            }
        ]
        self.rows["work_orders"] = []
        self.rows["equipment"] = [{"id": 1, "name": "Equipamento Teste"}]

    def test_administrador_aprova_chamado_e_gera_os(self):
        self._login_as("administrator")
        resp = self.client.post("/api/calls/20/approve")
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "Aguardando início")
        # Fallback sequencial: o chamado muda para 'Em analise'.
        self.assertEqual(self.rows["maintenance_calls"][0]["status"], "Em análise")
        # Uma OS deve ter sido criada para o chamado 20.
        orders = [o for o in self.rows["work_orders"] if o.get("call_id") == 20]
        self.assertTrue(orders, "Nenhuma ordem de serviço foi gerada.")

    def test_chamado_cancelado_nao_pode_ser_aprovado(self):
        self.rows["maintenance_calls"][0]["status"] = "Cancelado"
        self._login_as("administrator")
        resp = self.client.post("/api/calls/20/approve")
        self.assertEqual(resp.status_code, 409, resp.text)


if __name__ == "__main__":
    unittest.main()
