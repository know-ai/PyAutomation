"""The field client follows whatever hierarchical tree a server exposes."""

import asyncio
import unittest
from types import SimpleNamespace

from asyncua import ua

from automation.opcua.asyncua_client.handlers import _walk


def _ref(name: str, namespace: int = 2):
    return SimpleNamespace(
        NodeId=ua.NodeId(name, namespace),
        DisplayName=SimpleNamespace(Text=name),
        BrowseName=SimpleNamespace(Name=name),
        NodeClass=SimpleNamespace(name="Object"),
        ReferenceTypeId=SimpleNamespace(Identifier=ua.ObjectIds.Organizes),
    )


class _Client:
    def __init__(self) -> None:
        self.seen = []
        self.uaclient = SimpleNamespace(browse=self._browse, browse_next=self._browse_next)

    def get_node(self, node_id):
        return SimpleNamespace(nodeid=ua.NodeId.from_string(str(node_id)))

    async def _browse(self, parameters):
        results = []
        for desc in parameters.NodesToBrowse:
            self.seen.append(desc.ReferenceTypeId.Identifier)
            references = []
            if desc.NodeId.NamespaceIndex == 0 and desc.NodeId.Identifier == 85:
                references = [_ref("Server", 0), _ref("Line1"), _ref("MyObjects")]
            results.append(SimpleNamespace(References=references, ContinuationPoint=None))
        return results

    async def _browse_next(self, _parameters):
        return []


class TestGenericServerBrowse(unittest.TestCase):
    def test_keeps_every_vendor_folder_under_objects(self):
        client = _Client()
        children = asyncio.run(_walk(client, "ns=0;i=85", 0, 100, False, {"n": 0}, set()))
        titles = [child["title"] for child in children]
        self.assertEqual(titles, ["Server", "Line1", "MyObjects"])
        self.assertEqual(client.seen[0], ua.ObjectIds.HierarchicalReferences)
        self.assertEqual(children[1]["key"], "ns=2;s=Line1")


class TestPolledVariableAttributes(unittest.TestCase):
    def test_integer_node_class_still_exposes_value_time_and_status(self):
        from datetime import datetime, timezone

        from automation.opcua.asyncua_client.handlers import _ATTRS, _attr_dict

        stamp = datetime(2026, 9, 23, 20, 25, tzinfo=timezone.utc)

        def sample(value, status=None, source=None):
            return SimpleNamespace(
                Value=SimpleNamespace(Value=value),
                StatusCode=status,
                SourceTimestamp=source,
            )

        by_attr = {
            ua.AttributeIds.NodeClass: sample(int(ua.NodeClass.Variable)),
            ua.AttributeIds.BrowseName: sample(SimpleNamespace(Name="Flow")),
            ua.AttributeIds.DisplayName: sample(SimpleNamespace(Text="Flow")),
            ua.AttributeIds.DataType: sample(ua.NodeId(ua.ObjectIds.Double, 0)),
            ua.AttributeIds.AccessLevel: sample(1),
            ua.AttributeIds.UserAccessLevel: sample(1),
            ua.AttributeIds.Description: sample(SimpleNamespace(Text="")),
            ua.AttributeIds.Value: sample(12.5, ua.StatusCode(ua.StatusCodes.Good), stamp),
            ua.AttributeIds.ArrayDimensions: sample(None),
            ua.AttributeIds.ValueRank: sample(-1),
        }
        payload = _attr_dict("ns=2;s=Flow", [by_attr[attr] for attr in _ATTRS])
        self.assertEqual(payload["NodeClass"], "Variable")
        self.assertEqual(payload["Value"], 12.5)
        self.assertEqual(payload["StatusCode"], "Good")
        self.assertEqual(payload["SourceTimestamp"], stamp.isoformat())
        self.assertEqual(payload["Namespace"], "ns=2;s=Flow")


class _Results:
    def __init__(self) -> None:
        self.items = []

    def put(self, item) -> None:
        self.items.append(item)


class _DeadSession:
    def __init__(self, state) -> None:
        self.uaclient = SimpleNamespace(state=state, browse=self._browse)
        self.connects = 0

    async def connect(self) -> None:
        self.connects += 1
        from asyncua.client.ua_client import UaClientState

        self.uaclient.state = UaClientState.CONNECTED

    def get_node(self, node_id):
        return SimpleNamespace(nodeid=ua.NodeId.from_string(str(node_id)))

    async def _browse(self, parameters):
        return [SimpleNamespace(References=[], ContinuationPoint=None) for _ in parameters.NodesToBrowse]


class TestBrowseOnDeadSession(unittest.TestCase):
    def test_mapping_browse_reconnects_once(self):
        from asyncua.client.ua_client import UaClientState

        from automation.opcua.asyncua_client.commands import Browse
        from automation.opcua.asyncua_client.handlers import LoopContext, _browse

        flags = []
        ctx = LoopContext(_Results(), lambda name, connected: flags.append((name, connected)))
        dead = _DeadSession(UaClientState.DISCONNECTED)
        ctx.sessions["PLC"] = dead
        command = Browse("PLC", "ns=0;i=85", 1, "corr", mode="variables")
        asyncio.run(_browse(ctx, command))
        self.assertEqual(dead.connects, 1)
        self.assertEqual(flags, [("PLC", True)])
        self.assertTrue(ctx.results.items[0].ok)
        self.assertEqual(ctx.results.items[0].payload, [])

    def test_read_keeps_connected_while_asyncua_reconnects(self):
        from asyncua.client.ua_client import UaClientState

        from automation.opcua.asyncua_client.commands import ReadBatch
        from automation.opcua.asyncua_client.handlers import LoopContext, _read_batch

        flags = []
        ctx = LoopContext(_Results(), lambda name, connected: flags.append((name, connected)))
        ctx.sessions["PLC"] = _DeadSession(UaClientState.RECONNECTING)
        asyncio.run(_read_batch(ctx, ReadBatch("PLC", ("ns=2;s=FI_01",), "corr")))
        self.assertEqual(flags, [])
        self.assertIsNone(ctx.results.items[0].data_values)


class TestStructureText(unittest.TestCase):
    def test_engineering_units_show_display_name_text(self):
        from automation.modules.opcua.resources.clients import extract_primitive_value

        info = ua.EUInformation()
        info.DisplayName = ua.LocalizedText("kg/lt")
        self.assertEqual(extract_primitive_value(info), "kg/lt")

    def test_range_shows_its_ends(self):
        from automation.modules.opcua.resources.clients import extract_primitive_value

        span = ua.Range()
        span.Low = 0.0
        span.High = 12.5
        self.assertEqual(extract_primitive_value(span), "0.0 .. 12.5")
