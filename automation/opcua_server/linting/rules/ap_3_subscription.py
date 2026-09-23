"""AP-3: create_subscription only inside the shared factory."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import call_name, functions
from ...registry import register_lint_rule

_FACTORY = "_ensure_write_subscription"


@register_lint_rule
class SubscriptionOutsideFactoryRule(LintRule):
    rule_id = "AP-3"
    description = "create_subscription outside the shared write subscription factory"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for func in functions(tree):
            if func.name == _FACTORY:
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and call_name(node).endswith("create_subscription"):
                    found.append(self._hit(file, node, self.description))
        return found
