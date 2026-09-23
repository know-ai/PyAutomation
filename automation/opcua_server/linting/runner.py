"""Run every registered lint rule. New rules do not edit this module."""

from __future__ import annotations

import ast
import pathlib

from ..registry import lint_registry
from . import rules as _rules

del _rules

_EXCLUDED = {"tests", "benchmarks"}


def _is_excluded(path: pathlib.Path) -> bool:
    return bool(_EXCLUDED.intersection(path.parts))


def _suppressed(lines: list[str], line: int, rule_id: str) -> bool:
    if line < 1 or line > len(lines):
        return False
    text = lines[line - 1]
    return f"noqa: {rule_id}" in text


def run_rules(package_root: pathlib.Path) -> list:
    """O(nodes) over the package. Tests and benchmarks are excluded."""
    violations = []
    rules = lint_registry.all()
    for path in sorted(package_root.rglob("*.py")):
        if _is_excluded(path):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for rule in rules:
            for violation in rule.check(tree, str(path)):
                if _suppressed(lines, violation.line, violation.rule_id):
                    continue
                violations.append(violation)
    return violations
