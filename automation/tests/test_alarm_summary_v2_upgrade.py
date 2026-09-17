# -*- coding: utf-8 -*-
"""Upgrade path: pre-ISA alarmsummary on a remote historian must gain v2 columns
without dropping existing rows (lab postgres with an old schema)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from peewee import SqliteDatabase

from automation.dbmodels import proxy
from automation.dbmodels.alarms import AlarmStates, AlarmSummary, AlarmTypes, Alarms
from automation.dbmodels.tags import DataTypes, Tags, Units, Variables
from automation.persistence.idempotent_insert import AlarmSummaryInserter


class TestAlarmSummaryV2RemoteUpgrade(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables(
            [Variables, Units, DataTypes, Tags, AlarmTypes, AlarmStates, Alarms]
        )
        self.db.execute_sql(
            """
            CREATE TABLE alarmsummary (
              id INTEGER PRIMARY KEY,
              alarm_id INTEGER NOT NULL,
              state_id INTEGER NOT NULL,
              alarm_time INTEGER,
              ack_time INTEGER,
              area VARCHAR(64),
              sample_uuid VARCHAR(255)
            )
            """
        )
        Variables(name="Adimentional").save()
        Units(
            name="adim",
            unit="adim",
            variable_id=Variables.get(Variables.name == "Adimentional"),
        ).save()
        DataTypes(name="int").save()
        unit = Units.get(Units.name == "adim")
        Tags(
            identifier="tag-legacy",
            name="Supe.Linea1.LDS.leak",
            unit=unit,
            data_type=DataTypes.get(DataTypes.name == "int"),
            display_name="Supe.Linea1.LDS.leak",
            display_unit=unit,
            description="",
            area="Linea1",
            owner_node="edge-Supe-Linea1",
        ).save()
        AlarmTypes(name="BOOL").save()
        AlarmStates(
            name="Unacknowledged",
            mnemonic="UNACK",
            condition="Active",
            status="Unack",
        ).save()
        Alarms(
            identifier="alm-legacy",
            name="alarm.Supe.Linea1.LDS.leak",
            tag=Tags.get(Tags.name == "Supe.Linea1.LDS.leak"),
            trigger_type=AlarmTypes.get(AlarmTypes.name == "BOOL"),
            trigger_value=1,
            state=AlarmStates.get(AlarmStates.name == "Unacknowledged"),
            description="",
            area="Linea1",
        ).save()
        alarm = Alarms.get(Alarms.name == "alarm.Supe.Linea1.LDS.leak")
        state = AlarmStates.get(AlarmStates.name == "Unacknowledged")
        self.db.execute_sql(
            """
            INSERT INTO alarmsummary (id, alarm_id, state_id, alarm_time, ack_time, area, sample_uuid)
            VALUES (1, ?, ?, 1710000000, NULL, 'Linea1', 'legacy-row-uuid')
            """,
            (alarm.id, state.id),
        )

    def tearDown(self):
        self.db.close()

    def _columns(self) -> set[str]:
        return {item.name for item in self.db.get_columns("alarmsummary")}

    def test_ensure_schema_adds_v2_columns_and_keeps_legacy_row(self):
        before = self._columns()
        self.assertNotIn("from_state", before)
        self.assertEqual(
            self.db.execute_sql("SELECT COUNT(*) FROM alarmsummary").fetchone()[0],
            1,
        )

        AlarmSummary.ensure_schema()

        after = self._columns()
        for column in (
            "from_state",
            "to_state",
            "event_time",
            "operator_id",
            "condition_met",
            "condition_value",
            "schema_version",
        ):
            self.assertIn(column, after)

        row = self.db.execute_sql(
            "SELECT sample_uuid, area, from_state, to_state, schema_version, event_time "
            "FROM alarmsummary WHERE id = 1"
        ).fetchone()
        self.assertEqual(row[0], "legacy-row-uuid")
        self.assertEqual(row[1], "Linea1")
        self.assertEqual(row[2], "Unacknowledged")
        self.assertEqual(row[3], "Unacknowledged")
        self.assertEqual(row[4], 1)
        self.assertIsNotNone(row[5])
        self.assertEqual(
            self.db.execute_sql("SELECT COUNT(*) FROM alarmsummary").fetchone()[0],
            1,
        )

    def test_ensure_schema_is_idempotent(self):
        AlarmSummary.ensure_schema()
        AlarmSummary.ensure_schema()
        self.assertEqual(
            self.db.execute_sql("SELECT COUNT(*) FROM alarmsummary").fetchone()[0],
            1,
        )
        self.assertIn("from_state", self._columns())

    def test_saf_inserter_repairs_schema_then_inserts(self):
        self.assertNotIn("from_state", self._columns())
        alarm = Alarms.get(Alarms.name == "alarm.Supe.Linea1.LDS.leak")
        state = AlarmStates.get(AlarmStates.name == "Unacknowledged")
        stamp = datetime(2026, 9, 17, 13, 33, 27, tzinfo=timezone.utc)
        inserter = AlarmSummaryInserter()
        ok = inserter.insert_one(
            {
                "alarm": alarm.id,
                "state": state.id,
                "alarm_time": stamp,
                "ack_time": None,
                "area": "Linea1",
                "sample_uuid": "c0ee6eae-5f92-47ad-8ad0-186a2e2cd2ab",
                "from_state": "Normal",
                "to_state": "Unack Alarm",
                "event_time": stamp,
                "schema_version": 2,
            }
        )
        self.assertTrue(ok)
        self.assertIn("from_state", self._columns())
        self.assertEqual(
            self.db.execute_sql("SELECT COUNT(*) FROM alarmsummary").fetchone()[0],
            2,
        )
        new_row = self.db.execute_sql(
            "SELECT from_state, to_state FROM alarmsummary "
            "WHERE sample_uuid = 'c0ee6eae-5f92-47ad-8ad0-186a2e2cd2ab'"
        ).fetchone()
        self.assertEqual(new_row[0], "Normal")
        self.assertEqual(new_row[1], "Unack Alarm")
        legacy = self.db.execute_sql(
            "SELECT sample_uuid FROM alarmsummary WHERE id = 1"
        ).fetchone()
        self.assertEqual(legacy[0], "legacy-row-uuid")
