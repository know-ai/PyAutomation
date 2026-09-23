"""AP-5: every deque needs a maxlen."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import call_name
from ...registry import register_lint_rule


@register_lint_rule
class UnboundedDequeRule(LintRule):
    rule_id = "AP-5"
    description = "deque() without maxlen"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node)
            if name != "deque" and not name.endswith(".deque"):
                continue
            if any(keyword.arg == "maxlen" for keyword in node.keywords):
                continue
            found.append(self._hit(file, node, self.description))
        return found
