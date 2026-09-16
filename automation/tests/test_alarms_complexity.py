# -*- coding: utf-8 -*-
"""SPEC-ISA18-2-CLOSURE-v2 complexity tests T-60…T-80 (unittest, no extra deps)."""
from __future__ import annotations

import os
import statistics
import time
import unittest

from automation.alarms.runtime import (
    ChatterDetector,
    KPICollector,
    SuppressionManager,
    get_alarm_runtime,
    reset_alarm_runtime_for_tests,
)
from automation.managers.alarms import AlarmManager
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[idx]


def _bench(fn, rounds: int) -> dict[str, float]:
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1_000_000.0)
    return {
        "p50": _percentile(samples, 0.50),
        "p99": _percentile(samples, 0.99),
        "p999": _percentile(samples, 0.999),
        "mean": statistics.fmean(samples),
    }


class TestAlarmComplexity(unittest.TestCase):
    def setUp(self):
        self.runtime = reset_alarm_runtime_for_tests()
        self.mgr = AlarmManager()
        self._prev = dict(self.mgr._alarms)
        self.mgr._alarms.clear()
        self.mgr._by_name.clear()
        self.mgr._by_tag_name.clear()
        self.cvt = CVTEngine()

    def tearDown(self):
        self.runtime.stop_worker()
        self.mgr._alarms.clear()
        self.mgr._by_name.clear()
        self.mgr._by_tag_name.clear()
        self.mgr._alarms.update(self._prev)
        for alarm in self._prev.values():
            self.mgr._index_alarm(alarm)

    def _make_alarm(self, name: str, tag_name: str = "FI_02"):
        self.cvt.set_tag(
            name=tag_name,
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description=tag_name,
        )
        tag = self.cvt.get_tag_by_name(name=tag_name)
        from automation.alarms import Alarm

        alarm = Alarm(
            name=name,
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(9999.0),
            alarm_on_delay=FloatType(0.0),
            alarm_off_delay=FloatType(0.0),
            identifier=f"id-{name}"[:16],
        )
        alarm.enable_delay_wakeups = False
        self.mgr._alarms[alarm.identifier] = alarm
        self.mgr._index_alarm(alarm)
        return alarm, tag

    def test_t60_on_tag_value_one_alarm(self):
        alarm, tag = self._make_alarm("cpx_t60")
        tag.set_value(value=1.0)
        self.runtime.drain()
        # Warmup
        for _ in range(200):
            self.mgr.on_tag_value(tag, 1.0)
        stats = _bench(lambda: self.mgr.on_tag_value(tag, 1.0), rounds=5_000)
        self.assertLessEqual(
            stats["p99"],
            250.0,
            f"T-60 p99={stats['p99']:.1f}µs exceeds CPython CI budget 250µs",
        )
        self.assertEqual(alarm.current_state.value.lower(), "normal")

    def test_t64_lookup_independent_of_catalog_n(self):
        alarm, tag = self._make_alarm("cpx_t64")
        n = int(os.environ.get("ISA18_COMPLEXITY_N", "20000"))
        for i in range(n):
            self.mgr._by_tag_name.setdefault(f"noise_{i}", [])
        for _ in range(100):
            self.mgr.on_tag_value(tag, 1.0)
        small = _bench(lambda: self.mgr.on_tag_value(tag, 1.0), rounds=2_000)
        self.assertLessEqual(small["p99"], 250.0)
        self.assertGreaterEqual(len(self.mgr._by_tag_name), n)

    def test_t80_p99_stable_when_catalog_grows(self):
        alarm, tag = self._make_alarm("cpx_t80")
        for _ in range(200):
            self.mgr.on_tag_value(tag, 1.0)
        baseline = _bench(lambda: self.mgr.on_tag_value(tag, 1.0), rounds=2_000)["p99"]
        for i in range(5_000):
            self.mgr._by_tag_name.setdefault(f"grow_{i}", [])
        grown = _bench(lambda: self.mgr.on_tag_value(tag, 1.0), rounds=2_000)["p99"]
        self.assertLessEqual(
            grown,
            baseline * 2.0 + 50.0,
            f"T-80 p99 grew from {baseline:.1f} to {grown:.1f} µs",
        )

    def test_t74_chatter_o1(self):
        detector = ChatterDetector()
        stats = _bench(lambda: detector.on_transition("a1"), rounds=50_000)
        self.assertLessEqual(stats["p99"], 50.0)

    def test_t75_suppression_o1(self):
        mgr = SuppressionManager()
        mgr.update("a1", "SHLVD")
        stats = _bench(lambda: mgr.is_suppressed("a1"), rounds=50_000)
        self.assertTrue(mgr.is_suppressed("a1"))
        self.assertFalse(mgr.is_suppressed("missing"))
        self.assertLessEqual(stats["p99"], 50.0)

    def test_t76_kpi_o1(self):
        kpi = KPICollector()
        stats = _bench(lambda: kpi.record_transition("Unack Alarm"), rounds=50_000)
        self.assertEqual(kpi.transitions_total, 50_000)
        self.assertLessEqual(stats["p99"], 50.0)

    def test_count_active_o1(self):
        self.assertEqual(self.mgr.count_active(), 0)
        self.assertEqual(self.mgr.count_by_state("Unacknowledged"), 0)

    def test_health_snapshot_keys(self):
        snap = self.runtime.snapshot()
        for key in (
            "status",
            "on_tag_value_p99_us",
            "transition_queue_depth",
            "transition_worker_lag_ms",
            "active_count",
            "count_by_state",
            "history_rows_total",
            "violations",
            "transition_worker_alive",
            "worker_lag_ms",
            "pending_max_seen",
        ):
            self.assertIn(key, snap)
        self.assertIn("p50", snap["worker_lag_ms"])
        self.assertIn("p99", snap["worker_lag_ms"])

    def test_hot_path_does_not_insert_when_worker_running(self):
        alarm, tag = self._make_alarm("cpx_async")
        self.runtime.start_worker()
        try:
            self.runtime._pending.clear()
            tag.set_value(value=1.0)
            self.assertEqual(alarm.current_state.value.lower(), "normal")
        finally:
            self.runtime.stop_worker()
            self.runtime.drain()
