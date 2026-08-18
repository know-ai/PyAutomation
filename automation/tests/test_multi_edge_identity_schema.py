import os
import json
import unittest
from datetime import datetime, timezone
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
from ..dbmodels.alarms import AlarmStates, AlarmTypes
from ..dbmodels.tags import DataTypes, Units, Variables
from ..dbmodels.users import Roles, Users
from ..managers.db import DBManager
from ..node_scope import NodeIdentityError, NodeScope
from ..utils.db_connections import historian_application_name


class TestNodeScope(unittest.TestCase):
    def test_multi_edge_is_enabled_by_default_and_identity_is_required(self):
        scope = NodeScope.from_env({})
        self.assertTrue(scope.multi_edge_enabled)
        with self.assertRaises(NodeIdentityError):
            scope.validate_for_acquisition()

    def test_segment_and_manufacturer_are_aliases_of_area_and_site(self):
        from_app_env = NodeScope.from_env(
            {
                "AUTOMATION_NODE_ID": "edge-1",
                "AUTOMATION_SEGMENT": "Linea1",
                "AUTOMATION_MANUFACTURER": "Test",
            }
        )
        self.assertEqual(from_app_env.area, "Linea1")
        self.assertEqual(from_app_env.site, "Test")
        self.assertTrue(from_app_env.area_from_segment)
        self.assertTrue(from_app_env.site_from_manufacturer)
        from_app_env.validate_for_acquisition()

        matching = NodeScope.from_env(
            {
                "AUTOMATION_NODE_ID": "edge-1",
                "AUTOMATION_AREA": "Linea1",
                "AUTOMATION_SEGMENT": "Linea1",
                "AUTOMATION_SITE": "Test",
                "AUTOMATION_MANUFACTURER": "Test",
            }
        )
        self.assertEqual(matching.area, "Linea1")
        self.assertEqual(matching.site, "Test")
        self.assertFalse(matching.area_from_segment)
        matching.validate_for_acquisition()

        leftover_site = NodeScope.from_env(
            {
                "AUTOMATION_NODE_ID": "edge-1",
                "AUTOMATION_SEGMENT": "Linea1",
                "AUTOMATION_SITE": "Norte",
                "AUTOMATION_MANUFACTURER": "Test",
            }
        )
        self.assertTrue(leftover_site.is_valid)
        self.assertEqual(leftover_site.site, "Test")
        leftover_site.validate_for_acquisition()

        conflict = NodeScope.from_env(
            {
                "AUTOMATION_NODE_ID": "edge-1",
                "AUTOMATION_AREA": "Linea1",
                "AUTOMATION_SEGMENT": "Linea2",
            }
        )
        self.assertFalse(conflict.is_valid)
        with self.assertRaises(NodeIdentityError):
            conflict.validate_for_acquisition()

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
        payload = second.serialize()
        self.assertEqual(payload["area"], "Linea1")
        self.assertIsInstance(payload["last_seen"], str)
        self.assertIsInstance(payload["created_at"], str)
        self.assertIsInstance(payload["updated_at"], str)
        json.dumps(payload)
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


class TestAlarmSummaryArea(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables(
            [
                Variables,
                Units,
                DataTypes,
                Tags,
                AlarmTypes,
                AlarmStates,
                Alarms,
                AlarmSummary,
                Roles,
                Users,
                Events,
                Logs,
            ]
        )
        Variables(name="Adimentional").save()
        Units(name="adim", unit="adim", variable_id=Variables.get(Variables.name == "Adimentional")).save()
        DataTypes(name="int").save()
        unit = Units.get(Units.name == "adim")
        Tags(
            identifier="tag-leak",
            name="Test.Linea1.LDS.leak",
            unit=unit,
            data_type=DataTypes.get(DataTypes.name == "int"),
            display_name="Test.Linea1.LDS.leak",
            display_unit=unit,
            description="",
            area="Linea1",
            owner_node="edge-linea1",
        ).save()
        AlarmTypes(name="BOOL").save()
        AlarmStates(
            name="Unacknowledged",
            mnemonic="UNACK",
            condition="Active",
            status="Unack",
        ).save()
        Alarms(
            identifier="alm-leak",
            name="alarm.Test.Linea1.LDS.leak",
            area="Linea1",
            tag=Tags.get(Tags.name == "Test.Linea1.LDS.leak"),
            trigger_type=AlarmTypes.get(AlarmTypes.name == "BOOL"),
            trigger_value=1,
            state=AlarmStates.get(AlarmStates.name == "Unacknowledged"),
        ).save()

    def tearDown(self):
        self.db.close()

    def test_summary_inherits_alarm_area_and_filter_hides_unscoped_rows(self):
        stamp = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
        inherited = AlarmSummary.create(
            name="alarm.Test.Linea1.LDS.leak",
            state="Unacknowledged",
            timestamp=stamp,
        )
        self.assertIsNotNone(inherited)
        self.assertEqual(inherited.area, "Linea1")

        orphan = AlarmSummary(
            alarm=Alarms.get(Alarms.name == "alarm.Test.Linea1.LDS.leak"),
            state=AlarmStates.get(AlarmStates.name == "Unacknowledged"),
            alarm_time=stamp,
            area=None,
        )
        orphan.save()
        AlarmSummary._backfill_area_from_alarm()
        orphan = AlarmSummary.get_by_id(orphan.id)
        self.assertEqual(orphan.area, "Linea1")
        self.assertEqual(
            AlarmSummary.select().where(AlarmSummary.area == "Linea1").count(),
            2,
        )
        self.assertEqual(
            AlarmSummary.select().where(AlarmSummary.area == "Linea2").count(),
            0,
        )

    def test_filter_by_is_plant_wide_unless_area_is_given(self):
        stamp = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
        unit = Units.get(Units.name == "adim")
        Tags(
            identifier="tag-leak-2",
            name="Test.Linea2.LDS.leak",
            unit=unit,
            data_type=DataTypes.get(DataTypes.name == "int"),
            display_name="Test.Linea2.LDS.leak",
            display_unit=unit,
            description="",
            area="Linea2",
            owner_node="edge-linea2",
        ).save()
        Alarms(
            identifier="alm-leak-2",
            name="alarm.Test.Linea2.LDS.leak",
            area="Linea2",
            tag=Tags.get(Tags.name == "Test.Linea2.LDS.leak"),
            trigger_type=AlarmTypes.get(AlarmTypes.name == "BOOL"),
            trigger_value=1,
            state=AlarmStates.get(AlarmStates.name == "Unacknowledged"),
        ).save()
        AlarmSummary.create(
            name="alarm.Test.Linea1.LDS.leak",
            state="Unacknowledged",
            timestamp=stamp,
        )
        AlarmSummary.create(
            name="alarm.Test.Linea2.LDS.leak",
            state="Unacknowledged",
            timestamp=stamp,
        )

        plant = AlarmSummary.filter_by(page=1, limit=20)
        self.assertEqual(
            {row["area"] for row in plant["data"]},
            {"Linea1", "Linea2"},
        )
        self.assertTrue(all("area" in row for row in plant["data"]))

        linea1 = AlarmSummary.filter_by(area="Linea1", page=1, limit=20)
        self.assertEqual(len(linea1["data"]), 1)
        self.assertEqual(linea1["data"][0]["area"], "Linea1")


class TestAlarmSummarySafCatalog(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables(
            [
                Variables,
                Units,
                DataTypes,
                Tags,
                AlarmTypes,
                AlarmStates,
                Alarms,
                AlarmSummary,
            ]
        )
        Variables(name="Adimentional").save()
        Units(name="adim", unit="adim", variable_id=Variables.get(Variables.name == "Adimentional")).save()
        DataTypes(name="int").save()
        unit = Units.get(Units.name == "adim")
        Tags(
            identifier="tag-leak",
            name="Test.Linea1.LDS.leak",
            unit=unit,
            data_type=DataTypes.get(DataTypes.name == "int"),
            display_name="Test.Linea1.LDS.leak",
            display_unit=unit,
            description="",
            area="Linea1",
            owner_node="edge-linea1",
        ).save()
        AlarmTypes(name="BOOL").save()
        AlarmStates(
            name="Unacknowledged",
            mnemonic="UNACK",
            condition="Active",
            status="Unack",
        ).save()

    def tearDown(self):
        self.db.close()

    def test_summary_create_skips_when_catalog_missing(self):
        created = AlarmSummary.create(
            name="alarm.ghost",
            state="Unacknowledged",
            timestamp=datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
            area="Linea1",
        )
        self.assertIsNone(created)
        self.assertEqual(AlarmSummary.select().count(), 0)

    def test_write_creates_materializes_catalog_then_summary(self):
        from ..persistence.remote import PeeweeRemoteDB

        self.assertIsNone(Alarms.read_by_name("alarm.Test.Linea1.LDS.leak"))
        stamp = datetime(2026, 8, 18, 12, 1, tzinfo=timezone.utc)
        written = PeeweeRemoteDB()._write_alarm_creates(
            [
                {
                    "name": "alarm.Test.Linea1.LDS.leak",
                    "state": "Unacknowledged",
                    "timestamp": stamp.isoformat(),
                    "area": "Linea1",
                    "tag": "Test.Linea1.LDS.leak",
                    "identifier": "alm-leak-saf",
                    "trigger_type": "BOOL",
                    "trigger_value": 1,
                }
            ]
        )
        self.assertEqual(written, 1)
        catalog = Alarms.read_by_name("alarm.Test.Linea1.LDS.leak", area="Linea1")
        self.assertIsNotNone(catalog)
        self.assertEqual(catalog.area, "Linea1")
        self.assertEqual(AlarmSummary.select().count(), 1)
        row = AlarmSummary.select().get()
        self.assertEqual(row.area, "Linea1")
        self.assertEqual(row.alarm_id, catalog.id)


if __name__ == "__main__":
    unittest.main()
