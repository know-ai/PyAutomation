# -*- coding: utf-8 -*-
"""EngUnit.convert / Tag.get_value must not KeyError on unit desync (empty-DB boot)."""
from __future__ import annotations

import os
import unittest

from ..tags.tag import Tag
from ..tags.unit_provenance import align_tag_to_persisted_units
from ..utils.unit_symbols import canonical_symbol
from ..utils.units import UnitError
from ..variables.density import Density
from ..variables.length import Length
from ..variables.volume import Volume


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


class TestEngUnitConvertSafe(unittest.TestCase):
    def test_same_unit_short_circuit(self):
        vol = Volume(value=2.5, unit="m3")
        self.assertAlmostEqual(vol.convert("m3"), 2.5)
        self.assertAlmostEqual(Volume.convert_value(2.5, "m3", "m3"), 2.5)

    def test_unknown_to_unit_raises_unit_error(self):
        length = Length(value=1.0, unit="m")
        with self.assertRaises(UnitError) as ctx:
            length.convert("m3")
        self.assertIn("m3", str(ctx.exception))

    def test_m3_superscript_alias(self):
        self.assertEqual(canonical_symbol("m³"), "m3")
        vol = Volume(value=1.0, unit="m³")
        self.assertEqual(vol.unit, "m3")
        self.assertAlmostEqual(vol.convert("m3"), 1.0)


class TestTagGetValueFailSafe(unittest.TestCase):
    def test_get_value_survives_display_unit_desync(self):
        tag = Tag(
            name="t.desync",
            unit="m",
            variable="Length",
            data_type="float",
            display_unit="m",
        )
        # Poison display_unit the way a stale catalog FK used to.
        tag.display_unit = "m3"
        self.assertAlmostEqual(tag.get_value(), 0.0)

    def test_set_display_unit_rejects_incompatible(self):
        tag = Tag(
            name="t.length",
            unit="m",
            variable="Length",
            data_type="float",
            display_unit="m",
        )
        tag.set_display_unit("m3")
        self.assertEqual(tag.display_unit, "m")

    def test_align_skips_poisoned_display_unit(self):
        tag = Tag(
            name="t.align",
            unit="m",
            variable="Length",
            data_type="float",
            display_unit="m",
        )
        align_tag_to_persisted_units(tag, unit="m", display_unit="m3")
        self.assertEqual(tag.display_unit, "m")
        self.assertAlmostEqual(tag.get_value(), 0.0)

    def test_volume_m3_serializes(self):
        tag = Tag(
            name="t.volume",
            unit="m3",
            variable="Volume",
            data_type="float",
            display_unit="m3",
        )
        payload = tag.serialize()
        self.assertAlmostEqual(payload["value"], 0.0)
        self.assertEqual(payload["display_unit"], "m3")


if __name__ == "__main__":
    unittest.main()
