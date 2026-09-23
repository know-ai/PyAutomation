import unittest
from collections import deque
from unittest.mock import MagicMock

from automation.opcua_server.facade import OPCUAServer
from automation.opcua_server.writeback import WriteBackHandler


class TestLifecycle(unittest.TestCase):
    def test_reset_clears_structures(self):
        server = object.__new__(OPCUAServer)
        server.server = MagicMock()
        server.cvt = MagicMock()
        server.cvt.get_tag_by_name.return_value = None
        server.objects = object()
        server.builder = object()
        server._cvt_exposer = object()
        server._alarm_exposer = object()
        server._engine_exposer = object()
        server.writeback = WriteBackHandler()
        server._ua_nodes = {"t:_:a": 1}
        server._by_namespace = {"ns": 1}
        server._expose_queue = deque([("t", "a")], maxlen=10)
        server._expose_seen = {("t", "a")}
        server._dirty_tags = {"a"}
        server._dirty_alarms = {"b"}
        server._dirty_engines = {"c"}
        server._node_id_cache = {"a": "t:_:a"}
        server._access_cache = {"ns": "Read"}
        server._last_value = {"a": 1}
        server._dead_bands = {"a": 0}
        server._last_touch = {"a": 0}
        server._tag_observers = {}
        server._watch_order = ["a"]
        server._name_to_canonical = {}
        server._watch_index = 3
        server._tick_counter = 9
        server._opcua_ready = True
        server._opcua_endpoint_up = True
        server._opcua_space_loaded = True
        server._namespace_idx = 2
        server.metrics = MagicMock()
        server.publisher = None
        server._reset_structures()
        self.assertEqual(len(server._ua_nodes), 0)
        self.assertEqual(len(server._expose_queue), 0)
        self.assertEqual(len(server._dirty_tags), 0)
        self.assertEqual(len(server._access_cache), 0)
        self.assertFalse(server._opcua_ready)
        self.assertIsNone(server.server)
        from pathlib import Path
        facade = Path(__file__).resolve().parents[1] / "facade.py"
        self.assertLess(len(facade.read_text(encoding="utf-8").splitlines()), 200)

    def test_runner_keeps_the_expose_queue(self):
        from automation.opcua_server.runtime import process_expose_queue

        server = MagicMock()
        server.runner = object()
        server._expose_queue = deque([("t", "leak_volume")])
        self.assertEqual(process_expose_queue(server), 0)
        self.assertEqual(list(server._expose_queue), [("t", "leak_volume")])
