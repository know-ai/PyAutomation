# -*- coding: utf-8 -*-
"""CA-TZ: plant timezone presentation (Operación Hora Única)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pytz

from ..tags.tag import Tag
from ..timebase import ensure_utc, format_display_datetime, iso_millis
from ..modules.system.resources.system import plant_timezone_payload


class TestSocketIsoUtc(unittest.TestCase):
    def test_serialize_socket_emits_iso_offset(self):
        tag = Tag(name="F1", unit="C", variable="Temperature", data_type="float", id="f1f1f1f1")
        stamp = datetime(2026, 8, 14, 15, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=21.5, timestamp=stamp)
        payload = tag.serialize_socket()
        ts = payload["timestamp"]
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)
        self.assertTrue(ts.endswith("+00:00") or ts.endswith("Z"), ts)
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        self.assertEqual(parsed.astimezone(timezone.utc), stamp)

    def test_iso_millis_naive_is_utc(self):
        naive = datetime(2026, 8, 14, 15, 0, 0)
        rendered = iso_millis(naive)
        self.assertTrue(rendered.endswith("+00:00") or rendered.endswith("Z"), rendered)


class TestAlarmSummaryTimezone(unittest.TestCase):
    def test_caracas_lima_delta_one_hour(self):
        utc = datetime(2026, 8, 14, 15, 0, 0, tzinfo=timezone.utc)
        caracas = format_display_datetime(utc, "America/Caracas")
        lima = format_display_datetime(utc, "America/Lima")
        self.assertNotEqual(caracas, lima)
        caracas_hour = datetime.strptime(caracas.split(".")[0], "%m/%d/%Y, %H:%M:%S")
        lima_hour = datetime.strptime(lima.split(".")[0], "%m/%d/%Y, %H:%M:%S")
        delta_hours = (caracas_hour - lima_hour).total_seconds() / 3600.0
        self.assertEqual(delta_hours, 1.0)

    def test_fallback_uses_automation_timezone(self):
        utc = datetime(2026, 8, 14, 15, 0, 0, tzinfo=timezone.utc)
        rendered = format_display_datetime(utc, None)
        self.assertIsInstance(rendered, str)
        self.assertIn("2026", rendered)


class TestEnsureUtc(unittest.TestCase):
    def test_aware_converts_to_utc(self):
        caracas = pytz.timezone("America/Caracas")
        aware = caracas.localize(datetime(2026, 8, 14, 11, 0, 0))
        utc = ensure_utc(aware)
        self.assertEqual(utc.tzinfo, timezone.utc)
        self.assertEqual(utc.hour, 15)

    def test_naive_assumed_utc(self):
        naive = datetime(2026, 8, 14, 15, 0, 0)
        utc = ensure_utc(naive)
        self.assertEqual(utc.tzinfo, timezone.utc)
        self.assertEqual(utc.hour, 15)


class TestPlantTimezoneEndpoint(unittest.TestCase):
    def test_payload_exposes_plant_role(self):
        payload = plant_timezone_payload()
        self.assertEqual(payload["role"], "plant")
        self.assertTrue(payload["timezone"])
        self.assertIn("AUTOMATION_TIMEZONE", payload["description"])


if __name__ == "__main__":
    unittest.main()
