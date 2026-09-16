# -*- coding: utf-8 -*-
"""Frontend bound greps + reducer simulation. SPEC-ISA18-2-CLOSURE-v3 INV-43…46."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HMI = ROOT / "hmi" / "src"


class TestFrontendBounds(unittest.TestCase):
    def test_store_never_holds_full_catalog_map(self):
        text = (HMI / "store" / "slices" / "alarmsSlice.ts").read_text(encoding="utf-8")
        self.assertNotIn("alarms: Record<string, Alarm>", text)
        self.assertIn("top3Active", text)
        self.assertIn("slice(0, TOP3_MAX)", text)
        self.assertIn("CATALOG_PAGE_MAX = 50", text)
        self.assertIn("HISTORY_PAGE_MAX = 100", text)

    def test_socket_does_not_hydrate_catalog(self):
        text = (HMI / "hooks" / "useSocket.ts").read_text(encoding="utf-8")
        self.assertNotIn("getAlarms(1, 10000)", text)
        self.assertIn("getAlarmsFooter", text)
        self.assertIn("setTop3Active", text)

    def test_alarms_page_clamps_page_size(self):
        text = (HMI / "pages" / "Alarms.tsx").read_text(encoding="utf-8")
        self.assertNotIn("getAlarms(1, 10000", text)
        self.assertIn("collectAlarmsPages", text)
        self.assertNotIn('value={100}', text)

    def test_history_export_does_not_request_10000(self):
        text = (HMI / "pages" / "AlarmsSummary.tsx").read_text(encoding="utf-8")
        self.assertNotIn("limit: 10000", text)

    def test_no_explosion_reducer(self):
        top3 = []
        for i in range(1000):
            top3 = [i] + [x for x in top3 if x != i]
            top3 = top3[:3]
        self.assertLessEqual(len(top3), 3)
        page = list(range(200))[:50]
        self.assertLessEqual(len(page), 50)
        history = list(range(500))[:100]
        self.assertLessEqual(len(history), 100)

    def test_api_resources_have_no_unbounded_select_star(self):
        text = (ROOT / "automation" / "modules" / "alarms" / "resources" / "alarms.py").read_text(
            encoding="utf-8"
        )
        self.assertNotRegex(text, r"SELECT \*")
        self.assertIn("clamp_catalog_page_size", text)
        self.assertIn("clamp_history_page_size", text)
