"""AP-7: sleep does not belong in the state-machine hot methods."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import call_name, functions
from ...registry import register_lint_rule

_HOT = frozenset({"while_running", "while_starting"})


@register_lint_rule
class SleepInHotPathRule(LintRule):
    rule_id = "AP-7"
    description = "time.sleep inside while_running or while_starting"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for func in functions(tree):
            if func.name not in _HOT:
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and call_name(node).endswith("sleep"):
                    found.append(self._hit(file, node, self.description))
        return found
