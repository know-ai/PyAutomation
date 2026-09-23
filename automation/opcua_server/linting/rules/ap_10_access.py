"""AP-10: access terminology, a null subscription handler, and CVT writes in the loop."""

from __future__ import annotations

import ast
import pathlib

from ..rule import LintRule
from ..walk import call_name
from ...registry import register_lint_rule

_FORBIDDEN = ("access" + "_type", "Access" + "Type")
_SKIP = {"venv", "__pycache__", "node_modules", "assets", "dist", "site-packages", ".git"}
_SUFFIXES = {".py", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml"}


def forbidden_in(text: str) -> str | None:
    """Return the first forbidden term, or None. Complexity: O(N)."""
    for term in _FORBIDDEN:
        if term in text:
            return term
    return None


def scan_sources(root: pathlib.Path) -> list[str]:
    """Walk source files. Complexity: O(files)."""
    hits = []
    if not root.exists():
        return hits
    for path in root.rglob("*"):
        if _SKIP.intersection(path.parts):
            continue
        if path.suffix not in _SUFFIXES or not path.is_file():
            continue
        term = forbidden_in(path.read_text(encoding="utf-8", errors="ignore"))
        if term:
            hits.append(f"{path}: {term}")
    return hits


@register_lint_rule
class AccessWriteGateRule(LintRule):
    rule_id = "AP-10"
    description = "null subscription handler, CVT write inside the async handler, or retired access name"

    def check(self, tree: ast.AST, file: str) -> list:
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node)
            if name.endswith("create_subscription") and len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and arg.value is None:
                    found.append(self._hit(file, node, "create_subscription handler is None"))
            if "async_core/handlers.py" in file.replace("\\", "/") and name.endswith(
                ("set_value", "set_value_fast")
            ):
                found.append(self._hit(file, node, "CVT write inside the async handler"))
        path = pathlib.Path(file)
        if path.is_file():
            term = forbidden_in(path.read_text(encoding="utf-8", errors="ignore"))
            if term:
                found.append(self._hit(file, tree, f"retired name {term}"))
        return found
