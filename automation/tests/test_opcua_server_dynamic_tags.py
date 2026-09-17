import unittest
from unittest.mock import MagicMock, patch

from automation.modules.opcua.filters import filter_opcua_server_attrs
from automation.state_machine import OPCUAServer


class TestOpcuaServerAttrFilters(unittest.TestCase):
    def test_filter_by_name_is_case_insensitive(self):
        attrs = [
            {"name": "CVT.Site.Area.PT-101", "namespace": "ns=2;i=1", "access_type": "Read"},
            {"name": "CVT.Site.Area.TT-202", "namespace": "ns=2;i=2", "access_type": "Read"},
        ]
        matched = filter_opcua_server_attrs(attrs, name="pt-101")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "CVT.Site.Area.PT-101")

    def test_filter_by_namespace(self):
        attrs = [
            {"name": "CVT.TagA", "namespace": "ns=2;s=abc", "access_type": "Read"},
            {"name": "CVT.TagB", "namespace": "ns=2;s=xyz", "access_type": "Read"},
        ]
        matched = filter_opcua_server_attrs(attrs, name="xyz")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "CVT.TagB")

    def test_empty_filter_returns_all(self):
        attrs = [{"name": "CVT.TagA", "namespace": "ns=2;i=1", "access_type": "Read"}]
        self.assertEqual(filter_opcua_server_attrs(attrs, name=""), attrs)


class TestOpcuaServerDynamicExpose(unittest.TestCase):
    def _server_stub(self) -> OPCUAServer:
        server = object.__new__(OPCUAServer)
        server.cvt = MagicMock()
        server.my_folders = {"CVT": MagicMock()}
        server.idx = 2
        server.objects = MagicMock()
        server.server = MagicMock()
        server._opcua_ready = True
        return server

    def test_expose_cvt_tag_registers_missing_node(self):
        server = self._server_stub()
        tag = MagicMock()
        tag.serialize.return_value = {
            "name": "PT-101",
            "segment": "",
            "display_unit": "bar",
            "data_type": "float",
            "description": "Pressure",
            "value": 12.5,
        }
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch.object(
            server, "_register_cvt_tag", return_value=True
        ) as register, patch.object(server, "_push_cvt_tag_value") as push_value:
            registered = server.expose_cvt_tag(tag)
        self.assertTrue(registered)
        register.assert_called_once_with(tag)
        push_value.assert_called_once_with(tag)

    def test_expose_cvt_tag_noop_until_server_ready(self):
        server = self._server_stub()
        server._opcua_ready = False
        tag = MagicMock()
        with patch.object(server, "_register_cvt_tag") as register:
            registered = server.expose_cvt_tag(tag)
        self.assertFalse(registered)
        register.assert_not_called()

    def test_core_expose_delegates_to_opcua_server_machine(self):
        from automation import PyAutomation

        app = PyAutomation()
        tag = MagicMock()
        tag.name = "PT-101"
        machine = MagicMock()
        with patch.object(app, "get_machine", return_value=machine):
            app.expose_cvt_tag_on_opcua_server(tag)
        machine.expose_cvt_tag.assert_called_once_with(tag)
