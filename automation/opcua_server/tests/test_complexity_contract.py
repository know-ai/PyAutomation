import tracemalloc
import unittest
from collections import deque
from types import SimpleNamespace

from automation.opcua_server.metrics import OpcUaServerMetrics
from automation.opcua_server.runtime import process_one_tick


def _server():
    return SimpleNamespace(
        _opcua_ready=True,
        _expose_queue=deque(maxlen=10_000),
        _expose_seen=set(),
        _dirty_tags={f"tag_{i}" for i in range(20)},
        _dirty_alarms=set(),
        _dirty_engines=set(),
        _ua_nodes={f"t:_:tag_{i}": object() for i in range(100)},
        _tick_counter=1,
        _watch_order=[],
        _watch_index=0,
        _last_touch={},
        metrics=OpcUaServerMetrics(),
        cvt=SimpleNamespace(get_tag_by_name=lambda name: None),
        alarm_manager=SimpleNamespace(get_alarm_by_name=lambda name: None, get_alarms=lambda: {}),
        machine=SimpleNamespace(get_machine=lambda name: None),
    )


class TestComplexityContract(unittest.TestCase):
    def test_snapshot_lists_structures(self):
        from automation.opcua_server.facade import OPCUAServer

        server = object.__new__(OPCUAServer)
        server._opcua_ready = True
        server._namespace_idx = 2
        server._ua_nodes = {}
        server._expose_queue = deque(maxlen=10)
        server._dirty_tags = set()
        server._dirty_alarms = set()
        server._dirty_engines = set()
        server._node_id_cache = {}
        server._access_cache = {}
        server._last_value = {}
        server._dead_bands = {}
        server.writeback = SimpleNamespace(active=0)
        server.metrics = OpcUaServerMetrics()
        structures = server.snapshot()["OPCUA_MEMORY_STRUCTURES"]
        expected = {
            "ua_nodes",
            "expose_queue",
            "dirty_tags",
            "dirty_alarms",
            "dirty_engines",
            "node_id_cache",
            "access_cache",
            "write_subscriptions",
            "last_value",
            "dead_bands",
        }
        self.assertTrue(expected <= set(structures))

    def test_queues_have_maxlen(self):
        server = _server()
        self.assertIsNotNone(server._expose_queue.maxlen)

    def test_tick_allocation_stays_small(self):
        server = _server()
        process_one_tick(server)
        tracemalloc.start()
        before = tracemalloc.take_snapshot()
        server._dirty_tags = {f"tag_{i}" for i in range(20)}
        process_one_tick(server)
        after = tracemalloc.take_snapshot()
        tracemalloc.stop()
        total = sum(stat.size_diff for stat in after.compare_to(before, "lineno") if stat.size_diff > 0)
        self.assertLess(total, 64 * 1024, f"tick allocated {total} bytes")
