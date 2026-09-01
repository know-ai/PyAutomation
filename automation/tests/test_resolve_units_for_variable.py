"""Unit resolution when changing a tag's engineering variable."""
from __future__ import annotations

import unittest

from automation.variables import resolve_units_for_variable


class TestResolveUnitsForVariable(unittest.TestCase):
    def test_keeps_requested_bbl_hr_on_volumetric_flow(self):
        unit, display = resolve_units_for_variable(
            "VolumetricFlow",
            requested_unit="bbl/hr",
            requested_display_unit="bbl/hr",
            current_unit="kg/day",
            current_display_unit="kg/day",
        )
        self.assertEqual(unit, "bbl/hr")
        self.assertEqual(display, "bbl/hr")

    def test_defaults_to_first_catalogue_unit_when_incompatible(self):
        unit, display = resolve_units_for_variable(
            "VolumetricFlow",
            requested_unit=None,
            requested_display_unit=None,
            current_unit="kg/day",
            current_display_unit="kg/hr",
        )
        self.assertEqual(unit, "bbl/day")
        self.assertEqual(display, "bbl/day")

    def test_keeps_current_when_still_valid(self):
        unit, display = resolve_units_for_variable(
            "VolumetricFlow",
            requested_unit=None,
            requested_display_unit=None,
            current_unit="m3/hr",
            current_display_unit="gal/min",
        )
        self.assertEqual(unit, "m3/hr")
        self.assertEqual(display, "gal/min")

    def test_rejects_unknown_variable(self):
        with self.assertRaises(KeyError):
            resolve_units_for_variable("NotAVariable")


class TestVariableForUnit(unittest.TestCase):
    def test_kg_sec_is_mass_flow(self):
        from automation.variables import variable_for_unit

        self.assertEqual(variable_for_unit("kg/sec"), "MassFlow")

    def test_pa_is_pressure(self):
        from automation.variables import variable_for_unit

        self.assertEqual(variable_for_unit("Pa"), "Pressure")

    def test_kg_m3_is_density(self):
        from automation.variables import variable_for_unit

        self.assertEqual(variable_for_unit("kg/m3"), "Density")

    def test_empty_unit(self):
        from automation.variables import variable_for_unit

        self.assertIsNone(variable_for_unit(""))
        self.assertIsNone(variable_for_unit(None))

    def test_flow_variables_are_interchangeable(self):
        from automation.variables import compatible_field_variables

        self.assertEqual(
            compatible_field_variables("MassFlow"),
            frozenset({"MassFlow", "VolumetricFlow"}),
        )
        self.assertEqual(
            compatible_field_variables("VolumetricFlow"),
            frozenset({"MassFlow", "VolumetricFlow"}),
        )
        self.assertEqual(compatible_field_variables("Pressure"), frozenset({"Pressure"}))

    def test_process_type_serialize_includes_variable(self):
        from automation.models import ProcessType

        serialized = ProcessType(read_only=True, unit="kg/sec").serialize()
        self.assertEqual(serialized["variable"], "MassFlow")
        serialized = ProcessType(read_only=True, unit="kg/m3").serialize()
        self.assertEqual(serialized["variable"], "Density")


if __name__ == "__main__":
    unittest.main()
