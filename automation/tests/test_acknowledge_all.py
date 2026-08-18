# -*- coding: utf-8 -*-
"""Bulk acknowledge-all: one persist round-trip, ISA transitions, scope."""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from ..alarms import Alarm
from ..alarms.states import AlarmState
from ..managers.alarms import AlarmManager
from ..models import FloatType, StringType
from ..modules.users.users import User
from ..tags.tag import Tag


def _tag(name: str) -> Tag:
    return Tag(
        name=name,
        unit="C",
        variable="Temperature",
        data_type="float",
        id=name[:8].ljust(8, "0"),
        area="Linea1",
    )


def _alarm(name: str) -> Alarm:
    return Alarm(
        name=name,
        tag=_tag(f"tag_{name}"),
        alarm_type=StringType("HIGH"),
        alarm_setpoint=FloatType(50.0),
        identifier=f"id-{name}",
    )


def _enter(alarm: Alarm, *transitions: str) -> None:
    alarm._defer_persist = True
    try:
        for transition in transitions:
            alarm.send(transition)
    finally:
        alarm._defer_persist = False


class TestAcknowledgeAll(unittest.TestCase):
    def setUp(self):
        self.mgr = AlarmManager()
        self._previous = dict(self.mgr._alarms)
        self.mgr._alarms.clear()
        self.mgr._by_name.clear()
        self.mgr._by_tag_name.clear()
        self.user = MagicMock(spec=User)
        self.user.username = "operator"
        for target in (
            "automation.logger.alarms.AlarmsLoggerEngine.put",
            "automation.logger.alarms.AlarmsLoggerEngine.put_record_on_alarm_summary",
            "automation.logger.alarms.AlarmsLoggerEngine.create_record_on_alarm_summary",
            "automation.managers.alarms._scope_owns_alarm",
        ):
            kwargs = {}
            if target.endswith("_scope_owns_alarm"):
                kwargs["return_value"] = True
            else:
                kwargs["return_value"] = None
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.mgr._alarms.clear()
        self.mgr._by_name.clear()
        self.mgr._by_tag_name.clear()
        self.mgr._alarms.update(self._previous)
        for alarm in self._previous.values():
            self.mgr._index_alarm(alarm)

    def _register(self, *alarms: Alarm, emit: bool = True) -> None:
        for alarm in alarms:
            alarm.sio = MagicMock() if emit else None
            self.mgr._alarms[alarm.identifier] = alarm
            self.mgr._index_alarm(alarm)

    def test_acks_unack_and_rtnun_in_one_persist_call(self):
        unack = _alarm("bulk_unack")
        rtnun = _alarm("bulk_rtnun")
        already = _alarm("bulk_norm")
        _enter(unack, "normal_to_unack_alarm")
        _enter(rtnun, "normal_to_unack_alarm", "unack_alarm_to_rtn_unack")
        self._register(unack, rtnun, already)

        with patch("automation.PyAutomation") as app_cls, \
             patch("automation.utils.decorators.events_engine.create", return_value=(MagicMock(), None)) as create_event, \
             patch("automation.logger.alarms.AlarmsLoggerEngine.acknowledge_many", return_value=2) as persist:
            app_cls.return_value.sio = None
            result = self.mgr.acknowledge_all(user=self.user)

        self.assertEqual(unack.state.mnemonic, AlarmState.ACKED.mnemonic)
        self.assertEqual(rtnun.state.mnemonic, AlarmState.NORM.mnemonic)
        self.assertEqual(already.state.mnemonic, AlarmState.NORM.mnemonic)
        self.assertEqual(result[1], 2)
        persist.assert_called_once()
        payload = persist.call_args.args[0]
        self.assertEqual(len(payload), 2)
        self.assertEqual({item["name"] for item in payload}, {"bulk_unack", "bulk_rtnun"})
        self.assertTrue(all(item.get("area") == "Linea1" for item in payload))
        self.assertEqual(create_event.call_args.kwargs.get("message"), "Alarms acknowledged")
        ack_times = {item["ack_timestamp"] for item in payload}
        self.assertEqual(len(ack_times), 1)
        create_event.assert_called_once()
        unack.sio.emit.assert_called_once()
        rtnun.sio.emit.assert_called_once()
        already.sio.emit.assert_not_called()

    def test_skips_alarms_outside_scope(self):
        owned = _alarm("owned_unack")
        foreign = _alarm("foreign_unack")
        _enter(owned, "normal_to_unack_alarm")
        _enter(foreign, "normal_to_unack_alarm")
        self._register(owned, foreign)

        def _owns(alarm):
            return alarm.name != "foreign_unack"

        with patch("automation.managers.alarms._scope_owns_alarm", side_effect=_owns), \
             patch("automation.PyAutomation") as app_cls, \
             patch("automation.utils.decorators.events_engine.create", return_value=(MagicMock(), None)), \
             patch("automation.logger.alarms.AlarmsLoggerEngine.acknowledge_many", return_value=1) as persist:
            app_cls.return_value.sio = None
            result = self.mgr.acknowledge_all(user=self.user)

        self.assertEqual(result[1], 1)
        self.assertEqual(owned.state.mnemonic, AlarmState.ACKED.mnemonic)
        self.assertEqual(foreign.state.mnemonic, AlarmState.UNACK.mnemonic)
        persist.assert_called_once()
        self.assertEqual(persist.call_args.args[0][0]["name"], "owned_unack")

    def test_five_and_fifty_stay_under_50ms_with_mocked_io(self):
        def _run(n: int) -> float:
            alarms = []
            for i in range(n):
                alarm = _alarm(f"perf_{n}_{i}")
                _enter(alarm, "normal_to_unack_alarm")
                alarms.append(alarm)
            self.mgr._alarms.clear()
            self.mgr._by_name.clear()
            self.mgr._by_tag_name.clear()
            self._register(*alarms, emit=False)
            with patch("automation.PyAutomation") as app_cls, \
                 patch("automation.utils.decorators.events_engine.create", return_value=(MagicMock(), None)), \
                 patch("automation.logger.alarms.AlarmsLoggerEngine.acknowledge_many", return_value=n) as persist:
                app_cls.return_value.sio = None
                started = time.perf_counter()
                result = self.mgr.acknowledge_all(user=self.user)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.assertEqual(result[1], n)
            persist.assert_called_once()
            self.assertLess(elapsed_ms, 50.0, f"{n} alarms took {elapsed_ms:.1f} ms")
            return elapsed_ms

        _run(5)
        _run(50)
