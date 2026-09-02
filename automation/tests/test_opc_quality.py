# -*- coding: utf-8 -*-
"""Acceptance tests for OPC quality semantics and degraded OPC disconnect (spec 09)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.signal_conditioning.quality import (
    BAD,
    GOOD,
    UNCERTAIN,
    is_process_alarm_allowed,
    status_code_to_quality,
)
from automation.state_machine import StateMachineCore
from automation.tags.cvt import CVT, CVTEngine
from automation.tags.tag import MachineObserver, Tag
from automation.variables import Adimentional


def _make_tag(name: str = "PV.Press", **kwargs) -> Tag:
    return Tag(
        name=name,
        unit="adim",
        data_type="float",
        variable="Adimentional",
        id=kwargs.pop("id", "t1"),
        **kwargs,
    )


def setUpModule():
    from automation.signal_conditioning.quality import set_inhibit_uncertain_quality

    set_inhibit_uncertain_quality(False)
    patch("automation.alarms.quality_gate.set_quality_degraded").start()
    patch("automation.alarms.quality_gate._emit_quality_event").start()


def tearDownModule():
    patch.stopall()
    from automation.signal_conditioning.quality import set_inhibit_uncertain_quality

    set_inhibit_uncertain_quality(False)


class TestStatusCodeMapping(unittest.TestCase):
    def test_severity_bits_map_to_quality(self):
        try:
            from opcua import ua
        except ImportError:
            self.skipTest("opcua not installed")
        self.assertEqual(status_code_to_quality(ua.StatusCode(ua.StatusCodes.Good)), GOOD)
        self.assertEqual(
            status_code_to_quality(ua.StatusCode(ua.StatusCodes.Uncertain)), UNCERTAIN
        )
        self.assertEqual(status_code_to_quality(ua.StatusCode(ua.StatusCodes.Bad)), BAD)
        self.assertEqual(
            status_code_to_quality(ua.StatusCode(ua.StatusCodes.BadNodeIdUnknown)), BAD
        )

    def test_int_status_codes(self):
        self.assertEqual(status_code_to_quality(0), GOOD)
        self.assertEqual(status_code_to_quality(0x40000000), UNCERTAIN)
        self.assertEqual(status_code_to_quality(0x80000000), BAD)
        self.assertEqual(status_code_to_quality(None), GOOD)


class TestCVTQualityPropagation(unittest.TestCase):
    """CA-OQ-01: CVTEngine.set_value must persist quality."""

    def test_engine_set_value_propagates_quality(self):
        engine = CVTEngine()
        tag = _make_tag(id="cvtq")
        engine._cvt._tags[tag.id] = tag
        engine._cvt._name_index[tag.name] = tag.id
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("automation.tags.cvt._scope_owns_tag", return_value=True):
            engine.set_value(id=tag.id, value=1.0, timestamp=ts, quality=GOOD)
            engine.set_value(id=tag.id, value=9.0, timestamp=ts, quality=BAD)
        self.assertEqual(tag.quality, BAD)
        self.assertTrue(tag.stale)
        self.assertEqual(tag.get_value(), 1.0)


class TestHoldLast(unittest.TestCase):
    """CA-OQ-03: Bad/NaN/Inf hold last good PV and update quality."""

    def test_bad_holds_last_good(self):
        tag = _make_tag()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=42.0, timestamp=ts, quality=GOOD)
        tag.set_value(value=0.0, timestamp=ts, quality=BAD)
        self.assertEqual(tag.get_value(), 42.0)
        self.assertEqual(tag.quality, BAD)
        self.assertTrue(tag.stale)
        self.assertIsNotNone(tag.stale_timestamp)
        self.assertEqual(tag._bad_samples_dropped, 1)

    def test_nan_holds_last_good(self):
        tag = _make_tag()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=7.5, timestamp=ts, quality=GOOD)
        tag.set_value(value=float("nan"), timestamp=ts, quality=GOOD)
        self.assertEqual(tag.get_value(), 7.5)
        self.assertEqual(tag.quality, BAD)
        self.assertTrue(tag.stale)

    def test_good_clears_stale(self):
        tag = _make_tag()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=1.0, timestamp=ts, quality=GOOD)
        tag.set_value(value=2.0, timestamp=ts, quality=BAD)
        tag.set_value(value=3.0, timestamp=ts, quality=GOOD)
        self.assertEqual(tag.get_value(), 3.0)
        self.assertEqual(tag.quality, GOOD)
        self.assertFalse(tag.stale)
        self.assertIsNone(tag.stale_timestamp)

    def test_serialize_exposes_stale_age(self):
        tag = _make_tag()
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=1.0, timestamp=ts, quality=GOOD)
        tag.set_value(value=2.0, timestamp=ts, quality=BAD)
        payload = tag.serialize_socket()
        self.assertEqual(payload["quality"], BAD)
        self.assertEqual(payload["quality_label"], "BAD")
        self.assertTrue(payload["stale"])
        self.assertIsNotNone(payload["stale_age_ms"])

    def test_first_bad_sample_does_not_notify_machine_without_timestamp(self):
        """Lab / OPC down: first sample is BAD, Tag.timestamp stays None (hold-last)."""
        tag = _make_tag()
        machine = MagicMock()
        tag.attach(MachineObserver(machine))
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=0.0, timestamp=ts, quality=BAD)
        machine.notify.assert_not_called()
        self.assertIsNone(tag.get_timestamp())
        self.assertTrue(tag.stale)
        self.assertEqual(tag.quality, BAD)

    def test_machine_notified_after_first_good_sample(self):
        tag = _make_tag()
        machine = MagicMock()
        tag.attach(MachineObserver(machine))
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=1.0, timestamp=ts, quality=GOOD)
        machine.notify.assert_called_once()
        _, kwargs = machine.notify.call_args
        self.assertEqual(kwargs["tag"], tag.name)
        self.assertEqual(kwargs["timestamp"], ts)

    def test_state_machine_notify_ignores_none_timestamp(self):
        StateMachineCore.notify(
            object(),
            tag="PV.Press",
            value=Adimentional(0.0, unit="adim"),
            timestamp=None,
        )


class TestAlarmQualityGate(unittest.TestCase):
    """CA-OQ-04: process alarms inhibited on BAD quality."""

    def test_is_process_alarm_allowed_policy(self):
        self.assertTrue(is_process_alarm_allowed(GOOD))
        self.assertTrue(is_process_alarm_allowed(UNCERTAIN))
        self.assertFalse(is_process_alarm_allowed(BAD))
        self.assertFalse(is_process_alarm_allowed(UNCERTAIN, inhibit_uncertain=True))

    def test_alarm_notify_skips_setpoint_on_bad(self):
        from automation.alarms import Alarm
        from automation.models import FloatType, StringType
        from automation.variables import Adimentional

        tag = _make_tag(name="PV.Hi")
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tag.set_value(value=10.0, timestamp=ts, quality=GOOD)
        with patch.object(Alarm, "attach", lambda self, machine, tag: None):
            alarm = Alarm(
                name="ALM.PV.Hi",
                tag=tag,
                alarm_type=StringType("HIGH"),
                alarm_setpoint=FloatType(50.0),
                alarm_on_delay=FloatType(0.0),
                alarm_off_delay=FloatType(0.0),
            )
        # Simulate a Bad sample that would trip HI if evaluated on the incoming value.
        tag.quality = BAD
        tag.stale = True
        high = Adimentional(value=99.0, unit="adim")
        alarm.notify(tag=tag.name, value=high, timestamp=ts)
        self.assertEqual(alarm.state.state.lower(), "normal")

        tag.quality = GOOD
        tag.stale = False
        alarm.notify(tag=tag.name, value=high, timestamp=ts)
        self.assertIn(alarm.state.state.lower(), ("unacknowledged", "unack_alarm"))


class TestSubscriptionStatusCode(unittest.TestCase):
    """CA-OQ-02: datachange StatusCode reaches CVT quality."""

    def test_datachange_passes_bad_quality(self):
        from automation.opcua.subscription import DAS

        das = DAS()
        tag = _make_tag(name="OPC.PV", id="opc1")
        tag.node_namespace = "ns=2;s=PV"
        das.cvt = MagicMock()
        das.cvt.get_tag_by_node_namespace.return_value = tag
        das.cvt.set_value_fast = MagicMock(return_value=1.0)

        node = SimpleNamespace(nodeid=SimpleNamespace(to_string=lambda: "ns=2;s=PV"))
        try:
            from opcua import ua

            status = ua.StatusCode(ua.StatusCodes.Bad)
        except ImportError:
            status = SimpleNamespace(value=0x80000000, is_good=lambda: False)

        data = SimpleNamespace(
            monitored_item=SimpleNamespace(
                Value=SimpleNamespace(
                    SourceTimestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    StatusCode=status,
                )
            )
        )
        with patch("automation.opcua.subscription._scope_owns_tag", return_value=True):
            with patch.object(tag.value, "convert_value", side_effect=lambda value, from_unit, to_unit: value):
                das.datachange_notification(node, 1.23, data)

        kwargs = das.cvt.set_value_fast.call_args.kwargs
        self.assertEqual(kwargs.get("quality"), BAD)


class TestOpcDisconnectStale(unittest.TestCase):
    """CA-OQ-05: disconnect marks client tags BAD/stale without clobbering PV."""

    def test_mark_opcua_client_tags_stale(self):
        engine = CVTEngine()
        tag = _make_tag(name="Line.P", id="disc1")
        tag.opcua_client_name = "PlantOPC"
        engine._cvt._tags[tag.id] = tag
        engine._cvt._name_index[tag.name] = tag.id
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("automation.tags.cvt._scope_owns_tag", return_value=True):
            engine.set_value(id=tag.id, value=55.0, timestamp=ts, quality=GOOD)
            marked = engine.mark_opcua_client_tags_stale("PlantOPC")
        self.assertEqual(marked, 1)
        self.assertEqual(tag.get_value(), 55.0)
        self.assertEqual(tag.quality, BAD)
        self.assertTrue(tag.stale)


class TestLoginEventId(unittest.TestCase):
    """CA-OQ-07: degraded login payload carries correlatable event_id."""

    def test_database_unavailable_payload_has_event_id(self):
        from automation.modules.users.resources import users as users_mod
        from automation.utils.db_audit import database_connection_auditor

        database_connection_auditor.reset()
        payload = users_mod._database_unavailable_payload("down", "details")
        self.assertEqual(payload["error_type"], "database_connection_error")
        self.assertTrue(payload["event_id"])
        self.assertRegex(payload["event_id"], r"^[0-9a-f]{32}$")
        again = users_mod._database_unavailable_payload("down", "details")
        self.assertEqual(again["event_id"], payload["event_id"])


class TestQualityAlarmEngine(unittest.TestCase):
    """CA-OQ-09: ALM.QUALITY.<tag> ON on BAD/stale, OFF on GOOD."""

    def test_is_quality_subject_skips_system_and_filtered(self):
        from automation.utils.quality_alarms import is_quality_subject

        self.assertTrue(is_quality_subject(_make_tag("PV.Press")))
        self.assertFalse(is_quality_subject(_make_tag("SYS.CPU")))
        self.assertFalse(is_quality_subject(_make_tag("SYS.QUALITY.PV.Press")))
        self.assertFalse(is_quality_subject(_make_tag("ALM.QUALITY.PV.Press")))
        self.assertFalse(is_quality_subject(_make_tag("PV.Press.f")))

    def test_set_value_drives_quality_alarm_on_off(self):
        tag = _make_tag(name="Line.P")
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("automation.alarms.quality_gate.set_quality_degraded") as mocked:
            with patch("automation.alarms.quality_gate._emit_quality_event"):
                tag.set_value(value=42.0, timestamp=ts, quality=GOOD)
                mocked.assert_not_called()
                tag.set_value(value=0.0, timestamp=ts, quality=BAD)
                mocked.assert_called_with("Line.P", True)
                mocked.reset_mock()
                tag.set_value(value=43.0, timestamp=ts, quality=GOOD)
                mocked.assert_called_with("Line.P", False)

    def test_quality_alarm_returns_to_normal_when_pv_recovers(self):
        """ALM.QUALITY.* auto-acks to Normal; process BOOL stays RTN Unack."""
        from automation.alarms import Alarm
        from automation.models import FloatType, IntegerType, StringType
        from automation.tags.cvt import CVTEngine

        cvt = CVTEngine()
        cvt.set_tag(
            name="sys_quality_pi02",
            variable="Adimentional",
            unit="adim",
            data_type="boolean",
            description="quality bool",
        )
        tag = cvt.get_tag_by_name(name="sys_quality_pi02")
        alarm = Alarm(
            name="Supe.Linea2.ALM.QUALITY.Supe.Linea2.PI_02",
            tag=tag,
            alarm_type=StringType("BOOL"),
            alarm_setpoint=IntegerType(1),
            alarm_on_delay=FloatType(0.0),
            alarm_off_delay=FloatType(0.0),
        )
        alarm.enable_delay_wakeups = False
        tag.set_value(value=True)
        self.assertEqual(alarm.current_state.value.lower(), "unack_alarm")
        tag.set_value(value=False)
        self.assertEqual(alarm.current_state.value.lower(), "normal")


class TestInhibitUncertainCache(unittest.TestCase):
    """CA-OQ-11: Settings toggle applies hot via cache (no JSON on notify)."""

    def tearDown(self):
        from automation.signal_conditioning.quality import set_inhibit_uncertain_quality

        set_inhibit_uncertain_quality(False)

    def test_hot_cache_gates_uncertain(self):
        from automation.signal_conditioning.quality import (
            get_inhibit_uncertain_quality,
            set_inhibit_uncertain_quality,
        )

        set_inhibit_uncertain_quality(False)
        self.assertFalse(get_inhibit_uncertain_quality())
        self.assertTrue(is_process_alarm_allowed(UNCERTAIN, inhibit_uncertain=False))
        self.assertTrue(is_process_alarm_allowed(UNCERTAIN, inhibit_uncertain=get_inhibit_uncertain_quality()))
        set_inhibit_uncertain_quality(True)
        self.assertTrue(get_inhibit_uncertain_quality())
        self.assertFalse(is_process_alarm_allowed(UNCERTAIN, inhibit_uncertain=get_inhibit_uncertain_quality()))
        self.assertFalse(is_process_alarm_allowed(BAD, inhibit_uncertain=False))
        self.assertTrue(is_process_alarm_allowed(GOOD, inhibit_uncertain=True))


class TestHmiQualitySurfaces(unittest.TestCase):
    """CA-OQ-10 / CA-OQ-12: HMI artifacts present (static review)."""

    def _hmi(self, relative: str) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return (root / "hmi" / "src" / relative).read_text(encoding="utf-8")

    def test_login_shows_event_id(self):
        form = self._hmi("components/DatabaseConfigForm.tsx")
        self.assertIn("eventId", form)
        self.assertIn("databaseUnavailableWithEventId", form)
        login = self._hmi("pages/Login.tsx")
        self.assertIn("extractBackendEventId", login)
        self.assertIn("databaseEventId", login)

    def test_trends_and_datalogger_show_quality_legend(self):
        self.assertIn("HistoricalQualityLegend", self._hmi("pages/Trends.tsx"))
        self.assertIn("HistoricalQualityLegend", self._hmi("pages/DataLogger.tsx"))
        legend = self._hmi("components/HistoricalQualityLegend.tsx")
        self.assertIn("quality.historicalNone", legend)
        self.assertIn("QualityBadge", legend)

    def test_settings_uncertain_toggle(self):
        panel = self._hmi("components/QualityPolicyPanel.tsx")
        self.assertIn("alarm_inhibit_uncertain_quality", panel)
        self.assertIn("QualityPolicyPanel", self._hmi("pages/Settings.tsx"))


class TestSoakDocumented(unittest.TestCase):
    """CA-OQ-13…15: plant soak is a procedure, not a unit test."""

    def test_soak_runbook_lists_ca_oq_13_15(self):
        from pathlib import Path

        runbook = (
            Path(__file__).resolve().parents[2] / "docs" / "opc-quality-runbook.md"
        ).read_text(encoding="utf-8")
        self.assertIn("CA-OQ-13", runbook)
        self.assertIn("CA-OQ-14", runbook)
        self.assertIn("CA-OQ-15", runbook)

    @unittest.skip("Soak 24 h de planta — docs/opc-quality-runbook.md § 4")
    def test_ca_oq_13_intermittent_bad(self):
        self.fail("plant soak")

    @unittest.skip("Soak 24 h de planta — docs/opc-quality-runbook.md § 4")
    def test_ca_oq_14_opc_reconnect(self):
        self.fail("plant soak")

    @unittest.skip("Soak 24 h de planta — docs/opc-quality-runbook.md § 4")
    def test_ca_oq_15_historian_down(self):
        self.fail("plant soak")


if __name__ == "__main__":
    unittest.main()
