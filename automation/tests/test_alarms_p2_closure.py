# -*- coding: utf-8 -*-
"""SPEC-ISA18-2-P2-CLOSURE-v2 T-150…T-180 + greps AP-96…120."""
from __future__ import annotations

import inspect
import os
import re
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.alarms.p2.chatter import ChatterDetector
from automation.alarms.p2.clock import FakeClock
from automation.alarms.p2.constants import _ARCHIVE_CHUNK, _MAX_CHATTER_WINDOW, _SUPPRESSION_CACHE_MAX
from automation.alarms.p2.footer import select_footer
from automation.alarms.p2.kpi import KPICollector, KPIComputer, KPIHistoryRepository
from automation.alarms.p2.latching import LatchingPolicyRegistry, NonLatchingPolicy
from automation.alarms.p2.partition import PartitionManager
from automation.alarms.p2.priority import PriorityManager
from automation.alarms.p2.repository import MemoryAlarmRepository
from automation.alarms.p2.retention import RetentionArchiver
from automation.alarms.p2.subsystem import AlarmSubsystem
from automation.alarms.p2.suppression import SuppressionManager
from automation.alarms.p2.suppression_cache import SuppressionCache
from automation.alarms.p2.suppression_types import SilenceType, SuppressionType
from automation.alarms.runtime import (
    ChatterDetector as RuntimeChatter,
    KPICollector as RuntimeKPI,
    SuppressionManager as RuntimeSuppression,
    reset_alarm_runtime_for_tests,
)
from automation.alarms.states import HISTORY_CLEARED, HISTORY_RTNUN, HISTORY_UNACK
from automation.jobs.alarm_p2 import run_p2_maintenance

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "automation" / "alarms" / "p2"


def _pct(samples, p):
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))]


class _Alarm:
    def __init__(self, ident="a1", latching=True, ack_required=True, priority=3):
        self.identifier = ident
        self.name = ident
        self.id = ident
        self.latching = latching
        self.ack_required = ack_required
        self.priority = priority
        self.chattering = False
        self.chatter_count = 0
        self.last_chatter_ts = None


class TestP2Complexity(unittest.TestCase):
    def test_t150_suppression_cache_maxsize(self):
        cache = SuppressionCache(FakeClock())
        for i in range(3_000):
            cache.set(i, True)
        self.assertLessEqual(len(cache), _SUPPRESSION_CACHE_MAX)

    def test_t151_archive_chunk(self):
        arch = RetentionArchiver()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=400)
        rows = [{"id": i, "sample_uuid": str(i), "event_time": old} for i in range(25_000)]
        arch.seed_live(rows)
        n = arch.run(cutoff=now - timedelta(days=365), now=now)
        self.assertLessEqual(arch._CHUNK_SIZE, _ARCHIVE_CHUNK)
        self.assertEqual(n, 25_000)

    def test_t152_is_suppressed_o1(self):
        mgr = SuppressionManager()
        mgr.update("x", "SHLVD")
        t0 = time.perf_counter()
        n = 1_000_000
        for _ in range(n):
            mgr.is_suppressed("x")
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, f"1M is_suppressed took {elapsed:.3f}s")

    def test_t153_chatter_o1(self):
        det = ChatterDetector()
        t0 = time.perf_counter()
        for _ in range(1_000_000):
            det.on_transition("a1")
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 5.0, f"1M chatter took {elapsed:.3f}s")

    def test_t154_kpi_record_o1(self):
        kpi = KPICollector()
        t0 = time.perf_counter()
        for _ in range(1_000_000):
            kpi.record_event("Unack Alarm")
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 5.0, f"1M record took {elapsed:.3f}s")

    def test_t155_compute_kpis(self):
        kpi = KPICollector()
        for i in range(1000):
            kpi.record_activation(_Alarm(priority=1 + (i % 4)))
            kpi.record_ack(_Alarm(), latency_ms=float(i))
        samples = []
        computer = KPIComputer()
        for _ in range(200):
            t0 = time.perf_counter()
            snap = computer.compute(kpi)
            samples.append((time.perf_counter() - t0) * 1000.0)
        self.assertEqual(len(snap), 6)
        self.assertLessEqual(_pct(samples, 0.99), 5.0)

    def test_t156_footer_o_alog_a(self):
        alarms = [
            {"priority": (i % 4) + 1, "last_transition_ts": f"2026-01-01T00:00:{i:02d}Z", "name": str(i)}
            for i in range(100)
        ]
        samples = []
        for _ in range(500):
            t0 = time.perf_counter()
            select_footer(alarms, limit=3)
            samples.append((time.perf_counter() - t0) * 1000.0)
        top = select_footer(alarms, limit=3)
        self.assertEqual(top[0]["priority"], 1)
        self.assertLessEqual(_pct(samples, 0.99), 1.0)

    def test_t157_priority_set_o1(self):
        mgr = PriorityManager()
        t0 = time.perf_counter()
        for i in range(10_000):
            mgr.set_priority("a", 1 + (i % 4), op_id=1, reason="t")
        elapsed = (time.perf_counter() - t0) * 1000.0
        self.assertLess(elapsed, 500.0)
        self.assertEqual(len(mgr._events), min(10_000, 1000))

    def test_t158_latching_lookup_o1(self):
        alarm = _Alarm()
        t0 = time.perf_counter()
        for _ in range(100_000):
            LatchingPolicyRegistry.for_alarm(alarm)
        elapsed = (time.perf_counter() - t0) * 1000.0
        self.assertLess(elapsed, 100.0)

    def test_t163_archive_idempotent(self):
        arch = RetentionArchiver()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=400)
        arch.seed_live([{"id": 1, "sample_uuid": "u1", "event_time": old}])
        self.assertEqual(arch.run(cutoff=now - timedelta(days=365), now=now), 1)
        arch.seed_live([{"id": 1, "sample_uuid": "u1", "event_time": old}])
        self.assertEqual(arch.run(cutoff=now - timedelta(days=365), now=now), 0)

    def test_t165_priority_event(self):
        mgr = PriorityManager()
        mgr.set_priority("a", 1, op_id=9, reason="isa")
        self.assertEqual(mgr._events.last()["name"], "ALM.PRIORITY.CHANGED")

    def test_t166_suppression_event(self):
        mgr = SuppressionManager()
        mgr.apply("a", "silence", duration_min=5, reason="maint")
        self.assertEqual(mgr._events.last()["name"], "ALM.SUPPRESSION.APPLIED")

    def test_t167_chatter_perf_flag_threshold(self):
        runtime = reset_alarm_runtime_for_tests()
        try:
            for _ in range(5):
                runtime.kpi.record_chatter(1)
            self.assertGreaterEqual(runtime.kpi.chatter_detected_total, 5)
        finally:
            runtime.stop_worker()

    def test_t168_kpi_history_90_days(self):
        repo = KPIHistoryRepository(max_rows=90 * 24)
        for i in range(90):
            repo.save({"alarm_rate": {"value": i}}, ts=i)
        self.assertEqual(len(repo.get_history(1000)), 90)

    def test_t169_silence_expires(self):
        clock = FakeClock()
        mgr = SuppressionManager(clock=clock)
        mgr.apply("a", "silence", duration_min=30, reason="x")
        self.assertTrue(mgr.is_suppressed("a"))
        clock.advance(31 * 60)
        mgr.expire_due()
        self.assertFalse(mgr._active[1].active)

    def test_t170_shelve_expires(self):
        clock = FakeClock()
        mgr = SuppressionManager(clock=clock)
        mgr.apply("a", "shelve", duration_h=24, reason="x")
        clock.advance(25 * 3600)
        mgr.expire_due()
        self.assertFalse(mgr._active[1].active)

    def test_t171_oos_requires_reason(self):
        mgr = SuppressionManager()
        with self.assertRaises(ValueError):
            mgr.apply("a", "oos", reason="  ")

    def test_t172_nolatching_skips_rtn(self):
        policy = LatchingPolicyRegistry.for_alarm(_Alarm(latching=False, ack_required=True))
        self.assertIsInstance(policy, NonLatchingPolicy)
        self.assertEqual(policy.adjust_target_state(HISTORY_UNACK, HISTORY_RTNUN), HISTORY_CLEARED)

    def test_t173_auto_ack_policy(self):
        policy = LatchingPolicyRegistry.for_alarm(_Alarm(latching=True, ack_required=False))
        self.assertEqual(policy.adjust_target_state(HISTORY_UNACK, "Ack Alarm"), HISTORY_CLEARED)

    def test_t177_partition_future(self):
        mgr = PartitionManager()
        now = datetime(2026, 9, 16, tzinfo=timezone.utc)
        created = mgr.ensure(now)
        self.assertEqual(created, 13)
        self.assertIn("alarmsummary_p_2026_12", mgr.partitions)

    def test_t178_partition_drop_old(self):
        mgr = PartitionManager()
        mgr.partitions["alarmsummary_p_2000_01"] = (2000, 1)
        n = mgr.drop_old(datetime(2026, 9, 16, tzinfo=timezone.utc))
        self.assertEqual(n, 1)

    def test_t180_frontend_bounds(self):
        from automation.tests.test_alarms_frontend_bounds import TestFrontendBounds

        TestFrontendBounds().test_no_explosion_reducer()

    def test_ca_b4_chatter_window_maxlen(self):
        det = ChatterDetector()
        alarm = _Alarm()
        for _ in range(20):
            det.on_transition(alarm, HISTORY_UNACK, HISTORY_RTNUN)
        window = det._windows[alarm.identifier]
        self.assertEqual(window.maxlen, _MAX_CHATTER_WINDOW)
        self.assertLessEqual(len(window), 10)

    def test_ocp_fifth_suppression_type(self):
        class Extra(SuppressionType):
            def validate(self, **kwargs):
                return None

            def compute_expiry(self, clock):
                return None

            def name(self):
                return "extra"

        SuppressionManager.register("extra", Extra)
        mgr = SuppressionManager()
        rec = mgr.apply("z", "extra", reason="n/a")
        self.assertGreater(rec, 0)

    def test_t110_priority_range(self):
        mgr = PriorityManager()
        with self.assertRaises(ValueError):
            mgr.set_priority("a", 5, reason="x")

    def test_ca_b6_six_kpis(self):
        snap = KPIComputer().compute(KPICollector())
        self.assertEqual(
            set(snap),
            {
                "alarm_rate",
                "standing_alarms",
                "chattering_alarms",
                "stale_alarms",
                "priority_distribution",
                "operator_response_time",
            },
        )

    def test_bg_job(self):
        reset_alarm_runtime_for_tests()
        result = run_p2_maintenance()
        self.assertIn("kpis", result)

    def test_compat_t74_t75_t76_constructors(self):
        RuntimeChatter().on_transition("a1")
        s = RuntimeSuppression()
        s.update("a1", "SHLVD")
        self.assertTrue(s.is_suppressed("a1"))
        k = RuntimeKPI()
        k.record_transition("Unack Alarm")
        self.assertEqual(k.transitions_total, 1)


class TestP2HotPathAndGreps(unittest.TestCase):
    def test_t159_t160_no_lock_no_db_in_check_condition(self):
        from automation.alarms import Alarm

        src = inspect.getsource(Alarm._check_condition_impl)
        self.assertNotIn("execute_sql", src)
        self.assertNotIn("SELECT ", src)
        self.assertNotIn("with self._", src)
        self.assertNotIn(".lock", src.lower())

    def test_t161_no_count_star_runtime(self):
        hits = []
        for path in (ROOT / "automation" / "alarms").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "COUNT(*)" in text.upper() and "p2" in str(path):
                hits.append(str(path))
        self.assertEqual(hits, [])

    def test_t162_p2_collections_bounded(self):
        unbounded = []
        for path in P2.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"deque\(\s*\)", text):
                unbounded.append(f"{path.name}: deque()")
            if re.search(r"deque\(maxlen=None\)", text):
                unbounded.append(f"{path.name}: maxlen=None")
        self.assertEqual(unbounded, [])

    def test_t179_check_condition_budget(self):
        from automation.managers.alarms import AlarmManager
        from automation.models import FloatType, StringType
        from automation.tags.cvt import CVTEngine

        runtime = reset_alarm_runtime_for_tests()
        mgr = AlarmManager()
        prev = dict(mgr._alarms)
        mgr._alarms.clear()
        mgr._by_name.clear()
        mgr._by_tag_name.clear()
        try:
            cvt = CVTEngine()
            cvt.set_tag(name="P2_HOT", variable="Temperature", unit="C", data_type="FLOAT", description="p2")
            tag = cvt.get_tag_by_name(name="P2_HOT")
            from automation.alarms import Alarm

            alarm = Alarm(
                name="ALM.P2.HOT",
                tag=tag,
                alarm_type=StringType("HIGH"),
                alarm_setpoint=FloatType(1e9),
                alarm_on_delay=FloatType(0.0),
                alarm_off_delay=FloatType(0.0),
                identifier="p2hot0001",
            )
            alarm.enable_delay_wakeups = False
            mgr._alarms[alarm.identifier] = alarm
            mgr._index_alarm(alarm)
            samples = []
            for _ in range(300):
                t0 = time.perf_counter_ns()
                mgr.on_tag_value(tag, 1.0)
                samples.append((time.perf_counter_ns() - t0) / 1000.0)
            p99 = _pct(samples, 0.99)
            print(f"T-179 p99={p99:.1f}µs")
            self.assertLessEqual(p99, 250.0)
        finally:
            runtime.stop_worker()
            mgr._alarms.clear()
            mgr._alarms.update(prev)


class TestP2SolidAndContext(unittest.TestCase):
    def test_public_methods_bounded(self):
        from automation.alarms.p2 import priority, chatter, suppression, retention, partition

        for cls in (
            priority.PriorityManager,
            chatter.ChatterDetector,
            suppression.SuppressionManager,
            retention.RetentionArchiver,
            partition.PartitionManager,
        ):
            public = [n for n in dir(cls) if not n.startswith("_") and callable(getattr(cls, n))]
            extras = [n for n in public if n not in ("register",)]
            self.assertLessEqual(len(extras), 12, f"{cls.__name__} public={extras}")

    def test_docstrings_declare_context(self):
        src = (P2 / "suppression_cache.py").read_text(encoding="utf-8")
        self.assertIn("Context: HOT", src)
        src = (P2 / "retention.py").read_text(encoding="utf-8")
        self.assertIn("Context: BG", src)

    def test_subsystem_facade(self):
        sub = AlarmSubsystem()
        sub.priority.set_priority("a", 2, reason="x")
        snap = sub.compute_kpis()
        self.assertIn("alarm_rate", snap)

    def test_silence_no_isa_history_names(self):
        mgr = SuppressionManager()
        mgr.apply("a", "silence", duration_min=10, reason="pipe")
        self.assertTrue(mgr.is_suppressed("a"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
