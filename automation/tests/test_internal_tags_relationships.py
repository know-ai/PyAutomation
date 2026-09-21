# -*- coding: utf-8 -*-
"""Cold start must not auto-subscribe leak inputs via internal_tags_relationships."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from .. import MANUFACTURER, SEGMENT
from ..models import ProcessType
from ..state_machine import Machine, StateMachineCore
from ..tags.cvt import CVTEngine


class _DisabledScope:
    enabled = False


class ProbeLeakMachine(StateMachineCore):
    def __init__(self, name: str, field_tag: str):
        super().__init__(name=name, classification="Leak Detection")
        self.inlet_flow = ProcessType(read_only=True, unit="kg/sec")
        self.leak_flow = ProcessType(read_only=False, unit="kg/sec")
        self.internal_tags_relationships = {
            "inlet_flow": {"tag": field_tag, "description": "Inlet Flow"},
        }


class TestInternalTagsRelationships(unittest.TestCase):
    def test_cold_start_creates_field_tags_without_subscribing_inputs(self):
        suffix = uuid4().hex[:8]
        field_tag = f"FI_COLD_{suffix}"
        machine = ProbeLeakMachine(name=f"LDS_COLD_{suffix}", field_tag=field_tag)
        mgr = Machine()
        cvt = CVTEngine()

        def _create_tag_stub(**kwargs):
            tag, msg = cvt.set_tag(
                name=kwargs["name"],
                unit=kwargs["unit"],
                data_type=kwargs.get("data_type", "float"),
                variable=kwargs["variable"],
                description=kwargs.get("description") or "",
                segment=kwargs.get("segment"),
                manufacturer=kwargs.get("manufacturer"),
            )
            return tag, msg

        mock_app = MagicMock()
        mock_app.create_tag.side_effect = _create_tag_stub

        with patch(
            "automation.node_scope.get_node_scope", return_value=_DisabledScope()
        ), patch(
            "automation.state_machine.PyAutomation", return_value=mock_app
        ), patch.object(mgr, "logger_engine", MagicMock()), patch.object(
            mgr, "db_manager", MagicMock()
        ), patch.object(mgr, "create_alarm", MagicMock()):
            mgr.create_tag_internal_process_type(machine)

        self.assertIsNone(machine.inlet_flow.tag)
        self.assertEqual(machine.get_subscribed_tags(), {})
        self.assertIn("inlet_flow", machine.get_not_subscribed_tags())
        expected_field_name = field_tag
        if SEGMENT:
            expected_field_name = f"{SEGMENT}.{expected_field_name}"
        if MANUFACTURER:
            expected_field_name = f"{MANUFACTURER}.{expected_field_name}"
        self.assertIsNotNone(machine.leak_flow.tag)
        self.assertIsNotNone(cvt.get_tag_by_name(name=expected_field_name))

    def test_multiple_engines_get_distinct_output_tags(self):
        suffix = uuid4().hex[:8]
        mgr = Machine()
        cvt = CVTEngine()

        class Engine(StateMachineCore):
            def __init__(self, engine_name: str):
                super().__init__(name=engine_name, classification="Leak Detection")
                self.leak = ProcessType(read_only=False, unit="adim")

        def _create_tag_stub(**kwargs):
            tag, msg = cvt.set_tag(
                name=kwargs["name"],
                unit=kwargs["unit"],
                data_type=kwargs.get("data_type", "float"),
                variable=kwargs["variable"],
                description=kwargs.get("description") or "",
                display_name=kwargs.get("display_name"),
                segment=kwargs.get("segment"),
                manufacturer=kwargs.get("manufacturer"),
            )
            return tag, msg

        mock_app = MagicMock()
        mock_app.create_tag.side_effect = _create_tag_stub

        with patch(
            "automation.node_scope.get_node_scope", return_value=_DisabledScope()
        ), patch(
            "automation.state_machine.PyAutomation", return_value=mock_app
        ), patch.object(mgr, "logger_engine", MagicMock()), patch.object(
            mgr, "db_manager", MagicMock()
        ), patch.object(mgr, "create_alarm", MagicMock()):
            for engine_name in (f"ENG_A_{suffix}", f"ENG_B_{suffix}"):
                mgr.create_tag_internal_process_type(Engine(engine_name))

        self.assertIsNotNone(cvt.get_tag_by_name(name=f"ENG_A_{suffix}.leak"))
        self.assertIsNotNone(cvt.get_tag_by_name(name=f"ENG_B_{suffix}.leak"))
