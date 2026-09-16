# -*- coding: utf-8 -*-
"""SuppressionCache TTL+LRU. Context: HOT lookup / COLD set. Complexity: O(1). INV-107."""
from __future__ import annotations

from collections import deque

from .clock import SystemClock
from .constants import _SUPPRESSION_CACHE_MAX, _SUPPRESSION_TTL_S


class SuppressionCache:
    """Context: HOT is_suppressed O(1). INV-107 maxsize=2000 TTL 60s."""

    _MAXSIZE = _SUPPRESSION_CACHE_MAX
    _TTL_S = _SUPPRESSION_TTL_S

    def __init__(self, clock=None):
        self._clock = clock or SystemClock()
        self._cache: dict[object, tuple[bool, float]] = {}
        self._lru: deque = deque(maxlen=self._MAXSIZE)

    def is_suppressed(self, alarm_id) -> bool:
        """Context: HOT. Complexity: O(1). No lock. No I/O."""
        entry = self._cache.get(alarm_id)
        if entry and self._clock.monotonic() - entry[1] < self._TTL_S:
            return bool(entry[0])
        return False

    def set(self, alarm_id, value: bool) -> None:
        """Context: COLD/API. Complexity: O(1)."""
        now = self._clock.monotonic()
        if alarm_id not in self._cache and len(self._cache) >= self._MAXSIZE:
            oldest = self._lru.popleft() if self._lru else None
            if oldest is not None:
                self._cache.pop(oldest, None)
        self._cache[alarm_id] = (bool(value), now)
        self._lru.append(alarm_id)

    def __len__(self) -> int:
        return len(self._cache)
