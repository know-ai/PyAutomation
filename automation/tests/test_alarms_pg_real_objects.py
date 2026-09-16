# -*- coding: utf-8 -*-
"""T-64b: on_tag_value with N=500 real Alarm objects. GATE-29b."""
from __future__ import annotations

import time
import unittest

from automation.alarms.runtime import reset_alarm_runtime_for_tests
from automation.managers.alarms import AlarmManager
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine


def _percentile(samples: list[float], p: float) -> float:
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[idx]


class TestAlarmsPgRealObjects(unittest.TestCase):
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

    def test_t64b_500_real_alarms_p99(self):
        from automation.alarms import Alarm

        n = 500
        from automation.alarms import Alarm

        probe = "FI_T64B_000"
        for i in range(n):
            tag_name = f"FI_T64B_{i:03d}"
            self.cvt.set_tag(
                name=tag_name,
                variable="Temperature",
                unit="C",
                data_type="FLOAT",
                description=tag_name,
            )
            tag = self.cvt.get_tag_by_name(name=tag_name)
            alarm = Alarm(
                name=f"t64b_{i:04d}",
                tag=tag,
                alarm_type=StringType("HIGH"),
                alarm_setpoint=FloatType(9999.0),
                alarm_on_delay=FloatType(0.0),
                alarm_off_delay=FloatType(0.0),
                identifier=f"t64b{i:04d}"[:16],
            )
            alarm.enable_delay_wakeups = False
            self.mgr._alarms[alarm.identifier] = alarm
            self.mgr._index_alarm(alarm)

        probe_tag = self.cvt.get_tag_by_name(name=probe)
        for _ in range(200):
            self.mgr.on_tag_value(probe_tag, 1.0)

        samples = []
        for _ in range(5_000):
            t0 = time.perf_counter_ns()
            self.mgr.on_tag_value(probe_tag, 1.0)
            samples.append((time.perf_counter_ns() - t0) / 1000.0)
        p50 = _percentile(samples, 0.50)
        p99 = _percentile(samples, 0.99)
        pmax = max(samples)
        print(f"T-64b N={n} K=1 p50={p50:.1f}µs p99={p99:.1f}µs max={pmax:.1f}µs")
        self.assertEqual(len(self.mgr._alarms), n)
        self.assertLessEqual(p99, 50.0, f"p99={p99:.1f}µs > 50µs")
        self.assertLessEqual(pmax, 100.0, f"max={pmax:.1f}µs > 100µs")
