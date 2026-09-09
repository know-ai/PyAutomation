# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import tempfile
import unittest

from ..modules.settings.workspace import sanitize_workspace, save_realtime_trends_workspace, WORKSPACE_PATH


class TestRealtimeTrendsWorkspace(unittest.TestCase):
    def test_sanitize_caps_charts_and_tags(self):
        raw = {
            "kind": "real-time-trends",
            "charts": [
                {
                    "id": "a",
                    "title": "x" * 200,
                    "tagNames": [f"T{i}" for i in range(40)],
                    "bufferSize": 99999,
                    "w": 1,
                    "h": 1,
                }
            ]
            + [{"id": f"c{i}", "title": "c", "tagNames": []} for i in range(30)],
        }
        doc = sanitize_workspace(raw)
        self.assertEqual(doc["kind"], "real-time-trends")
        self.assertEqual(len(doc["charts"]), 24)
        self.assertEqual(len(doc["charts"][0]["title"]), 80)
        self.assertEqual(len(doc["charts"][0]["tagNames"]), 16)
        self.assertEqual(doc["charts"][0]["w"], 16)
        self.assertEqual(doc["charts"][0]["h"], 15)
        self.assertEqual(doc["charts"][0]["timeSpanMinutes"], 5)
        self.assertTrue(doc["charts"][0]["showThresholds"])
        self.assertNotIn("bufferSize", doc["charts"][0])

    def test_sanitize_persists_time_span_minutes(self):
        doc = sanitize_workspace(
            {
                "kind": "real-time-trends",
                "charts": [
                    {
                        "id": "span",
                        "title": "Span",
                        "tagNames": ["FI_01"],
                        "timeSpanMinutes": 5,
                    }
                ],
            }
        )
        self.assertEqual(doc["schemaVersion"], 3)
        self.assertEqual(doc["grid"]["cols"], 48)
        self.assertEqual(doc["charts"][0]["timeSpanMinutes"], 5)

    def test_sanitize_rejects_invalid_time_span(self):
        doc = sanitize_workspace(
            {"charts": [{"id": "x", "title": "x", "tagNames": [], "timeSpanMinutes": 7}]}
        )
        self.assertEqual(doc["charts"][0]["timeSpanMinutes"], 2)

    def test_save_roundtrip(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            os.makedirs("db", exist_ok=True)
            try:
                saved = save_realtime_trends_workspace(
                    {"charts": [{"id": "p1", "title": "Pressure", "tagNames": ["PI_01"]}]}
                )
                self.assertTrue(os.path.isfile(WORKSPACE_PATH))
                with open(WORKSPACE_PATH, encoding="utf-8") as handle:
                    on_disk = json.load(handle)
                self.assertEqual(on_disk["charts"][0]["id"], "p1")
                self.assertEqual(saved["charts"][0]["tagNames"], ["PI_01"])
            finally:
                os.chdir(cwd)

    def test_v3_width_is_not_clamped_to_twelve(self):
        doc = sanitize_workspace(
            {
                "schemaVersion": 3,
                "grid": {"cols": 48, "rowHeight": 10},
                "panelTitle": "Sala 1",
                "charts": [
                    {
                        "id": "wide",
                        "title": "Wide",
                        "tagNames": ["FI_01"],
                        "showThresholds": False,
                        "x": 0,
                        "y": 0,
                        "w": 24,
                        "h": 15,
                    }
                ],
            }
        )
        self.assertEqual(doc["schemaVersion"], 3)
        self.assertEqual(doc["panelTitle"], "Sala 1")
        self.assertEqual(doc["charts"][0]["w"], 24)
        self.assertFalse(doc["charts"][0]["showThresholds"])

    def test_legacy_twelve_col_migrates_to_forty_eight(self):
        doc = sanitize_workspace(
            {
                "schemaVersion": 2,
                "charts": [
                    {
                        "id": "legacy",
                        "title": "Legacy",
                        "tagNames": [],
                        "x": 3,
                        "y": 6,
                        "w": 6,
                        "h": 6,
                    }
                ],
            }
        )
        chart = doc["charts"][0]
        self.assertEqual(chart["x"], 12)
        self.assertEqual(chart["w"], 24)
        self.assertEqual(chart["y"], 15)
        self.assertEqual(chart["h"], 15)
        self.assertEqual(doc["grid"]["cols"], 48)


if __name__ == "__main__":
    unittest.main()
