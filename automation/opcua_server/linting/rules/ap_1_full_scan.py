"""AP-1: full catalog scan inside the tick."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import HOT_FUNCTIONS, functions
from ...registry import register_lint_rule

_MARKERS = ("iter_tags", "get_alarms", "get_machines")


@register_lint_rule
class FullScanInHotPathRule(LintRule):
    rule_id = "AP-1"
    description = "Full catalog scan inside the OPC UA hot path"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for func in functions(tree):
            if func.name not in HOT_FUNCTIONS:
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.For):
                    continue
                source = ast.unparse(node.iter)
                if any(marker in source for marker in _MARKERS):
                    found.append(self._hit(file, node, self.description))
        return found
