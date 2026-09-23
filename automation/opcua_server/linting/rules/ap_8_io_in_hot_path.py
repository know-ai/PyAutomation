"""AP-8: database, disk and audit I/O stay out of the tick."""

from __future__ import annotations

import ast

from ..rule import LintRule
from ..walk import HOT_FUNCTIONS, call_name, functions
from ...registry import register_lint_rule

_FORBIDDEN = (
    "persist_system_event",
    "execute_sql",
    "get_or_none",
    "urlopen",
    "audit_failure",
)


@register_lint_rule
class IoInHotPathRule(LintRule):
    rule_id = "AP-8"
    description = "I/O call inside the OPC UA hot path"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for func in functions(tree):
            if func.name not in HOT_FUNCTIONS:
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                name = call_name(node)
                if any(item in name for item in _FORBIDDEN) or name == "open":
                    found.append(self._hit(file, node, self.description))
        return found
