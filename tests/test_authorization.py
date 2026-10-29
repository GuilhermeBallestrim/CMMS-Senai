import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from backend.dependencies import require_roles


class AuthorizationDependencyTests(unittest.TestCase):
    def _user(self, role: str) -> dict:
        return {"id": 1, "name": "Teste", "email": "t@t.test", "role": role, "is_active": True}

    def test_administrator_role_is_accepted(self):
        dep = require_roles("administrator")
        request_user = self._user("administrator")
        # Simula a dependência interna chamando-a diretamente com o usuário já resolvido.
        inner = dep.__wrapped__ if hasattr(dep, "__wrapped__") else None
        # require_roles retorna uma função-dependência; chamamos via Depends manualmente.
        func = require_roles("administrator")
        # A função interna espera `user` como kwarg.
        result = func(user=request_user)
        self.assertEqual(result["role"], "administrator")

    def test_professor_is_rejected_for_admin_operation(self):
        func = require_roles("administrator")
        with self.assertRaises(HTTPException) as ctx:
            func(user=self._user("professor"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_unknown_role_is_rejected(self):
        func = require_roles("administrator", "tecnico")
        with self.assertRaises(HTTPException) as ctx:
            func(user=self._user("professor"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_multiple_allowed_roles(self):
        func = require_roles("professor", "administrator")
        for role in ("professor", "administrator"):
            result = func(user=self._user(role))
            self.assertEqual(result["role"], role)