# -*- coding: utf-8 -*-
"""EngUnit / variable consistency and cross-DB unit FK safety."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ..catalog.rows import _resolve_tag_unit_fks
from ..tags.tag import Tag
from ..tags.unit_provenance import (
    align_tag_to_persisted_units,
    historian_units_need_engine_repair,
    tag_eng_accepts_symbol,
)
from ..variables import unit_belongs_to_variable


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


class TestVariableUnitConsistency(unittest.TestCase):
    def test_adim_only_for_adimentional(self):
        self.assertTrue(unit_belongs_to_variable("adim", "Adimentional"))
        self.assertFalse(unit_belongs_to_variable("m3", "Adimentional"))
        self.assertFalse(unit_belongs_to_variable("mW", "Adimentional"))

    def test_m3_is_volume_not_power(self):
        self.assertTrue(unit_belongs_to_variable("m3", "Volume"))
        self.assertFalse(unit_belongs_to_variable("m3", "Power"))
        self.assertTrue(unit_belongs_to_variable("mW", "Power"))
        self.assertTrue(unit_belongs_to_variable("MW", "Power"))

    def test_percent_is_percentage(self):
        self.assertTrue(unit_belongs_to_variable("%", "Percentage"))
        self.assertFalse(unit_belongs_to_variable("gal", "Percentage"))


class TestAlignRefusesPoison(unittest.TestCase):
    def test_adimentional_keeps_adim_when_hist_says_m3(self):
        tag = Tag(
            name="Linea1.SYS.CATALOG.Conflict",
            unit="adim",
            variable="Adimentional",
            data_type="float",
            display_unit="adim",
        )
        align_tag_to_persisted_units(tag, unit="m3", display_unit="m3")
        self.assertEqual(tag.unit, "adim")
        self.assertEqual(tag.display_unit, "adim")
        self.assertFalse(tag_eng_accepts_symbol(tag, "m3"))

    def test_historian_repair_flag(self):
        tag = Tag(
            name="t.sys",
            unit="adim",
            variable="Adimentional",
            data_type="float",
            display_unit="adim",
        )
        row = SimpleNamespace(
            unit=SimpleNamespace(unit="m3"),
            display_unit=SimpleNamespace(unit="m3"),
            unit_source="engine",
            unit_locked_at=None,
        )
        self.assertTrue(historian_units_need_engine_repair(tag, row))


class TestResolveTagUnitFksPreferSymbol(unittest.TestCase):
    def test_symbol_wins_over_foreign_integer(self):
        raw = {"unit": "adim", "unit_id": 168, "display_unit": "adim", "display_unit_id": 168}
        with patch(
            "automation.catalog.seed._find_unit_by_symbol",
            side_effect=lambda s: {"_pk": 1, "id": 1, "unit": s},
        ), patch(
            "automation.catalog.seed.ensure_unit_symbol",
            side_effect=lambda s, variable=None: {"_pk": 1, "id": 1, "unit": s},
        ):
            out = _resolve_tag_unit_fks(raw)
        self.assertEqual(out["unit"], 1)
        self.assertEqual(out["unit_id"], 1)


if __name__ == "__main__":
    unittest.main()
