"""Tick allocations. Push to UA is mocked so the budget covers the scheduler."""

import tracemalloc
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from automation.opcua_server.dirty.per_tag import PerTagDirtyTracker
from automation.opcua_server.metrics import OpcUaServerMetrics
from automation.opcua_server.runtime import process_one_tick


def _server(k: int):
    dirty = {f"tag_{i}" for i in range(k)}
    server = SimpleNamespace(
        _opcua_ready=True,
        _expose_queue=deque(maxlen=10),
        _expose_seen=set(),
        _dirty_tags=dirty,
        _dirty_alarms=set(),
        _dirty_engines=set(),
        _tick_counter=1,
        _watch_order=[],
        _watch_index=0,
        _last_touch={},
        _drain_scratch=[None] * 1000,
        metrics=OpcUaServerMetrics(),
        cvt=SimpleNamespace(get_tag_by_name=lambda name: None),
        publisher=None,
    )
    server.tag_tracker = PerTagDirtyTracker({}, dirty)
    server.alarm_tracker = PerTagDirtyTracker({}, server._dirty_alarms)
    server.engine_tracker = PerTagDirtyTracker({}, server._dirty_engines)
    return server


class TestTickAllocations(unittest.TestCase):
    def _delta(self, k: int) -> int:
        server = _server(k)
        process_one_tick(server)
        server._dirty_tags.update(f"tag_{i}" for i in range(k))
        tracemalloc.start()
        before = tracemalloc.take_snapshot()
        process_one_tick(server)
        after = tracemalloc.take_snapshot()
        tracemalloc.stop()
        return sum(stat.size_diff for stat in after.compare_to(before, "lineno") if stat.size_diff > 0)

    def test_k20_under_one_kilobyte(self):
        self.assertLess(self._delta(20), 1024)

    def test_k200_under_four_kilobytes(self):
        self.assertLess(self._delta(200), 4096)

    def test_runtime_has_no_sorted_call(self):
        source = Path(__file__).resolve().parents[1].joinpath("runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("sorted(", source)

    def test_one_timestamp_helper(self):
        source = Path(__file__).resolve().parents[1].joinpath("runtime.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("datetime.now"), 1)
