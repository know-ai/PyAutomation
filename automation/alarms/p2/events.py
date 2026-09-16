# -*- coding: utf-8 -*-
"""IEventLogger. Context: COLD/API. Complexity: O(1). Collection: deque(maxlen=_EVENT_LOG_MAX)."""
from __future__ import annotations

from collections import deque
from typing import Any

from .clock import SystemClock
from .constants import _EVENT_LOG_MAX


class MemoryEventLogger:
    """Context: COLD/API. Complexity: O(1) append."""

    def __init__(self, clock=None):
        self._clock = clock or SystemClock()
        self._events: deque[dict[str, Any]] = deque(maxlen=_EVENT_LOG_MAX)

    def log(self, name: str, **fields: Any) -> None:
        payload = {"name": name, "timestamp": self._clock.now(), **fields}
        self._events.append(payload)

    def last(self) -> dict[str, Any] | None:
        return self._events[-1] if self._events else None

    def __len__(self) -> int:
        return len(self._events)
