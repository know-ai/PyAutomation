# -*- coding: utf-8 -*-
"""MassFlow conversion table must cover every declared unit (startup serialize)."""
from __future__ import annotations

import unittest

from automation.variables.mass_flow import MassFlow


class TestMassFlowConversions(unittest.TestCase):
    def test_every_declared_unit_has_a_conversion_factor(self):
        missing = [unit for unit in MassFlow.Units.list() if unit not in MassFlow.conversions]
        self.assertEqual(missing, [], msg=f"MassFlow.conversions missing {missing}")

    def test_mg_sec_converts_to_kg_sec(self):
        flow = MassFlow(value=1.0, unit="mg/sec")
        self.assertAlmostEqual(flow.convert(to_unit="kg/sec"), 1e-6)

    def test_mg_min_is_not_overwritten_by_mg_sec(self):
        per_min = MassFlow.conversions["mg/min"]
        per_sec = MassFlow.conversions["mg/sec"]
        self.assertAlmostEqual(per_min / per_sec, 60.0)


class TestDefineIadAlarmsNoneTags(unittest.TestCase):
    def test_define_iad_alarms_tolerates_get_tags_none(self):
        from unittest.mock import MagicMock, patch

        from automation.state_machine import Machine

        manager = Machine.__new__(Machine)
        fake_cvt = MagicMock()
        fake_cvt.get_tags.return_value = None
        with patch("automation.state_machine.CVTEngine", return_value=fake_cvt):
            manager._Machine__define_iad_alarms()
