"""AP-9: a bare except that only passes hides failures."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ...registry import register_lint_rule


@register_lint_rule
class ExceptPassRule(LintRule):
    rule_id = "AP-9"
    description = "except handler whose body is only pass"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                found.append(self._hit(file, node, self.description))
        return found
