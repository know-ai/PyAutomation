"""IDirtyTracker contract, the per-tag implementation, and a substitute tracker."""

import time
import unittest
from collections import deque
from types import SimpleNamespace

from automation.opcua_server.dirty.per_tag import PerTagDirtyTracker
from automation.opcua_server.dirty.tracker import IDirtyTracker
from automation.opcua_server.metrics import OpcUaServerMetrics
from automation.opcua_server.runtime import process_one_tick


class _FakeTracker(IDirtyTracker):
    def __init__(self):
        self.drained = 0

    def mark(self, name, value):
        return

    def drain(self, limit=1000):
        self.drained += 1
        return ["substituted"]

    def attach(self, name, initial_value):
        return

    def detach(self, name):
        return


def _tick_server():
    return SimpleNamespace(
        _opcua_ready=True,
        _expose_queue=deque(maxlen=10),
        _expose_seen=set(),
        _dirty_tags=set(),
        _dirty_alarms=set(),
        _dirty_engines=set(),
        _tick_counter=0,
        _watch_order=[],
        _watch_index=0,
        _last_touch={},
        _drain_scratch=[None] * 1000,
        metrics=OpcUaServerMetrics(),
        cvt=SimpleNamespace(get_tag_by_name=lambda name: None),
        alarm_manager=SimpleNamespace(get_alarm_by_name=lambda name: None, get_alarms=lambda: {}),
        machine=SimpleNamespace(get_machine=lambda name: None),
    )


class TestDirtyTracker(unittest.TestCase):
    def test_runtime_does_not_import_the_concrete_tracker(self):
        from pathlib import Path

        import automation.opcua_server.runtime as runtime

        source = Path(runtime.__file__).read_text(encoding="utf-8")
        self.assertNotIn("PerTagDirtyTracker", source)

    def test_drain_clears_and_mark_respects_deadband(self):
        dirty = set()
        tracker = PerTagDirtyTracker({"a": 1.0}, dirty)
        tracker.mark("a", 0.0)
        tracker.mark("a", 0.2)
        self.assertEqual(dirty, {"a"})
        tracker.drain()
        self.assertEqual(dirty, set())
        tracker.mark("a", 0.4)
        self.assertEqual(dirty, set())
        tracker.mark("a", 2.0)
        self.assertEqual(dirty, {"a"})

    def test_mark_one_thousand_is_fast(self):
        tracker = PerTagDirtyTracker({}, set())
        started = time.perf_counter()
        for index in range(1000):
            tracker.mark(f"t{index}", float(index))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.assertLess(elapsed_ms, 10.0)

    def test_attach_and_detach_are_bounded(self):
        tracker = PerTagDirtyTracker({}, set())
        started = time.perf_counter()
        for index in range(1000):
            tracker.attach(f"t{index}", 0.0)
            tracker.detach(f"t{index}")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.assertLess(elapsed_ms, 20.0)

    def test_fake_tracker_is_used_by_the_tick(self):
        server = _tick_server()
        server.tag_tracker = _FakeTracker()
        server.alarm_tracker = _FakeTracker()
        server.engine_tracker = _FakeTracker()
        process_one_tick(server)
        self.assertEqual(server.tag_tracker.drained, 1)

    def test_async_expose_attaches_the_observer_and_marks_dirty(self):
        from automation.opcua_server.runtime import bind_exposed_tag

        attached = []

        class _Tag:
            name = "DI_02"

            def get_value(self):
                return 1.5

            def get_dead_band(self):
                return 0.0

            def attach(self, observer):
                attached.append(observer)
                observer._subject = self

        tag = _Tag()
        dirty = set()
        server = SimpleNamespace(
            _tag_observers={},
            _watch_order=[],
            _last_touch={},
            _dead_bands={},
            _dirty_tags=dirty,
            cvt=SimpleNamespace(get_tag_by_name=lambda name: tag if name == "DI_02" else None),
        )
        server.tag_tracker = PerTagDirtyTracker(server._dead_bands, dirty, server)
        bind_exposed_tag(server, "t", "DI_02")
        self.assertEqual(len(attached), 1)
        self.assertIn("DI_02", server._dirty_tags)
        bind_exposed_tag(server, "a", "alarm")
        self.assertEqual(len(attached), 1)
