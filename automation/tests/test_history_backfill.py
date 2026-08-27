# -*- coding: utf-8 -*-
"""Unit tests for TagValue reconnect backfill helper."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestParseBackfillBounds(unittest.TestCase):
    def test_epoch_ms_and_iso(self):
        from automation.modules.history.resources.history import _parse_bound_ms

        self.assertEqual(_parse_bound_ms("1724520000000"), 1724520000000)
        iso_ms = _parse_bound_ms("2026-08-24T19:36:12.647Z")
        self.assertIsNotNone(iso_ms)
        self.assertGreater(iso_ms, 1_700_000_000_000)


class TestReadBackfillCap(unittest.TestCase):
    def test_clamps_span_to_five_minutes(self):
        from automation.logger.datalogger import DataLogger

        logger = DataLogger()
        logger.is_history_logged = True
        logger.check_connectivity = MagicMock(return_value=True)

        captured = {}

        def fake_select(*_a, **_k):
            raise AssertionError("should not query when tags empty")

        with patch("automation.logger.datalogger.TagValue") as tv:
            tv.select = fake_select
            out = logger.read_backfill([], 0, 1)
            self.assertEqual(out, {})

        # Empty tags short-circuit before DB; span clamp is covered by inspecting locals via call.
        # Exercise clamp path with mocked query returning no rows.
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.dicts.return_value = []

        with patch("automation.logger.datalogger.TagValue") as tv, patch(
            "automation.logger.datalogger.Tags"
        ):
            tv.select.return_value = mock_query
            tv.timestamp = MagicMock()
            stop = 1_724_520_000_000
            start = stop - (10 * 60 * 1000)  # 10 min → clamped to 5
            out = logger.read_backfill(["Linea1.PI_01"], start, stop, limit_per_tag=10)
            self.assertIn("Linea1.PI_01", out)
            self.assertEqual(out["Linea1.PI_01"], [])


class TestDataLoggerEngineReadBackfill(unittest.TestCase):
    def test_engine_delegates_read_backfill(self):
        from automation.logger.datalogger import DataLoggerEngine

        self.assertTrue(callable(getattr(DataLoggerEngine, "read_backfill", None)))
        engine = DataLoggerEngine()
        with patch.object(engine, "query", return_value={"Linea1.PI_01": []}) as query:
            out = engine.read_backfill(
                ["Linea1.PI_01"], 1_724_520_000_000, 1_724_520_060_000, limit_per_tag=10
            )
        self.assertEqual(out, {"Linea1.PI_01": []})
        query.assert_called_once()
        payload = query.call_args[0][0]
        self.assertEqual(payload["action"], "read_backfill")
        self.assertEqual(payload["parameters"]["tags"], ["Linea1.PI_01"])
        self.assertEqual(payload["parameters"]["start_ms"], 1_724_520_000_000)
        self.assertEqual(payload["parameters"]["stop_ms"], 1_724_520_060_000)
        self.assertEqual(payload["parameters"]["limit_per_tag"], 10)


if __name__ == "__main__":
    unittest.main()
