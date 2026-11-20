"""Testes de autorização por perfil nas rotas críticas da API.

Usam TestClient com mock do Supabase, sem exigir rede. Verificam que cada
perfil (administrator, tecnico, professor) só acessa as operações que lhe
são permitidas.
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
    client.rpc = MagicMock(return_value=MagicMock(data=None))
    return client


class AuthorizationRouteTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI

        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="test-secret")
        self.app.include_router(router)
        self.rows = {}
        db._client = _fake_client(self.rows)

        self.admin = {"id": 1, "name": "Admin", "email": "admin@test.test",
                      "role": "administrator", "is_active": True,
                      "created_at": "2026-01-01T00:00:00+00:00"}
        self.tecnico = {"id": 2, "name": "Tecnico", "email": "tec@test.test",
                        "role": "tecnico", "is_active": True,
                        "created_at": "2026-01-01T00:00:00+00:00"}
        self.professor = {"id": 3, "name": "Prof", "email": "prof@test.test",
                          "role": "professor", "is_active": True,
                          "created_at": "2026-01-01T00:00:00+00:00"}
        self.app.dependency_overrides[csrf_header] = lambda: None
        self.client = TestClient(self.app)

    def _as(self, user):
        self.app.dependency_overrides[get_current_user] = lambda: user
        return user

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_administrator_pode_listar_usuarios(self):
        self.rows["users"] = [self.admin, self.tecnico, self.professor]
        self._as(self.admin)
        resp = self.client.get("/api/users")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_tecnico_nao_pode_listar_usuarios(self):
        self.rows["users"] = [self.admin, self.tecnico]
        self._as(self.tecnico)
        resp = self.client.get("/api/users")
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_professor_nao_pode_listar_usuarios(self):
        self.rows["users"] = [self.admin, self.professor]
        self._as(self.professor)
        resp = self.client.get("/api/users")
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_administrator_pode_criar_setor(self):
        self.rows["sectors"] = []
        self._as(self.admin)
        resp = self.client.post("/api/sectors", json={"name": "Novo Setor"})
        self.assertEqual(resp.status_code, 201, resp.text)

    def test_tecnico_nao_pode_criar_setor(self):
        self.rows["sectors"] = []
        self._as(self.tecnico)
        resp = self.client.post("/api/sectors", json={"name": "Novo Setor"})
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_administrator_pode_criar_equipamento(self):
        self.rows["sectors"] = [{"id": 1, "name": "Usinagem"}]
        self.rows["equipment"] = []
        self._as(self.admin)
        resp = self.client.post("/api/equipment", json={
            "name": "Torno Teste", "sector_id": 1, "asset_tag": "TO-99"
        })
        self.assertEqual(resp.status_code, 201, resp.text)

    def test_tecnico_nao_pode_criar_equipamento(self):
        self.rows["sectors"] = [{"id": 1, "name": "Usinagem"}]
        self.rows["equipment"] = []
        self._as(self.tecnico)
        resp = self.client.post("/api/equipment", json={
            "name": "Torno Teste", "sector_id": 1, "asset_tag": "TO-99"
        })
        self.assertEqual(resp.status_code, 403, resp.text)

    NOW = "2026-01-01T00:00:00+00:00"

    def _call(self, call_id: int, requester_id: int, status: str = "Aberto") -> dict:
        return {
            "id": call_id,
            "number": f"CH-{call_id}",
            "equipment_id": 1,
            "requester_id": requester_id,
            "description": "Descricao do chamado",
            "priority": "Média",
            "status": status,
            "created_at": self.NOW,
            "updated_at": self.NOW,
        }

    def test_professor_so_ve_os_próprios_chamados(self):
        self.rows["maintenance_calls"] = [
            self._call(1, 3),
            self._call(2, 1),
        ]
        self._as(self.professor)
        resp = self.client.get("/api/calls")
        self.assertEqual(resp.status_code, 200, resp.text)
        ids = [c["id"] for c in resp.json()]
        self.assertEqual(ids, [1])

    def test_administrator_ve_todos_os_chamados(self):
        self.rows["maintenance_calls"] = [
            self._call(1, 3),
            self._call(2, 1),
        ]
        self._as(self.admin)
        resp = self.client.get("/api/calls")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(len(resp.json()), 2)

    def test_audit_logs_somente_administrador(self):
        self.rows["audit_logs"] = [{
            "id": 1, "actor_id": 1, "action": "created",
            "entity_type": "user", "entity_id": 5, "details": "Cadastrou usuario",
            "created_at": "2026-01-01T00:00:00+00:00",
        }]
        self._as(self.admin)
        resp = self.client.get("/api/audit-logs")
        self.assertEqual(resp.status_code, 200, resp.text)

        self._as(self.tecnico)
        resp = self.client.get("/api/audit-logs")
        self.assertEqual(resp.status_code, 403, resp.text)

        self._as(self.professor)
        resp = self.client.get("/api/audit-logs")
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_indicadores_somente_administrador(self):
        self.rows["maintenance_calls"] = []
        self.rows["equipment"] = []
        self.rows["work_orders"] = []
        self._as(self.admin)
        resp = self.client.get("/api/indicators")
        self.assertEqual(resp.status_code, 200, resp.text)

        self._as(self.tecnico)
        resp = self.client.get("/api/indicators")
        self.assertEqual(resp.status_code, 403, resp.text)


    def test_equipment_photo_endpoint_nao_quebra(self):
        self.rows["equipment"] = [{"id": 1, "name": "Eq", "photo_name": None}]
        self._as(self.admin)
        resp = self.client.get("/api/equipment/1/photo")
        self.assertIn(resp.status_code, (404, 200), resp.text)


if __name__ == "__main__":
    unittest.main()
