"""Rewrite dynamic-expose tests against the enqueue contract."""

import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.modules.opcua.filters import filter_opcua_server_attrs
from automation.state_machine import OPCUAServer


class TestOpcuaServerAttrFilters(unittest.TestCase):
    def test_filter_by_name_is_case_insensitive(self):
        attrs = [
            {"name": "CVT.Site.Area.PT-101", "namespace": "ns=2;i=1", "access_level": "Read"},
            {"name": "CVT.Site.Area.TT-202", "namespace": "ns=2;i=2", "access_level": "Read"},
        ]
        matched = filter_opcua_server_attrs(attrs, name="pt-101")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "CVT.Site.Area.PT-101")

    def test_filter_by_namespace(self):
        attrs = [
            {"name": "CVT.TagA", "namespace": "ns=2;s=abc", "access_level": "Read"},
            {"name": "CVT.TagB", "namespace": "ns=2;s=xyz", "access_level": "Read"},
        ]
        matched = filter_opcua_server_attrs(attrs, name="xyz")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "CVT.TagB")

    def test_empty_filter_returns_all(self):
        attrs = [{"name": "CVT.TagA", "namespace": "ns=2;i=1", "access_level": "Read"}]
        self.assertEqual(filter_opcua_server_attrs(attrs, name=""), attrs)

    def test_server_view_reads_the_listing(self):
        from automation.core import PyAutomation

        rows = [{
            "name": "Process.DI_02",
            "namespace": "ns=2;s=t:linea1:di_02",
            "access_level": 1,
            "access_level_label": "Read",
            "user_access_level": 1,
            "access_restrictions": 0,
        }]
        app = object.__new__(PyAutomation)
        app.get_machine = lambda name: SimpleNamespace(list_attrs=lambda: rows)
        self.assertEqual(app.get_opcua_server_attrs(), rows)
        self.assertEqual(app.get_opcua_server_attrs(name="di_02"), rows)
        self.assertEqual(app.get_opcua_server_attrs(name="missing"), [])


class TestOpcuaServerDynamicExpose(unittest.TestCase):
    def _server_stub(self) -> OPCUAServer:
        server = object.__new__(OPCUAServer)
        server._opcua_ready = False
        server._expose_queue = deque(maxlen=10_000)
        server._expose_seen = set()
        server._node_id_cache = {}
        server.cvt = SimpleNamespace(get_tag_by_name=lambda **_kwargs: None)
        server.metrics = SimpleNamespace(note_queue=lambda _n: None, expose_failures=0)
        return server

    def test_expose_cvt_tag_registers_when_ready(self):
        server = self._server_stub()
        server._opcua_ready = True
        tag = MagicMock()
        tag.name = "PT-101"
        with patch("automation.opcua_server.facade.register_tag", return_value=True) as register:
            registered = server.expose_cvt_tag(tag)
        self.assertTrue(registered)
        register.assert_called_once_with(server, tag)

    def test_expose_cvt_tag_queues_until_server_ready(self):
        server = self._server_stub()
        tag = MagicMock()
        tag.name = "Supe.Linea2.TI_02"
        registered = server.expose_cvt_tag(tag)
        self.assertFalse(registered)
        self.assertIn(("t", "Supe.Linea2.TI_02"), list(server._expose_queue))

    def test_core_expose_enqueues_on_opcua_server_machine(self):
        from automation import PyAutomation

        app = PyAutomation()
        tag = MagicMock()
        tag.name = "PT-101"
        machine = MagicMock()
        with patch.object(app, "get_machine", return_value=machine), patch.object(
            app.cvt, "get_tag_by_name", return_value=None
        ):
            app.expose_cvt_tag_on_opcua_server(tag)
        machine.enqueue_expose.assert_called_once_with("t", "PT-101")

    def test_definition_change_dirties_the_value_and_reenqueues_the_node(self):
        from automation.opcua_server.runtime import publish_tag_definition

        tag = SimpleNamespace(get_dead_band=lambda: 1.5)
        server = SimpleNamespace(
            enqueue_expose=MagicMock(),
            _dirty_tags=set(),
            _dead_bands={},
            _last_touch={},
            _expose_seen=set(),
            runner=None,
            cvt=SimpleNamespace(get_tag_by_name=lambda **_kwargs: tag),
        )
        publish_tag_definition(server, "Supe.Linea1.PI_01")
        server.enqueue_expose.assert_called_once_with("t", "Supe.Linea1.PI_01")
        self.assertIn("Supe.Linea1.PI_01", server._dirty_tags)
        self.assertEqual(server._dead_bands["Supe.Linea1.PI_01"], 1.5)
