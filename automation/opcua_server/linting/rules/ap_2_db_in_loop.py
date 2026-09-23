"""AP-2: a database lookup inside a loop."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import call_name, functions
from ...registry import register_lint_rule

_MARKER = "get_opcua_server_record_by_namespace"


@register_lint_rule
class DbInLoopRule(LintRule):
    rule_id = "AP-2"
    description = "Per-node database read inside a loop"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for func in functions(tree):
            for node in ast.walk(func):
                if not isinstance(node, ast.For):
                    continue
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) and _MARKER in call_name(inner):
                        found.append(self._hit(file, inner, self.description))
        return found
