# -*- coding: utf-8 -*-
"""SPEC-ISA18-2-CLOSURE-v3 T-90…T-100 (unittest, no extra deps)."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import os
import time
import unittest
from unittest.mock import patch

from automation.alarms.config import AlarmConfig
from automation.alarms.pagination import clamp_catalog_page_size, clamp_history_page_size
from automation.alarms.runtime import (
    KIND_EMIT,
    TransitionEvent,
    get_alarm_runtime,
    reset_alarm_runtime_for_tests,
)
from automation.managers.alarms import AlarmManager
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine


class _Dummy:
    identifier = "dummy"
    name = "dummy"
    last_transition_to = None
    state = None


class TestP1QueueAndHealth(unittest.TestCase):
    def setUp(self):
        self.runtime = reset_alarm_runtime_for_tests()

    def tearDown(self):
        self.runtime.stop_worker()

    def test_t90_overflow_at_maxlen(self):
        dummy = _Dummy()
        for _ in range(self.runtime._PENDING_TRANSITIONS_MAXLEN):
            self.runtime.enqueue(dummy, KIND_EMIT)
        self.assertEqual(self.runtime._pending_transitions.maxlen, 100_000)
        self.assertEqual(len(self.runtime._pending_transitions), 100_000)
        self.assertIn("ALM.PERF.ALARM_QUEUE_OVERFLOW", self.runtime._perf_flags)
        self.assertEqual(self.runtime._perf_flags["ALM.PERF.ALARM_QUEUE_OVERFLOW"]["severity"], "CRITICAL")

    def test_t91_backlog_warns_once(self):
        dummy = _Dummy()
        for _ in range(10_001):
            self.runtime.enqueue(dummy, KIND_EMIT)
        self.assertIn("ALM.PERF.ALARM_QUEUE_BACKLOG", self.runtime._perf_flags)
        self.assertTrue(self.runtime._backlog_warned)
        self.runtime._perf_flags.clear()
        self.runtime.enqueue(dummy, KIND_EMIT)
        self.assertNotIn("ALM.PERF.ALARM_QUEUE_BACKLOG", self.runtime._perf_flags)

    def test_t92_health_worker_alive_and_lag(self):
        snap = self.runtime.snapshot()
        self.assertIn("transition_worker_alive", snap)
        self.assertIsInstance(snap["transition_worker_alive"], bool)
        lag = snap["worker_lag_ms"]
        for key in ("p50", "p95", "p99", "count"):
            self.assertIn(key, lag)
        self.assertFalse(snap["transition_worker_alive"])
        self.assertEqual(snap["status"], "unhealthy")
        self.assertIn("WORKER_DEAD", snap["violations"])

    def test_t94_health_p99_under_5ms(self):
        samples = []
        for _ in range(1000):
            t0 = time.perf_counter()
            self.runtime.snapshot()
            samples.append((time.perf_counter() - t0) * 1000.0)
        samples.sort()
        p99 = samples[int(len(samples) * 0.99)]
        self.assertLessEqual(p99, 5.0, f"health p99={p99:.3f}ms")

    def test_t95_pending_max_seen(self):
        dummy = _Dummy()
        for _ in range(17):
            self.runtime.enqueue(dummy, KIND_EMIT)
        self.assertEqual(self.runtime._pending_max_seen, 17)
        self.runtime.dequeue_batch(max_size=10)
        self.assertEqual(self.runtime._pending_max_seen, 17)

    def test_t91_queue_backlog_violation(self):
        dummy = _Dummy()
        for _ in range(10_001):
            self.runtime.enqueue(dummy, KIND_EMIT)
        snap = self.runtime.snapshot()
        self.assertIn("QUEUE_BACKLOG", snap["violations"])

    def test_enqueue_never_takes_pending_lock(self):
        source = inspect.getsource(self.runtime.enqueue_transition)
        self.assertNotIn("with self._pending_lock", source)
        self.assertNotIn("with self._lock", source)


class TestP1SyncDrain(unittest.TestCase):
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

    def _make_alarm(self, name: str, tag_name: str = "FI_P1"):
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
            alarm_setpoint=FloatType(10.0),
            alarm_on_delay=FloatType(0.0),
            alarm_off_delay=FloatType(0.0),
            identifier=f"id-{name}"[:16],
        )
        alarm.enable_delay_wakeups = False
        self.mgr._alarms[alarm.identifier] = alarm
        self.mgr._index_alarm(alarm)
        return alarm, tag

    def test_t93_dead_worker_flag_false_does_not_drain(self):
        alarm, tag = self._make_alarm("p1_t93")
        with patch.dict(os.environ, {"AUTOMATION_ENV": "test", "ALARM_SYNC_DRAIN": "false"}):
            self.assertFalse(AlarmConfig.is_sync_drain_allowed())
            before = self.runtime.queue_depth()
            alarm.check_condition(99.0, datetime.now(timezone.utc))
            self.assertGreater(self.runtime.queue_depth(), before)
            self.assertEqual(alarm.current_state.value.lower(), "normal")

    def test_t96_sync_drain_in_test_env(self):
        alarm, tag = self._make_alarm("p1_t96", tag_name="FI_P1B")
        with patch.dict(os.environ, {"AUTOMATION_ENV": "test", "ALARM_SYNC_DRAIN": "true"}):
            self.assertTrue(AlarmConfig.is_sync_drain_allowed())
            alarm.check_condition(99.0, datetime.now(timezone.utc))
        self.assertEqual(self.runtime.queue_depth(), 0)
        self.assertEqual(alarm.current_state.value.lower(), "unack_alarm")

    def test_t97_sync_drain_ignored_in_production(self):
        alarm, tag = self._make_alarm("p1_t97", tag_name="FI_P1C")
        with patch.dict(os.environ, {"AUTOMATION_ENV": "production", "ALARM_SYNC_DRAIN": "true"}):
            self.assertFalse(AlarmConfig.is_sync_drain_allowed())
            alarm.check_condition(99.0, datetime.now(timezone.utc))
            self.assertGreater(self.runtime.queue_depth(), 0)
            self.assertEqual(alarm.current_state.value.lower(), "normal")

    def test_ca_p1_3_1_production_always_false(self):
        with patch.dict(os.environ, {"AUTOMATION_ENV": "production", "ALARM_SYNC_DRAIN": "true"}):
            self.assertFalse(AlarmConfig.is_sync_drain_allowed())


class TestP1PaginationAndSocket(unittest.TestCase):
    def test_t98_catalog_page_size_clamped_to_50(self):
        self.assertEqual(clamp_catalog_page_size(100), 50)
        self.assertEqual(clamp_catalog_page_size(20), 20)

    def test_t99_history_page_size_clamped_to_100(self):
        self.assertEqual(clamp_history_page_size(500), 100)
        self.assertEqual(clamp_history_page_size(80), 80)

    def test_t100_socket_payload_under_2kb(self):
        runtime = reset_alarm_runtime_for_tests()
        try:
            cvt = CVTEngine()
            cvt.set_tag(
                name="FI_SOCK",
                variable="Temperature",
                unit="C",
                data_type="FLOAT",
                description="FI_SOCK",
            )
            tag = cvt.get_tag_by_name(name="FI_SOCK")
            from automation.alarms import Alarm

            alarm = Alarm(
                name="LDS.LEAK.HIGH",
                tag=tag,
                alarm_type=StringType("HIGH"),
                alarm_setpoint=FloatType(42.0),
                alarm_on_delay=FloatType(0.0),
                alarm_off_delay=FloatType(0.0),
                identifier="sock-alarm-01",
            )
            payload = alarm.serialize_socket()
            raw = json.dumps(payload).encode("utf-8")
            self.assertLessEqual(len(raw), 2048, f"on.alarm payload {len(raw)} B")
        finally:
            runtime.stop_worker()

    def test_maxlen_is_sacred(self):
        runtime = reset_alarm_runtime_for_tests()
        try:
            self.assertEqual(runtime._pending_transitions.maxlen, 100_000)
        finally:
            runtime.stop_worker()
