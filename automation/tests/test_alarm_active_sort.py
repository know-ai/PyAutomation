# -*- coding: utf-8 -*-
"""Orden de alarmas activas con fechas naive y aware mezcladas."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from automation.alarms.runtime import AlarmRuntime


class TestActiveAlarmSort(unittest.TestCase):
    def test_mixed_naive_and_aware_timestamps_sort(self):
        runtime = AlarmRuntime()
        naive = SimpleNamespace(
            identifier="naive",
            last_transition_ts=datetime(2026, 10, 1, 14, 0, 0),
            timestamp=None,
        )
        aware = SimpleNamespace(
            identifier="aware",
            last_transition_ts=datetime(2026, 10, 1, 15, 0, 0, tzinfo=timezone.utc),
            timestamp=None,
        )
        missing = SimpleNamespace(
            identifier="missing",
            last_transition_ts=None,
            timestamp=None,
        )
        runtime._annunciated = {"naive": naive, "aware": aware, "missing": missing}
        ordered = [item.identifier for item in runtime.active_alarms()]
        self.assertEqual(ordered, ["aware", "naive", "missing"])
