"""Shared AST helpers for the OPC UA lint rules."""

from __future__ import annotations

import ast

HOT_FUNCTIONS = frozenset(
    {
        "while_running",
        "while_starting",
        "process_one_tick",
        "_update_tags",
        "__update_tags",
        "_update_alarms",
        "__update_alarms",
        "_update_engines",
        "__update_engines",
    }
)


def functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return ast.unparse(node.func)
    return ""
