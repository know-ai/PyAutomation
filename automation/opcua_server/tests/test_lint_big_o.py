"""AST lint for the OPC UA package. The runner is the source of truth."""

import pathlib
import unittest

from automation.opcua_server.linting.runner import run_rules

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestLintBigO(unittest.TestCase):
    def test_package_has_no_violations(self):
        violations = run_rules(PACKAGE_ROOT)
        rendered = [f"{item.rule_id}:{item.file}:{item.line}" for item in violations]
        self.assertEqual(rendered, [])
