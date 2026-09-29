import os
import unittest
from unittest.mock import patch

from automation.opcua_server.address_space import AddressSpaceBuilder
from automation.opcua_server.identity import make_node_id
from automation.opcua_server.runtime import watch_identity_env


class _Folder:
    def __init__(self, name="root"):
        self.name = name
        self.children = []

    def add_folder(self, _idx, name):
        child = _Folder(name)
        self.children.append(child)
        return child


class TestNodeIdStability(unittest.TestCase):
    def test_root_always_exists(self):
        objects = _Folder("Objects")
        builder = AddressSpaceBuilder(objects, 2)
        builder.build_tree("Supe", "Linea1")
        self.assertEqual(objects.children[0].name, "PyAutomationIO")

    def test_site_folder_is_always_default(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        builder.build_tree("Supe", "Linea1")
        root = objects.children[0]
        self.assertEqual({child.name for child in root.children}, {"Default", "Process", "Alarms", "Engines"})
        default = next(child for child in root.children if child.name == "Default")
        self.assertEqual({child.name for child in default.children}, {"Process", "Alarms"})

    def test_area_folder_is_not_created(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        builder.build_tree("Supe", "Linea1")
        root = objects.children[0]
        names = [child.name for child in root.children]
        self.assertNotIn("Linea1", names)
        self.assertNotIn("linea1", names)
        self.assertNotIn("Supe", names)
        self.assertNotIn("Global", names)

    def test_moving_tag_does_not_change_nodeid(self):
        identifier = make_node_id("t", "Linea1", "Supe.Linea1.FI_01")
        self.assertEqual(identifier, make_node_id("t", "Linea1", "Supe.Linea1.FI_01"))
        self.assertNotIn("Process", identifier)

    def test_changing_manufacturer_does_not_rename_tags(self):
        with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea1"}):
            identifier = make_node_id("t", "Linea1", "Supe.Linea1.FI_01")
            self.assertEqual(identifier, "fi_01")
        with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea1"}):
            self.assertEqual(identifier, make_node_id("t", "Linea1", "Supe.Linea1.FI_01"))

    def test_segment_argument_does_not_change_nodeids(self):
        self.assertEqual(
            make_node_id("t", "Linea1", "Supe.Linea1.FI_01"),
            make_node_id("t", "Linea2", "Supe.Linea1.FI_01"),
        )

    def test_manufacturer_and_segment_empty(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        builder.build_tree("", "")
        root = objects.children[0]
        self.assertIn("Default", {child.name for child in root.children})
        self.assertEqual({child.name for child in root.children}, {"Default", "Process", "Alarms", "Engines"})
        with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea1"}):
            self.assertEqual(make_node_id("t", None, "Supe.Linea1.FI_01"), "fi_01")
            self.assertEqual(make_node_id("t", None, "Linea1.SYS.PERF.SAF_QUEUE"), "sys.perf.saf_queue")

    def test_segment_change_is_audited_once(self):
        server = type("S", (), {})()
        with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea1"}):
            watch_identity_env(server)
        with patch("automation.opcua_server.runtime.audit_failure") as audited:
            with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea2"}):
                watch_identity_env(server)
                watch_identity_env(server)
        self.assertEqual(audited.call_count, 1)
        self.assertEqual(audited.call_args.args[0], "OPC UA segment changed")
