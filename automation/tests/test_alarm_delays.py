# -*- coding: utf-8 -*-
"""ISA-18.2 On-Delay / Off-Delay evaluation (CA-AL-01 .. CA-AL-08)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from automation.alarms import Alarm
from automation.models import FloatType, StringType
from automation.tags.cvt import CVTEngine
from automation.variables import Adimentional

cvt = CVTEngine()
BASE = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def _ts(seconds: float) -> datetime:
    return BASE + timedelta(seconds=seconds)


def _qty(value: float) -> Adimentional:
    return Adimentional(value=value, unit="adim")


class _StubAlarm(Alarm):
    """Minimal Alarm subclass so @validate_types output check accepts the stub."""

    def __init__(self):
        self.identifier = "alm-1"
        self.name = "ALM_TEST"
        self.display_name = None
        self.owner_node = None
        self.area = None


def _make_alarm(name: str, *, on_delay: float = 0.0, off_delay: float = 0.0, deadband: float = 0.0) -> Alarm:
    cvt.set_tag(
        name=f"tag_{name}",
        variable="Temperature",
        unit="C",
        data_type="FLOAT",
        description=name,
    )
    tag = cvt.get_tag_by_name(name=f"tag_{name}")
    with patch.object(Alarm, "attach", lambda self, machine, tag: None):
        alarm = Alarm(
            name=name,
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(50.0),
            alarm_deadband=FloatType(deadband),
            alarm_on_delay=FloatType(on_delay),
            alarm_off_delay=FloatType(off_delay),
        )
    alarm.enable_delay_wakeups = False
    return alarm


class TestAlarmDelays(unittest.TestCase):
    def test_ca_al_01_on_delay_ignores_fleeting_peak(self):
        alarm = _make_alarm("ca01", on_delay=3.0, off_delay=0.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        self.assertEqual(alarm.state.state.lower(), "normal")
        self.assertEqual(alarm.serialize()["delay_phase"], "pending")
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(2))
        self.assertEqual(alarm.state.state.lower(), "normal")
        self.assertIsNone(alarm.serialize()["delay_phase"])

    def test_ca_al_02_on_delay_activates_after_continuous(self):
        alarm = _make_alarm("ca02", on_delay=3.0, off_delay=0.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        self.assertEqual(alarm.state.state.lower(), "normal")
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(3))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        self.assertIsNone(alarm.serialize()["delay_phase"])

    def test_ca_al_03_off_delay_holds_brief_drop(self):
        alarm = _make_alarm("ca03", on_delay=0.0, off_delay=5.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(1))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        self.assertEqual(alarm.serialize()["delay_phase"], "clearing")
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(3))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        self.assertIsNone(alarm.serialize()["delay_phase"])

    def test_ca_al_04_off_delay_clears_after_continuous_normal(self):
        alarm = _make_alarm("ca04", on_delay=0.0, off_delay=5.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(1))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(6))
        self.assertEqual(alarm.current_state.value.lower(), "rtn_unack")

    def test_ca_al_05_on_delay_timer_resets_on_intermittent(self):
        alarm = _make_alarm("ca05", on_delay=3.0, off_delay=0.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(1))
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(2))
        self.assertEqual(alarm.state.state.lower(), "normal")
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(4.5))
        self.assertEqual(alarm.state.state.lower(), "normal")
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(5))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")

    def test_ca_al_06_off_delay_timer_resets_when_condition_returns(self):
        alarm = _make_alarm("ca06", on_delay=0.0, off_delay=5.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(1))
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(4))
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(5))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(9))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(10))
        self.assertEqual(alarm.current_state.value.lower(), "rtn_unack")

    def test_ca_al_07_zero_delays_are_immediate(self):
        alarm = _make_alarm("ca07", on_delay=0.0, off_delay=0.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(60.0), timestamp=_ts(0))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        alarm.notify(tag=alarm.tag.name, value=_qty(40.0), timestamp=_ts(0.1))
        self.assertEqual(alarm.current_state.value.lower(), "rtn_unack")

    def test_ca_al_08_serialize_and_put_include_delays(self):
        alarm = _make_alarm("ca08", on_delay=3.0, off_delay=5.0)
        payload = alarm.serialize()
        self.assertEqual(payload["on_delay"], 3.0)
        self.assertEqual(payload["off_delay"], 5.0)
        self.assertEqual(payload["on_delay_units"], "seconds")
        self.assertEqual(payload["off_delay_units"], "seconds")
        self.assertIn("condition_met", payload)
        self.assertIn("on_timer_remaining", payload)
        self.assertIn("off_timer_remaining", payload)
        self.assertIn("delay_phase", payload)
        alarm.put(on_delay=8.0, off_delay=1.0)
        updated = alarm.serialize()
        self.assertEqual(updated["on_delay"], 8.0)
        self.assertEqual(updated["off_delay"], 1.0)

    def test_default_delay_is_zero_seconds(self):
        cvt.set_tag(
            name="tag_default_delay",
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description="default",
        )
        tag = cvt.get_tag_by_name(name="tag_default_delay")
        with patch.object(Alarm, "attach", lambda self, machine, tag: None):
            alarm = Alarm(
                name="default_delay",
                tag=tag,
                alarm_type=StringType("HIGH"),
                alarm_setpoint=FloatType(50.0),
            )
        self.assertEqual(alarm._on_delay_s(), 0.0)
        self.assertEqual(alarm._off_delay_s(), 0.0)

    def test_bool_trigger_serializes_as_boolean(self):
        cvt.set_tag(
            name="tag_bool_trigger",
            variable="Adimentional",
            unit="adim",
            data_type="BOOL",
            description="bool",
        )
        tag = cvt.get_tag_by_name(name="tag_bool_trigger")
        with patch.object(Alarm, "attach", lambda self, machine, tag: None):
            alarm = Alarm(
                name="bool_trigger",
                tag=tag,
                alarm_type=StringType("BOOL"),
                alarm_setpoint=FloatType(True),
            )
        self.assertIs(alarm.alarm_setpoint.value, True)
        payload = alarm.serialize()
        self.assertEqual(payload["alarm_type"], "BOOL")
        self.assertIs(payload["trigger_value"], True)
        self.assertEqual(payload["alarm_setpoint"]["value"], True)

    def test_create_alarm_reload_accepts_delay_fields(self):
        """DB serialize() includes on_delay; @validate_types must not KeyError on load."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from automation.core import PyAutomation

        app = PyAutomation.__new__(PyAutomation)
        app.sio = None
        tag = MagicMock()
        tag.area = "Linea1"
        app.cvt = MagicMock()
        app.cvt.get_tag_by_name.return_value = tag
        app._refresh_node_scope = MagicMock(
            return_value=SimpleNamespace(
                enabled=False,
                is_valid=True,
                area=None,
                node_id="n1",
                owns_tag=lambda _tag: True,
            )
        )
        alarm = _StubAlarm()
        app.alarm_manager = MagicMock()
        app.alarm_manager.append_alarm.return_value = (alarm, "ok")
        app.is_db_connected = MagicMock(return_value=False)

        result = PyAutomation.create_alarm(
            app,
            reload=True,
            name="ALM_TEST",
            tag="tag_test",
            alarm_type="BOOL",
            trigger_value=True,
            description="",
            identifier="alm-1",
            state="Normal",
            timestamp=None,
            area="Linea1",
            on_delay=0.0,
            off_delay=0,
            on_delay_units="seconds",
            off_delay_units="seconds",
        )
        self.assertIs(result[0], alarm)
        app.alarm_manager.append_alarm.assert_called_once()
        kwargs = app.alarm_manager.append_alarm.call_args.kwargs
        self.assertEqual(kwargs["on_delay"], 0.0)
        self.assertEqual(kwargs["off_delay"], 0)


class TestIadQualityLifecycle(unittest.TestCase):
    def _make_iad(self, *, on_delay: float = 0.0, off_delay: float = 0.0) -> Alarm:
        from automation.signal_conditioning.quality import GOOD

        cvt.set_tag(
            name="tag_iad_pv",
            variable="Pressure",
            unit="bar",
            data_type="FLOAT",
            description="iad",
        )
        tag = cvt.get_tag_by_name(name="tag_iad_pv")
        tag.quality = GOOD
        tag.stale = False
        with patch.object(Alarm, "attach", lambda self, machine, tag: None):
            alarm = Alarm(
                name="alarm.tag_iad_pv.iad",
                tag=tag,
                alarm_type=StringType("BOOL"),
                alarm_setpoint=FloatType(True),
                alarm_on_delay=FloatType(on_delay),
                alarm_off_delay=FloatType(off_delay),
            )
        alarm.enable_delay_wakeups = False
        return alarm

    def test_iad_ignores_analog_value_when_quality_good(self):
        alarm = self._make_iad(on_delay=0.0)
        alarm.notify(tag=alarm.tag.name, value=_qty(55.0), timestamp=_ts(0))
        self.assertEqual(alarm.state.state.lower(), "normal")

    def test_iad_trips_on_bad_quality_and_clears_on_good(self):
        from automation.signal_conditioning.quality import BAD, GOOD

        alarm = self._make_iad(on_delay=3.0, off_delay=0.0)
        alarm.tag.quality = BAD
        alarm.tag.stale = True
        alarm.notify(tag=alarm.tag.name, value=_qty(55.0), timestamp=_ts(0))
        self.assertEqual(alarm.state.state.lower(), "normal")
        alarm.notify(tag=alarm.tag.name, value=_qty(55.0), timestamp=_ts(3))
        self.assertEqual(alarm.state.state.lower(), "unacknowledged")
        alarm.acknowledge()
        self.assertEqual(alarm.state.state.lower(), "acknowledged")
        alarm.notify(tag=alarm.tag.name, value=_qty(55.0), timestamp=_ts(4))
        self.assertEqual(alarm.state.state.lower(), "acknowledged")
        alarm.tag.quality = GOOD
        alarm.tag.stale = False
        alarm.notify(tag=alarm.tag.name, value=_qty(55.0), timestamp=_ts(5))
        self.assertEqual(alarm.state.state.lower(), "normal")


if __name__ == "__main__":
    unittest.main()
