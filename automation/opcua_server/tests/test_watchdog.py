"""Watchdog fires on state entry and does not double-count."""

import time
import unittest
from types import SimpleNamespace

from automation.opcua_server.metrics import OpcUaServerMetrics
from automation.opcua_server.watchdog.supervisor import WatchdogSupervisor, bind_watchdog
from automation.state_machine import StateMachineCore


class TestWatchdog(unittest.TestCase):
    def _server(self):
        dirty = set()
        metrics = OpcUaServerMetrics()

        def mark_engine(name):
            if name and name != "OPCUAServer":
                dirty.add(name)

        engines = []
        server = SimpleNamespace(
            _dirty_engines=dirty,
            _dirty_tags=set(),
            _watch_order=[],
            _watch_index=0,
            _last_touch={},
            metrics=metrics,
            mark_engine=mark_engine,
            machine=SimpleNamespace(machine_manager=SimpleNamespace(get_machines=lambda: engines)),
        )
        server._engines = engines
        return server

    def test_transition_without_while_running(self):
        server = self._server()
        supervisor = WatchdogSupervisor(server)
        bind_watchdog(supervisor)

        class Child(StateMachineCore):
            def while_running(self):
                self.skipped_super = True

        machine = SimpleNamespace(name=SimpleNamespace(value="Pump"))
        StateMachineCore.on_enter_state(
            machine,
            source=SimpleNamespace(value="wait"),
            target=SimpleNamespace(value="run"),
        )
        self.assertIn("Pump", server._dirty_engines)
        self.assertEqual(server.metrics.engine_watchdog_recoveries, 1)
        StateMachineCore.on_enter_state(
            machine,
            source=SimpleNamespace(value="wait"),
            target=SimpleNamespace(value="run"),
        )
        self.assertEqual(server.metrics.engine_watchdog_recoveries, 1)
        self.assertEqual(len(server._dirty_engines), 1)

    def test_reconcile_recovers_an_engine_that_never_transitioned(self):
        server = self._server()
        supervisor = WatchdogSupervisor(server)
        motor = SimpleNamespace(name=SimpleNamespace(value="Motor"))
        server._engines.append((motor, None, None))
        supervisor.on_reconcile()
        self.assertIn("Motor", server._dirty_engines)
        self.assertGreaterEqual(server.metrics.engine_watchdog_recoveries, 1)
        before = server.metrics.engine_watchdog_recoveries
        supervisor.on_reconcile()
        self.assertEqual(server.metrics.engine_watchdog_recoveries, before)

    def test_notify_transition_stays_cheap(self):
        server = self._server()
        supervisor = WatchdogSupervisor(server)
        started = time.perf_counter()
        for _ in range(1000):
            supervisor.notify_transition("Pump", "wait", "run")
        per_call_us = (time.perf_counter() - started) * 1_000_000.0 / 1000.0
        self.assertLess(per_call_us, 50.0)

    def test_recovery_counter_is_in_the_snapshot(self):
        server = self._server()
        supervisor = WatchdogSupervisor(server)
        supervisor.notify_transition("Pump", "wait", "run")
        self.assertGreaterEqual(server.metrics.engine_watchdog_recoveries, 1)
        payload = server.metrics.as_dict(ready=True, namespace_idx=2, structures={})
        self.assertGreaterEqual(payload["OPCUA_ENGINE_WATCHDOG_RECOVERIES_TOTAL"], 1)
        self.assertIn("OPCUA_MEMORY_STRUCTURES", payload)
        self.assertIn("OPCUA_TAG_WATCHDOG_RECOVERIES_TOTAL", payload)
