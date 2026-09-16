# -*- coding: utf-8 -*-
"""Command pattern. Context: API. Complexity: O(1). Auditable, testeable."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AlarmAction:
    """Context: API. Complexity: O(1)."""

    name: str
    alarm_id: object
    operator_id: int = 0
    payload: dict | None = None
    executed: bool = False

    def execute(self, handler) -> None:
        handler(self)
        self.executed = True
