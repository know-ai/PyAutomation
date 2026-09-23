"""AP-4: nodes must not be stored with setattr on the state machine."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import call_name
from ...registry import register_lint_rule


@register_lint_rule
class SetattrForUaNodesRule(LintRule):
    rule_id = "AP-4"
    description = "setattr(self, ...) stores a UA node on the state machine"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or call_name(node) != "setattr":
                continue
            if node.args and ast.unparse(node.args[0]) == "self":
                found.append(self._hit(file, node, self.description))
        return found
