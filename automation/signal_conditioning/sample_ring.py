# -*- coding: utf-8 -*-
"""O(1) ring buffer for raw acquisition samples (value, timestamp, quality)."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Iterable


@dataclass(frozen=True)
class SamplePoint:
    value: float
    timestamp: datetime
    quality: float = 1.0


class SampleRing:
    """Thread-safe fixed-capacity ring; append is O(1)."""

    def __init__(self, capacity: int = 32):
        self._capacity = max(4, int(capacity))
        self._data: Deque[SamplePoint] = deque(maxlen=self._capacity)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def append(self, value: float, timestamp: datetime, quality: float = 1.0) -> None:
        point = SamplePoint(float(value), timestamp, float(quality))
        with self._lock:
            self._data.append(point)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def latest(self) -> SamplePoint | None:
        with self._lock:
            if not self._data:
                return None
            return self._data[-1]

    def snapshot(self) -> list[SamplePoint]:
        with self._lock:
            return list(self._data)

    def tail_values(self, n: int) -> list[float]:
        with self._lock:
            if n <= 0 or not self._data:
                return []
            items = list(self._data)[-n:]
            return [item.value for item in items]

    def extend_from_iterable(self, points: Iterable[SamplePoint]) -> None:
        with self._lock:
            for point in points:
                self._data.append(point)

    def resize(self, capacity: int) -> None:
        """Grow/shrink capacity keeping the most recent samples."""
        new_cap = max(4, int(capacity))
        with self._lock:
            if new_cap == self._capacity:
                return
            kept = list(self._data)[-new_cap:]
            self._capacity = new_cap
            self._data = deque(kept, maxlen=new_cap)
