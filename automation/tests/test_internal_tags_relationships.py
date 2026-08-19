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

        with patch(
            "automation.node_scope.get_node_scope", return_value=_DisabledScope()
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
