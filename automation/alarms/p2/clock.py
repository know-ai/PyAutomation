# -*- coding: utf-8 -*-
"""IClock. Context: COLD/BG/API (never HOT allocations). Complexity: O(1)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol


class IClock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


class SystemClock:
    """Context: COLD/BG/API. Complexity: O(1)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    """Context: API/tests. Complexity: O(1). Time travel for T-169/T-170."""

    def __init__(self, start: float = 1_000_000.0):
        self._mono = float(start)
        self._wall = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._wall

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._mono += float(seconds)
        from datetime import timedelta

        self._wall = self._wall + timedelta(seconds=float(seconds))
