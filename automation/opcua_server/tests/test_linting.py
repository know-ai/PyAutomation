"""Lint rules: positive and negative snippets, noqa, and a clean package."""

import ast
import pathlib
import textwrap
import time
import unittest

from automation.opcua_server.linting.rule import LintRule
from automation.opcua_server.linting.runner import run_rules
from automation.opcua_server.registry import lint_registry

PACKAGE = pathlib.Path(__file__).resolve().parents[1]


def _parse(source: str) -> ast.AST:
    return ast.parse(textwrap.dedent(source))


class TestLinting(unittest.TestCase):
    def test_rules_are_registered(self):
        rules = lint_registry.all()
        ids = {rule.rule_id for rule in rules}
        self.assertTrue({"AP-1", "AP-2", "AP-3", "AP-4", "AP-5", "AP-7", "AP-8", "AP-9"} <= ids)
        for rule in rules:
            self.assertIsInstance(rule, LintRule)

    def test_each_rule_has_a_positive_and_a_negative_case(self):
        samples = {
            "AP-1": (
                "def process_one_tick():\n    for tag in cvt.iter_tags():\n        pass\n",
                "def process_one_tick():\n    return 1\n",
            ),
            "AP-2": (
                "def load():\n    for node in nodes:\n        get_opcua_server_record_by_namespace(node)\n",
                "def load():\n    rows = read_by_namespaces(nodes)\n",
            ),
            "AP-3": (
                "def subscribe():\n    server.create_subscription(100, handler)\n",
                "def _ensure_write_subscription():\n    server.create_subscription(100, handler)\n",
            ),
            "AP-4": (
                "def store():\n    setattr(self, 'n', node)\n",
                "def store():\n    self._ua_nodes['a'] = node\n",
            ),
            "AP-5": (
                "from collections import deque\n\ndef q():\n    return deque()\n",
                "from collections import deque\n\ndef q():\n    return deque(maxlen=10)\n",
            ),
            "AP-7": (
                "import time\n\ndef while_running():\n    time.sleep(1)\n",
                "import time\n\ndef start_endpoint():\n    time.sleep(1)\n",
            ),
            "AP-8": (
                "def process_one_tick():\n    audit_failure('x', 'y')\n",
                "def process_one_tick():\n    return 1\n",
            ),
            "AP-9": (
                "def run():\n    try:\n        work()\n    except Exception:\n        pass\n",
                "def run():\n    try:\n        work()\n    except Exception:\n        log('x')\n",
            ),
        }
        by_id = {rule.rule_id: rule for rule in lint_registry.all()}
        for rule_id, (bad, good) in samples.items():
            self.assertTrue(by_id[rule_id].check(_parse(bad), "bad.py"), rule_id)
            self.assertEqual(by_id[rule_id].check(_parse(good), "good.py"), [], rule_id)

    def test_package_is_clean(self):
        self.assertEqual(run_rules(PACKAGE), [])

    def test_runner_is_fast_enough_for_the_package(self):
        started = time.perf_counter()
        run_rules(PACKAGE)
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_noqa_suppresses_a_line(self):
        path = PACKAGE / "_lint_noqa_probe.py"
        path.write_text("def process_one_tick():\n    audit_failure('x', 'y')  # noqa: AP-8\n", encoding="utf-8")
        try:
            violations = [item for item in run_rules(PACKAGE) if item.file.endswith("_lint_noqa_probe.py")]
            self.assertEqual(violations, [])
        finally:
            path.unlink(missing_ok=True)
