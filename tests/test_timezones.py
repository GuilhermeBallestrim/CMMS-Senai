from datetime import datetime, timezone
import unittest

from main import format_local_datetime


class TimezoneFormattingTests(unittest.TestCase):
    def test_formats_utc_datetime_in_selected_zone(self):
        value = datetime(2026, 10, 28, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(format_local_datetime(value, "America/Sao_Paulo"), "28/10/2026 00:30")

    def test_uses_sao_paulo_as_safe_fallback_for_invalid_zone(self):
        value = datetime(2026, 10, 28, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(format_local_datetime(value, "Invalid/Timezone"), "28/10/2026 00:30")
