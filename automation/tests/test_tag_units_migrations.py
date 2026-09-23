# -*- coding: utf-8 -*-
"""Opt-in unit migrations never touch operator rows (spec 12 CA-UNIT-10)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from ..migrations.unit_migrations import (
    APPLY_ENV,
    apply_unit_migrations,
    dry_run_unit_migrations,
)
from ..utils.ops_controls import OpsControlError


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


def _row(name, unit_sym, source=None):
    unit = MagicMock()
    unit.unit = unit_sym
    row = MagicMock()
    row.name = name
    row.unit = unit
    row.display_unit = unit
    row.unit_source = source
    row.id = 1
    return row


class TestUnitMigrations(unittest.TestCase):
    def test_dry_run_skips_operator(self):
        engine = _row("LINE.PI_01", "bar", source=None)
        operator = _row("LINE.PI_02", "bar", source="operator")
        with patch(
            "automation.migrations.unit_migrations._iter_tag_rows",
            return_value=[engine, operator],
        ):
            report = dry_run_unit_migrations()
        names = {c["name"] for c in report["changes"]}
        self.assertIn("LINE.PI_01", names)
        self.assertNotIn("LINE.PI_02", names)
        self.assertGreaterEqual(report["skipped_operator"], 1)
        self.assertFalse(report["applied"])

    def test_apply_requires_confirm(self):
        os.environ.pop(APPLY_ENV, None)
        with self.assertRaises(OpsControlError):
            apply_unit_migrations(confirm=False)

    def test_ca_unit_10_apply_never_operator(self):
        engine = _row("LINE.PI_01", "bar", source="engine")
        operator = _row("LINE.PI_02", "bar", source="operator")
        dest = MagicMock()
        with patch(
            "automation.migrations.unit_migrations._iter_tag_rows",
            return_value=[engine, operator],
        ), patch("automation.dbmodels.tags.Tags") as tags_mod, patch(
            "automation.dbmodels.tags.Units"
        ) as units_mod, patch(
            "automation.migrations.unit_migrations.persist_system_event"
        ), patch(
            "automation.migrations.unit_migrations.PyAutomation", create=True
        ):
            tags_mod.get_or_none.side_effect = lambda expr: engine
            units_mod.read_by_unit.return_value = dest
            report = apply_unit_migrations(confirm=True)
        self.assertTrue(report["applied"])
        self.assertTrue(tags_mod.put.called)
        names = {c["name"] for c in report["changes"]}
        self.assertIn("LINE.PI_01", names)
        self.assertNotIn("LINE.PI_02", names)

    def test_dry_run_skips_fi_already_kgsec(self):
        done = _row("Supe.Linea1.FI_01", "kg/sec", source="engine")
        with patch(
            "automation.migrations.unit_migrations._iter_tag_rows",
            return_value=[done],
        ):
            report = dry_run_unit_migrations()
        self.assertEqual(report["count"], 0)

    def test_dry_run_plans_fi_literal_kgs(self):
        pending = _row("Supe.Linea1.FI_02", "kg/s", source="engine")
        with patch(
            "automation.migrations.unit_migrations._iter_tag_rows",
            return_value=[pending],
        ):
            report = dry_run_unit_migrations()
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["changes"][0]["from_unit"], "kg/s")
        self.assertEqual(report["changes"][0]["to_unit"], "kg/sec")
