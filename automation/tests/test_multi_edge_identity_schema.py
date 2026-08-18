import os
import unittest
from unittest.mock import patch

from peewee import SqliteDatabase

from ..dbmodels import (
    AlarmSummary,
    Alarms,
    Events,
    Logs,
    Machines,
    Nodes,
    OPCUA,
    Tags,
    TagValue,
    proxy,
)
from ..managers.db import DBManager
from ..node_scope import NodeIdentityError, NodeScope
from ..utils.db_connections import historian_application_name


class TestNodeScope(unittest.TestCase):
    def test_multi_edge_is_enabled_by_default_and_identity_is_required(self):
        scope = NodeScope.from_env({})
        self.assertTrue(scope.multi_edge_enabled)
        with self.assertRaises(NodeIdentityError):
            scope.validate_for_acquisition()

    def test_area_uses_segment_only_as_compatibility_fallback(self):
        fallback = NodeScope.from_env(
            {"AUTOMATION_NODE_ID": "edge-1", "AUTOMATION_SEGMENT": "Linea1"}
        )
        self.assertEqual(fallback.area, "Linea1")
        self.assertTrue(fallback.area_from_segment)
        fallback.validate_for_acquisition()

        explicit = NodeScope.from_env(
            {
                "AUTOMATION_NODE_ID": "edge-1",
                "AUTOMATION_AREA": "AreaNueva",
                "AUTOMATION_SEGMENT": "AreaLegacy",
            }
        )
        self.assertEqual(explicit.area, "AreaNueva")
        self.assertFalse(explicit.area_from_segment)

    def test_disabled_mode_does_not_require_identity(self):
        scope = NodeScope.from_env({"AUTOMATION_MULTI_EDGE_ENABLED": "false"})
        self.assertIs(scope.validate_for_acquisition(), scope)

    def test_ownership_requires_matching_node_and_area(self):
        scope = NodeScope.from_env(
            {"AUTOMATION_NODE_ID": "edge-1", "AUTOMATION_AREA": "Linea1"}
        )
        owned = type("Tag", (), {"owner_node": "edge-1", "area": "Linea1"})()
        inconsistent = type("Tag", (), {"owner_node": "edge-1", "area": "Otra"})()
        legacy = type("Tag", (), {"owner_node": None, "area": "Linea1"})()
        foreign = type("Tag", (), {"owner_node": "edge-2", "area": "Linea1"})()
        self.assertTrue(scope.owns_tag(owned))
        self.assertFalse(scope.owns_tag(inconsistent))
        self.assertFalse(scope.owns_tag(legacy))
        self.assertFalse(scope.owns_tag(foreign))


class TestApplicationName(unittest.TestCase):
    def test_contains_node_and_role(self):
        with patch.dict(
            os.environ,
            {
                "AUTOMATION_MULTI_EDGE_ENABLED": "true",
                "AUTOMATION_NODE_ID": "edge-1",
            },
            clear=False,
        ):
            self.assertEqual(
                historian_application_name("LoggerWorker"),
                "PyAutomationIO:edge-1:LoggerWorker",
            )

    def test_long_name_is_deterministically_truncated(self):
        with patch.dict(
            os.environ,
            {
                "AUTOMATION_MULTI_EDGE_ENABLED": "true",
                "AUTOMATION_NODE_ID": "edge-" + ("x" * 64),
            },
            clear=False,
        ):
            first = historian_application_name("role-" + ("y" * 80))
            second = historian_application_name("role-" + ("y" * 80))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 63)


class TestMultiEdgeSchema(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables([Nodes, OPCUA])

    def tearDown(self):
        self.db.close()

    def test_runtime_models_expose_specified_scope_columns_and_indexes(self):
        expected = {
            Tags: ("area", "owner_node"),
            OPCUA: ("owner_node",),
            Machines: ("area",),
            Alarms: ("area",),
            TagValue: ("area",),
            AlarmSummary: ("area",),
            Events: ("area",),
            Logs: ("area",),
        }
        for model, fields in expected.items():
            for field_name in fields:
                field = model._meta.fields[field_name]
                self.assertTrue(field.index, f"{model.__name__}.{field_name}")

        self.assertIn((("area", "timestamp"), False), TagValue._meta.indexes)

    def test_node_registration_is_idempotent_and_preserves_created_at(self):
        first = Nodes.register(
            "edge-1",
            "Linea1",
            site="Norte",
            hostname="host-a",
            version="1.0",
        )
        created_at = first.created_at
        second = Nodes.register(
            "edge-1",
            "Linea1",
            site="Norte",
            hostname="host-b",
            version="1.1",
        )
        self.assertEqual(Nodes.select().count(), 1)
        self.assertEqual(second.hostname, "host-b")
        self.assertEqual(second.version, "1.1")
        self.assertEqual(second.created_at, created_at)
        with self.assertRaises(ValueError):
            Nodes.register("edge-1", "OtraArea")

    def test_model_and_manager_queries_are_scoped(self):
        OPCUA.create("a", "127.0.0.1", 4840, owner_node="edge-a")
        OPCUA.create("b", "127.0.0.2", 4840, owner_node="edge-b")

        self.assertEqual(
            [row.client_name for row in OPCUA.scoped(owner_node="edge-a")],
            ["a"],
        )
        manager = DBManager()
        self.assertEqual(
            [row.client_name for row in manager.scoped_query(OPCUA, owner_node="edge-b")],
            ["b"],
        )


if __name__ == "__main__":
    unittest.main()
