import unittest

from httpx import ConnectError

from backend.database import db
from backend.models import TABLE_AUDIT_LOGS
from backend.services import log_audit


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.created_ids = []

    def tearDown(self):
        for entry_id in self.created_ids:
            try:
                db.client.table(TABLE_AUDIT_LOGS).delete().eq("id", entry_id).execute()
            except Exception:
                pass

    def test_persists_audit_entry_with_actor_and_entity(self):
        try:
            log_audit(None, "updated", "equipment", 15, "Atualizou o equipamento EQ-15.")
            rows = (
                db.client.table(TABLE_AUDIT_LOGS)
                .select("*")
                .eq("entity_type", "equipment")
                .eq("entity_id", 15)
                .order("id", desc=True)
                .limit(1)
                .execute()
                .data
            )
        except ConnectError as exc:  # ambiente sem rede/DB
            self.skipTest(f"Supabase indisponível neste ambiente: {exc}")
            return
        self.assertTrue(rows, "A entrada de auditoria não foi persistida.")
        entry = rows[0]
        self.created_ids.append(entry["id"])
        self.assertEqual(entry["entity_type"], "equipment")
        self.assertEqual(entry["entity_id"], 15)
        self.assertEqual(entry["action"], "updated")