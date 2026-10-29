import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.database import Base
from backend.models import AuditLog, User
from backend.services import log_audit


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.user = User(
            name="Administrador de teste",
            email="admin@example.test",
            password_hash="not-used-by-this-test",
            role="administrator",
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_persists_audit_entry_with_actor_and_entity(self):
        log_audit(self.session, self.user.id, "updated", "equipment", 15, "Atualizou o equipamento EQ-15.")
        self.session.commit()

        entry = self.session.scalar(select(AuditLog))

        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor_id, self.user.id)
        self.assertEqual(entry.entity_type, "equipment")
        self.assertEqual(entry.entity_id, 15)
