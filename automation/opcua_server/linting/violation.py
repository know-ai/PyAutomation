"""A single lint finding."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    rule_id: str
    file: str
    line: int
    column: int
    message: str
