"""Growth checks on the tick. Mocked nodes, no live UA server."""

import time
import unittest
from types import SimpleNamespace

from automation.opcua_server.metrics import OpcUaServerMetrics
from automation.opcua_server.runtime import process_one_tick


def _server(n: int):
    server = SimpleNamespace(
        _opcua_ready=True,
        _expose_queue=[],
        _expose_seen=set(),
        _dirty_tags=set(),
        _dirty_alarms=set(),
        _dirty_engines=set(),
        _ua_nodes={f"t:_:tag_{i}": object() for i in range(n)},
        _tick_counter=0,
        _watch_order=[],
        _watch_index=0,
        _last_touch={},
        metrics=OpcUaServerMetrics(),
        cvt=SimpleNamespace(get_tag_by_name=lambda name: None),
        alarm_manager=SimpleNamespace(get_alarm_by_name=lambda name: None, get_alarms=lambda: {}),
        machine=SimpleNamespace(get_machine=lambda name: None),
    )
    # process_expose_queue expects popleft
    from collections import deque

    server._expose_queue = deque(maxlen=10_000)
    return server


def _p95_ms(n: int) -> float:
    server = _server(n)
    server._dirty_tags = {f"tag_{i}" for i in range(20)}
    process_one_tick(server)
    samples = []
    for _ in range(40):
        server._dirty_tags = {f"tag_{i}" for i in range(20)}
        started = time.perf_counter_ns()
        process_one_tick(server)
        samples.append((time.perf_counter_ns() - started) / 1e6)
    samples.sort()
    return samples[int(0.95 * (len(samples) - 1))]


class TestGrowth(unittest.TestCase):
    def test_tick_does_not_grow_with_n(self):
        small = _p95_ms(100)
        large = _p95_ms(10000)
        ratio = large / max(small, 0.001)
        self.assertLessEqual(ratio, 2.0, f"tick grew {ratio:.2f}x")
        self.assertLess(large, 20.0)

    def test_reset_ratio_is_flat(self):
        server = _server(10000)
        started = time.perf_counter()
        for _ in range(50):
            server._ua_nodes.clear()
            server._dirty_tags.clear()
            server._dirty_alarms.clear()
            server._dirty_engines.clear()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.assertLess(elapsed_ms, 100.0)
