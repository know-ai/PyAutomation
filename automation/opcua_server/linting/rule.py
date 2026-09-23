"""Lint rule contract. check is O(nodes)."""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod

from .violation import Violation


class LintRule(ABC):
    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Stable identifier, for example AP-1."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""

    @abstractmethod
    def check(self, tree: ast.AST, file: str) -> list[Violation]:
        """Return violations found in the AST."""

    def _hit(self, file: str, node: ast.AST, message: str) -> Violation:
        return Violation(
            rule_id=self.rule_id,
            file=file,
            line=getattr(node, "lineno", 1),
            column=getattr(node, "col_offset", 0),
            message=message,
        )
