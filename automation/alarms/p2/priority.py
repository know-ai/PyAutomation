# -*- coding: utf-8 -*-
"""PriorityManager. Context: API. Complexity: O(1). SRP: solo priority."""
from __future__ import annotations

from .clock import SystemClock
from .constants import _PRIORITY_MAX, _PRIORITY_MIN, alarm_priority_or_default, coerce_alarm_priority
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
        p = coerce_alarm_priority(p)
        with self._repo.transaction():
            old = self._repo.get_priority(alarm_id)
            self._repo.set_priority(alarm_id, p)
            if self._distribution.get(old, 0) > 0:
                self._distribution[old] -= 1
            self._distribution[p] = self._distribution.get(p, 0) + 1
            self._events.log(
                name="ALM.PRIORITY.CHANGED",
                alarm_id=alarm_id,
                user_id=op_id,
                reason=reason,
                from_priority=old,
                to_priority=p,
                timestamp=self._clock.now(),
            )

    def distribution(self) -> dict[int, int]:
        """Context: API. Complexity: O(1) — 4 keys."""
        return dict(self._distribution)

    def hydrate(self, alarm_id, p: int) -> None:
        """Context: BG. Complexity: O(1). Load catalog into counters."""
        p = alarm_priority_or_default(p)
        self._repo.set_priority(alarm_id, p)
        self._distribution[p] = self._distribution.get(p, 0) + 1
