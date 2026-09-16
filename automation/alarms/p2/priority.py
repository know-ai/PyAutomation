# -*- coding: utf-8 -*-
"""PriorityManager. Context: API. Complexity: O(1). SRP: solo priority."""
from __future__ import annotations

from .clock import SystemClock
from .constants import _PRIORITY_DEFAULT, _PRIORITY_MAX, _PRIORITY_MIN
from .events import MemoryEventLogger
from .repository import MemoryAlarmRepository


class PriorityManager:
    """Context: API. Complexity: O(1) UPDATE + 1 Event. INV-102 incremental dist."""

    def __init__(self, repo=None, events=None, clock=None):
        self._repo = repo or MemoryAlarmRepository()
        self._events = events or MemoryEventLogger(clock)
        self._clock = clock or SystemClock()
        self._distribution: dict[int, int] = {i: 0 for i in range(_PRIORITY_MIN, _PRIORITY_MAX + 1)}

    def get_priority(self, alarm_id) -> int:
        """Context: API. Complexity: O(1)."""
        return self._repo.get_priority(alarm_id)

    def set_priority(self, alarm_id, p: int, op_id: int = 0, reason: str = "") -> None:
        """Context: API. Complexity: O(1)."""
        if not _PRIORITY_MIN <= int(p) <= _PRIORITY_MAX:
            raise ValueError(f"priority {p} out of range [{_PRIORITY_MIN}, {_PRIORITY_MAX}]")
        with self._repo.transaction():
            old = self._repo.get_priority(alarm_id)
            self._repo.set_priority(alarm_id, int(p))
            if self._distribution.get(old, 0) > 0:
                self._distribution[old] -= 1
            self._distribution[int(p)] = self._distribution.get(int(p), 0) + 1
            self._events.log(
                name="ALM.PRIORITY.CHANGED",
                alarm_id=alarm_id,
                user_id=op_id,
                reason=reason,
                from_priority=old,
                to_priority=int(p),
                timestamp=self._clock.now(),
            )

    def distribution(self) -> dict[int, int]:
        """Context: API. Complexity: O(1) — 4 keys."""
        return dict(self._distribution)

    def hydrate(self, alarm_id, p: int) -> None:
        """Context: BG. Complexity: O(1). Load catalog into counters."""
        p = int(p) if p is not None else _PRIORITY_DEFAULT
        p = min(_PRIORITY_MAX, max(_PRIORITY_MIN, p))
        self._repo.set_priority(alarm_id, p)
        self._distribution[p] = self._distribution.get(p, 0) + 1
