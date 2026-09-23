# -*- coding: utf-8 -*-
"""UNIT_ALIASES and SI subscription helper (spec 12 CA-UNIT-06/08/09)."""
from __future__ import annotations

import os
import unittest

from ..utils.unit_metrics import get_units_mismatch_runtime, reset_unit_metrics
from ..utils.unit_symbols import UNIT_ALIASES, canonical_symbol
from ..variables import MassFlow, Pressure
from ..variables.units_contract import resolve_value_for_process_type


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


class TestUnitAliases(unittest.TestCase):
    def test_ca_unit_08_canonical_symbols(self):
        self.assertEqual(canonical_symbol("kg/s"), "kg/sec")
        self.assertEqual(canonical_symbol("m3/s"), "m3/sec")
        self.assertEqual(canonical_symbol("m³/s"), "m3/sec")
        self.assertEqual(canonical_symbol("°K"), "K")
        self.assertEqual(canonical_symbol("barg"), "bar")
        self.assertEqual(canonical_symbol("Pa"), "Pa")
        self.assertIn("kg/s", UNIT_ALIASES)

    def test_mass_flow_alias_converts(self):
        flow = MassFlow(value=2.0, unit="kg/s")
        self.assertEqual(flow.unit, "kg/sec")
        self.assertAlmostEqual(flow.convert("kg/sec"), 2.0)

    def test_barg_alias_converts_to_pa(self):
        pressure = Pressure(value=1.0, unit="barg")
        self.assertEqual(pressure.unit, "bar")
        self.assertGreater(pressure.convert("Pa"), 0)


class TestResolveValueForProcessType(unittest.TestCase):
    def setUp(self):
        reset_unit_metrics()

    def test_ca_unit_06_converts_to_process_type_unit(self):
        class _PT:
            unit = "Pa"
            tag = None

        sample = Pressure(value=1.0, unit="bar")
        resolve_value_for_process_type(sample, _PT(), mutate=True)
        self.assertEqual(sample.unit, "Pa")
        self.assertGreater(sample.value, 10000)

    def test_ca_unit_09_mismatch_increments(self):
        class _PT:
            unit = "Pa"
            tag = None

        class _Broken:
            unit = "nope"

            def change_unit(self, unit):
                raise KeyError(unit)

        before = get_units_mismatch_runtime()
        resolve_value_for_process_type(_Broken(), _PT(), mutate=True)
        self.assertEqual(get_units_mismatch_runtime(), before + 1)
