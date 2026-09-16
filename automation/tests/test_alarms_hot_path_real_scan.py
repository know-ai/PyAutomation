# -*- coding: utf-8 -*-
"""GATE-35 hot path while polling the live OPC simulator (100 ms)."""
from __future__ import annotations

import time
import unittest

from opcua import Client

from automation.alarms.runtime import reset_alarm_runtime_for_tests
from automation.managers.alarms import AlarmManager
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine


def _pct(samples, p):
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))]


class TestHotPathRealScan(unittest.TestCase):
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

    def _setup_alarm(self):
        from automation.alarms import Alarm

        self.cvt.set_tag(
            name="FI_01",
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description="FI_01",
        )
        tag = self.cvt.get_tag_by_name(name="FI_01")
        alarm = Alarm(
            name="ALM.FI_01.HIGH",
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(1e9),
            alarm_on_delay=FloatType(0.0),
            alarm_off_delay=FloatType(0.0),
            identifier="hotpathfi01",
        )
        alarm.enable_delay_wakeups = False
        self.mgr._alarms[alarm.identifier] = alarm
        self.mgr._index_alarm(alarm)
        return tag

    def _measure(self, interval_s: float, n: int) -> dict:
        tag = self._setup_alarm()
        client = Client("opc.tcp://127.0.0.1:4840")
        client.connect()
        node = client.get_node("ns=2;i=2")
        samples = []
        try:
            for _ in range(n):
                pv = node.get_value()
                t0 = time.perf_counter_ns()
                self.mgr.on_tag_value(tag, pv)
                samples.append((time.perf_counter_ns() - t0) / 1000.0)
                time.sleep(interval_s)
        finally:
            client.disconnect()
        p50, p99, p999 = _pct(samples, 0.5), _pct(samples, 0.99), _pct(samples, 0.999)
        label = f"{int(interval_s * 1000)}ms"
        print(
            f"{label} scan n={len(samples)} p50={p50:.1f} p99={p99:.1f} "
            f"p999={p999:.1f} max={max(samples):.1f} µs"
        )
        return {"n": len(samples), "p50": p50, "p99": p99, "p999": p999, "max": max(samples)}

    def test_hot_path_100ms_scan(self):
        result = self._measure(0.1, 50)
        self.assertGreater(result["n"], 40)
        self.assertLessEqual(result["p99"], 250.0)  # CPython CI; planta 50µs = T-64b
        self.assertLessEqual(result["p999"], 400.0)

    def test_hot_path_500ms_scan(self):
        result = self._measure(0.5, 10)
        self.assertGreater(result["n"], 8)
        self.assertLessEqual(result["p99"], 250.0)
        self.assertLessEqual(result["p999"], 400.0)

    def test_hot_path_1000ms_scan(self):
        result = self._measure(1.0, 8)
        self.assertGreater(result["n"], 6)
        self.assertLessEqual(result["p99"], 250.0)
        self.assertLessEqual(result["p999"], 400.0)
