# -*- coding: utf-8 -*-
"""ISA-18.2 P0 history tests T-01…T-11 against SQLite (no AlarmSummary mocks)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from peewee import SqliteDatabase

from automation.alarms import Alarm
from automation.alarms.states import (
    HISTORY_ACK,
    HISTORY_CLEARED,
    HISTORY_RTNUN,
    HISTORY_UNACK,
    AlarmState,
)
from automation.dbmodels import proxy
from automation.dbmodels.alarms import AlarmStates, AlarmSummary, AlarmTypes, Alarms
from automation.dbmodels.tags import DataTypes, Tags, Units, Variables
from automation.logger.alarms import AlarmsLogger, AlarmsLoggerEngine
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine


def _passthrough_journal(record, remote_write, connected):
    return remote_write(), True


class TestIsa18History(unittest.TestCase):
    def setUp(self):
        self.cvt = CVTEngine()
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables(
            [Variables, Units, DataTypes, Tags, AlarmTypes, AlarmStates, Alarms, AlarmSummary]
        )
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
        AlarmTypes.create(name="BOOL")
        self.logger = AlarmsLogger()
        self.logger.set_db(self.db)
        self.logger.is_history_logged = True
        self._conn_patch = patch.object(AlarmsLogger, "check_connectivity", return_value=True)
        self._journal_patch = patch(
            "automation.persistence.outbox.journal_then_remote",
            side_effect=_passthrough_journal,
        )
        self._engine_patch = patch.object(
            AlarmsLoggerEngine,
            "create_record_on_alarm_summary",
            self.logger.create_record_on_alarm_summary,
        )
        self._put_patch = patch.object(AlarmsLoggerEngine, "put", return_value=None)
        self._conn_patch.start()
        self._journal_patch.start()
        self._engine_patch.start()
        self._put_patch.start()
        self.addCleanup(self._conn_patch.stop)
        self.addCleanup(self._journal_patch.stop)
        self.addCleanup(self._engine_patch.stop)
        self.addCleanup(self._put_patch.stop)
        self.addCleanup(self.db.close)

    def _seed_catalog(self, name: str, tag_name: str) -> str:
        unit = Units.get(Units.name == "C")
        identifier = name[:8].ljust(8, "x")
        Tags(
            identifier=tag_name[:8].ljust(8, "0"),
            name=tag_name,
            unit=unit,
            data_type=DataTypes.get(DataTypes.name == "float"),
            display_name=tag_name,
            display_unit=unit,
            description="",
            area="Linea1",
        ).save()
        Alarms(
            identifier=identifier,
            name=name,
            tag=Tags.get(Tags.name == tag_name),
            trigger_type=AlarmTypes.get(AlarmTypes.name == "HIGH"),
            trigger_value=50,
            state=AlarmStates.get(AlarmStates.name == "Normal"),
            description="",
            area="Linea1",
        ).save()
        return identifier

    def _make(self, name: str, *, alarm_type: str = "HIGH", setpoint=50.0, reload=False, state="Normal"):
        tag_name = f"tag_{name}"
        self.cvt.set_tag(
            name=tag_name,
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description=tag_name,
        )
        tag = self.cvt.get_tag_by_name(name=tag_name)
        identifier = None
        if not reload:
            identifier = self._seed_catalog(name, tag_name)
        alarm = Alarm(
            name=name,
            tag=tag,
            alarm_type=StringType(alarm_type),
            alarm_setpoint=FloatType(setpoint),
            alarm_on_delay=FloatType(0.0),
            alarm_off_delay=FloatType(0.0),
            reload=reload,
            state=state,
            identifier=identifier,
        )
        alarm.enable_delay_wakeups = False
        return alarm, tag

    def _history(self, name: str):
        alarm_row = Alarms.read_by_name(name=name, area="Linea1") or Alarms.read_by_name(name=name)
        rows = list(
            AlarmSummary.select().where(AlarmSummary.alarm == alarm_row).order_by(AlarmSummary.id.asc())
        )
        return [row.to_state or row.state.name for row in rows], rows

    def _assert_chain(self, rows):
        for previous, current in zip(rows, rows[1:]):
            self.assertEqual(current.from_state, previous.to_state)

    def test_t01_ack_while_active(self):
        alarm, tag = self._make("t01")
        tag.set_value(value=55)
        alarm.acknowledge(operator_id=1)
        tag.set_value(value=45)
        states, rows = self._history("t01")
        self.assertEqual(states, [HISTORY_UNACK, HISTORY_ACK, HISTORY_CLEARED])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1].from_state, HISTORY_UNACK)
        self.assertEqual(rows[2].from_state, HISTORY_ACK)
        self.assertEqual(rows[1].operator_id, 1)
        self._assert_chain(rows)

    def test_t02_rtn_then_ack(self):
        alarm, tag = self._make("t02")
        tag.set_value(value=55)
        activation = alarm.timestamp
        tag.set_value(value=45)
        self.assertEqual(alarm.current_state.value.lower(), "rtn_unack")
        self.assertEqual(alarm.timestamp, activation)
        self.assertIsNotNone(alarm.last_transition_ts)
        alarm.acknowledge(operator_id=7)
        states, rows = self._history("t02")
        self.assertEqual(states, [HISTORY_UNACK, HISTORY_RTNUN, HISTORY_CLEARED])
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[0].operator_id)
        self.assertIsNone(rows[1].operator_id)
        self.assertEqual(rows[2].operator_id, 7)
        self._assert_chain(rows)

    def test_t03_redispparo(self):
        alarm, tag = self._make("t03")
        tag.set_value(value=55)
        tag.set_value(value=45)
        tag.set_value(value=60)
        alarm.acknowledge()
        tag.set_value(value=40)
        states, _ = self._history("t03")
        self.assertEqual(
            states,
            [HISTORY_UNACK, HISTORY_RTNUN, HISTORY_UNACK, HISTORY_ACK, HISTORY_CLEARED],
        )

    def test_t04_oscillation(self):
        alarm, tag = self._make("t04")
        tag.set_value(value=55)
        tag.set_value(value=45)
        tag.set_value(value=60)
        tag.set_value(value=40)
        tag.set_value(value=70)
        alarm.acknowledge()
        tag.set_value(value=30)
        states, _ = self._history("t04")
        self.assertEqual(len(states), 7)
        self.assertEqual(
            states,
            [
                HISTORY_UNACK,
                HISTORY_RTNUN,
                HISTORY_UNACK,
                HISTORY_RTNUN,
                HISTORY_UNACK,
                HISTORY_ACK,
                HISTORY_CLEARED,
            ],
        )

    def test_t05_noop_normal(self):
        alarm, _ = self._make("t05")
        before = AlarmSummary.select().count()
        alarm._record_transition("Normal", "Normal")
        self.assertEqual(AlarmSummary.select().count(), before)

    def test_t06_perf_autoclear(self):
        alarm, tag = self._make("site.ALM.PERF.CPU")
        tag.set_value(value=55)
        tag.set_value(value=45)
        states, _ = self._history("site.ALM.PERF.CPU")
        self.assertEqual(states, [HISTORY_UNACK, HISTORY_RTNUN, HISTORY_CLEARED])

    def test_t07_ack_in_normal(self):
        alarm, _ = self._make("t07")
        before = AlarmSummary.select().count()
        self.assertFalse(alarm.acknowledge())
        self.assertEqual(AlarmSummary.select().count(), before)

    def test_t08_ack_in_cleared(self):
        alarm, tag = self._make("t08")
        tag.set_value(value=55)
        alarm.acknowledge()
        tag.set_value(value=45)
        before = AlarmSummary.select().count()
        self.assertFalse(alarm.acknowledge())
        self.assertEqual(AlarmSummary.select().count(), before)

    def test_t09_record_same_state(self):
        alarm, _ = self._make("t09")
        before = AlarmSummary.select().count()
        self.assertFalse(alarm._record_transition(HISTORY_UNACK, HISTORY_UNACK))
        self.assertEqual(AlarmSummary.select().count(), before)

    def test_t10_shelved_skips_history(self):
        alarm, _ = self._make("t10")
        before = AlarmSummary.select().count()
        self.assertFalse(alarm._record_transition("Normal", "Shelved"))
        self.assertEqual(AlarmSummary.select().count(), before)

    def test_t11_last_transition_monotonic(self):
        alarm, tag = self._make("t11")
        stamps = []
        tag.set_value(value=55)
        stamps.append(alarm.last_transition_ts)
        tag.set_value(value=45)
        stamps.append(alarm.last_transition_ts)
        for previous, current in zip(stamps, stamps[1:]):
            self.assertLessEqual(previous, current)

    def test_p13_reload_restores_sm(self):
        self._seed_catalog("t_reload", "tag_t_reload")
        self.cvt.set_tag(
            name="tag_t_reload",
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description="reload",
        )
        tag = self.cvt.get_tag_by_name(name="tag_t_reload")
        before = AlarmSummary.select().count()
        alarm = Alarm(
            name="t_reload",
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(50.0),
            alarm_on_delay=FloatType(0.0),
            alarm_off_delay=FloatType(0.0),
            identifier="t_reloadx",
            reload=True,
            state="RTN Unacknowledged",
        )
        self.assertEqual(alarm.current_state.value.lower(), "rtn_unack")
        self.assertEqual(alarm._last_history_state, HISTORY_RTNUN)
        self.assertEqual(AlarmSummary.select().count(), before)
        alarm.acknowledge(operator_id=1)
        _, rows = self._history("t_reload")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].to_state, HISTORY_CLEARED)
        self.assertEqual(rows[0].from_state, HISTORY_RTNUN)

    def test_i01_annunciated_filter_includes_rtn(self):
        from automation.managers.alarms import AlarmManager

        mgr = AlarmManager()
        previous = dict(mgr._alarms)
        by_name = dict(mgr._by_name)
        by_tag = dict(mgr._by_tag_name)
        mgr._alarms.clear()
        mgr._by_name.clear()
        mgr._by_tag_name.clear()
        self.addCleanup(lambda: _restore_manager(mgr, previous, by_name, by_tag))
        scope_patch = patch("automation.managers.alarms._scope_owns_alarm", return_value=True)
        scope_patch.start()
        self.addCleanup(scope_patch.stop)

        unack, tag_b = self._make("i01b")
        tag_b.set_value(value=55)
        acked, tag_c = self._make("i01c")
        tag_c.set_value(value=55)
        acked.acknowledge()
        rtn, tag_d = self._make("i01d")
        tag_d.set_value(value=55)
        tag_d.set_value(value=45)
        normal, _ = self._make("i01e")
        for alarm in (unack, acked, rtn, normal):
            mgr._alarms[alarm.identifier] = alarm
            mgr._index_alarm(alarm)
        names = {item["name"] for item in mgr.get_lasts_active_alarms()}
        self.assertEqual(names, {"i01b", "i01c", "i01d"})
        self.assertEqual(rtn.serialize()["state"]["annunciate_status"], "Annunciated")


def _restore_manager(mgr, previous, by_name, by_tag):
    mgr._alarms.clear()
    mgr._by_name.clear()
    mgr._by_tag_name.clear()
    mgr._alarms.update(previous)
    mgr._by_name.update(by_name)
    mgr._by_tag_name.update(by_tag)
