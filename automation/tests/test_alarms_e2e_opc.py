# -*- coding: utf-8 -*-
"""E2E OPC + ISA cycle. GATE-34 / GATE-38. PV del simulador no es escribible."""
from __future__ import annotations

import os
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from peewee import SqliteDatabase

from automation.alarms import Alarm
from automation.alarms.runtime import reset_alarm_runtime_for_tests
from automation.alarms.states import AlarmState, HISTORY_ACK, HISTORY_CLEARED, HISTORY_RTNUN, HISTORY_UNACK
from automation.dbmodels import proxy
from automation.dbmodels.alarms import AlarmStates, AlarmSummary, AlarmTypes, Alarms
from automation.dbmodels.tags import DataTypes, Tags, Units, Variables
from automation.logger.alarms import AlarmsLogger, AlarmsLoggerEngine
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine


def _passthrough_journal(record, remote_write, connected):
    return remote_write(), True


class TestAlarmE2EOPC(unittest.TestCase):
    def test_opc_simulator_readable(self):
        from opcua import Client

        client = Client("opc.tcp://127.0.0.1:4840")
        client.connect()
        try:
            node = client.get_node("ns=2;i=2")
            value = node.get_value()
            self.assertIsNotNone(value)
            print(f"OPC FI_01={value}")
            try:
                node.set_value(60.0)
                writable = True
            except Exception as exc:
                writable = False
                print(f"OPC write denied: {type(exc).__name__}: {exc}")
            self.assertFalse(writable, "si el simulador permite write, actualizar este test")
        finally:
            client.disconnect()

    def test_isa_lifecycle_five_history_rows(self):
        """Ciclo A→B→D→B→C→E con check_condition real (PV local; OPC no escribible)."""
        runtime = reset_alarm_runtime_for_tests()
        cvt = CVTEngine()
        db = SqliteDatabase(":memory:")
        proxy.initialize(db)
        db.create_tables([Variables, Units, DataTypes, Tags, AlarmTypes, AlarmStates, Alarms, AlarmSummary])
        Variables(name="Temperature").save()
        Units(name="C", unit="C", variable_id=Variables.get(Variables.name == "Temperature")).save()
        DataTypes(name="float").save()
        for alarm_state in AlarmState._states:
            AlarmStates.create(
                name=alarm_state.state,
                mnemonic=alarm_state.mnemonic,
                condition=alarm_state.process_condition,
                status=alarm_state.alarm_status,
            )
        AlarmTypes.create(name="HIGH")
        logger = AlarmsLogger()
        logger.set_db(db)
        logger.is_history_logged = True
        patches = [
            patch.object(AlarmsLogger, "check_connectivity", return_value=True),
            patch("automation.persistence.outbox.journal_then_remote", side_effect=_passthrough_journal),
            patch.object(AlarmsLoggerEngine, "create_record_on_alarm_summary", logger.create_record_on_alarm_summary),
            patch.object(AlarmsLoggerEngine, "put", return_value=None),
        ]
        for item in patches:
            item.start()
        try:
            cvt.set_tag(name="FI_E2E", variable="Temperature", unit="C", data_type="FLOAT", description="e2e")
            tag = cvt.get_tag_by_name(name="FI_E2E")
            identifier = "e2ealarm01"
            unit = Units.get(Units.name == "C")
            Tags(
                identifier="fie2e001",
                name="FI_E2E",
                unit=unit,
                data_type=DataTypes.get(DataTypes.name == "float"),
                display_name="FI_E2E",
                display_unit=unit,
                description="e2e",
                area="Linea1",
            ).save()
            Alarms(
                identifier=identifier,
                name="ALM.TEST.HIGH",
                tag=Tags.get(Tags.name == "FI_E2E"),
                trigger_type=AlarmTypes.get(AlarmTypes.name == "HIGH"),
                trigger_value=50,
                state=AlarmStates.get(AlarmStates.name == "Normal"),
                description="",
                area="Linea1",
            ).save()
            alarm = Alarm(
                name="ALM.TEST.HIGH",
                tag=tag,
                alarm_type=StringType("HIGH"),
                alarm_setpoint=FloatType(50.0),
                alarm_on_delay=FloatType(0.0),
                alarm_off_delay=FloatType(0.0),
                identifier=identifier,
            )
            alarm.enable_delay_wakeups = False
            now = datetime.now(timezone.utc)
            alarm.check_condition(60.0, now)
            runtime.drain()
            alarm.check_condition(40.0, now)
            runtime.drain()
            alarm.check_condition(60.0, now)
            runtime.drain()
            alarm.acknowledge()
            runtime.drain()
            alarm.check_condition(40.0, now)
            runtime.drain()
            rows = list(AlarmSummary.select().order_by(AlarmSummary.id))
            states = [(row.from_state, row.to_state) for row in rows]
            print("history", states)
            self.assertGreaterEqual(len(rows), 5)
            uuids = [str(row.sample_uuid) for row in rows if row.sample_uuid]
            self.assertEqual(len(uuids), len(set(uuids)))
        finally:
            for item in patches:
                item.stop()
            runtime.stop_worker()
            db.close()


class TestPgHistoryLabInsert(unittest.TestCase):
    def test_five_unique_uuids_roundtrip_pg(self):
        try:
            import psycopg2
            conn = psycopg2.connect(
                host="127.0.0.1", port=32800, user="postgres", password="postgres", dbname="app_db"
            )
        except Exception as exc:
            self.skipTest(str(exc))
        conn.autocommit = True
        cur = conn.cursor()
        uuids = [str(uuid4()) for _ in range(5)]
        seq = [
            ("Normal", "Unack Alarm"),
            ("Unack Alarm", "RTN Unack"),
            ("RTN Unack", "Unack Alarm"),
            ("Unack Alarm", "Ack Alarm"),
            ("Ack Alarm", "Cleared"),
        ]
        for uid, (frm, to) in zip(uuids, seq):
            cur.execute(
                """
                INSERT INTO alarmsummary (
                    alarm_id, from_state, to_state, event_time, sample_uuid, schema_version
                ) VALUES (1, %s, %s, NOW(), %s, 2)
                """,
                (frm, to, uid),
            )
        cur.execute(
            "SELECT from_state, to_state, sample_uuid FROM alarmsummary WHERE sample_uuid = ANY(%s) ORDER BY id",
            (uuids,),
        )
        got = cur.fetchall()
        conn.close()
        self.assertEqual(len(got), 5)
        self.assertEqual([row[0] for row in got], [s[0] for s in seq])
        self.assertEqual(len({row[2] for row in got}), 5)
