# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import tempfile
import unittest

from automation.modules.settings.machines_summary_columns import (
    DEFAULT_COLUMNS,
    PATH,
    load_machines_summary_columns,
    sanitize_columns,
    save_machines_summary_columns,
)


class TestMachinesSummaryColumns(unittest.TestCase):
    def test_locked_columns_stay_first_and_unique(self):
        columns = sanitize_columns(
            {"columns": ["description", "name", "leak_likelihood", "state", "description", "bad key", ""]}
        )
        self.assertEqual(columns[:2], ["name", "state"])
        self.assertEqual(columns.count("description"), 1)
        self.assertIn("leak_likelihood", columns)
        self.assertNotIn("bad key", columns)

    def test_missing_file_uses_defaults(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                document = load_machines_summary_columns()
            finally:
                os.chdir(cwd)
        self.assertEqual(document["columns"], list(DEFAULT_COLUMNS))

    def test_save_roundtrip(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                saved = save_machines_summary_columns(
                    {"columns": ["priority", "state", "inlet_pressure"]}
                )
                self.assertTrue(os.path.isfile(PATH))
                with open(PATH, encoding="utf-8") as handle:
                    on_disk = json.load(handle)
                loaded = load_machines_summary_columns()
            finally:
                os.chdir(cwd)
        self.assertEqual(saved["columns"], ["name", "state", "priority", "inlet_pressure"])
        self.assertEqual(on_disk["kind"], "machines-summary")
        self.assertEqual(loaded["columns"], saved["columns"])
