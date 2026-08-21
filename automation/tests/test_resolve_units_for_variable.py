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


if __name__ == "__main__":
    unittest.main()
