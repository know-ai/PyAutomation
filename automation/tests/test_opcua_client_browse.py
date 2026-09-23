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
