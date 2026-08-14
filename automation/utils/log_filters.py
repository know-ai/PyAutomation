# -*- coding: utf-8 -*-
"""Rate-limit / dedupe for application logs (Operación «Log Eterno»).

A ``logging.Filter`` decides whether a record is written. It does not change
the message. Cost is O(1) dict lookup; the cache is bounded.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict, deque
from typing import Optional

DEFAULT_COOLDOWN_S = 60.0
DEFAULT_MAX_ENTRIES = 1000
DEFAULT_RATE_WINDOW_S = 60.0
DEFAULT_ERROR_ALERT_PER_MIN = 5.0

_active_filter: Optional["DedupeFilter"] = None
_active_lock = threading.Lock()


def get_dedupe_filter() -> Optional["DedupeFilter"]:
    with _active_lock:
        return _active_filter


def set_dedupe_filter(filt: Optional["DedupeFilter"]) -> None:
    global _active_filter
    with _active_lock:
        _active_filter = filt


class DedupeFilter(logging.Filter):
    """Drop repeated ERROR+ records during ``cooldown`` seconds.

    ``cooldown_sec=0`` disables suppression (development). Cache size is
    capped at ``max_entries`` (LRU). ERROR/CRITICAL attempts are counted
    even when suppressed so ``error_rate_per_min`` still alerts.
    """

    def __init__(
        self,
        cooldown_sec: float = DEFAULT_COOLDOWN_S,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        name: str = "",
        rate_window_s: float = DEFAULT_RATE_WINDOW_S,
        alert_per_min: float = DEFAULT_ERROR_ALERT_PER_MIN,
    ):
        super().__init__(name)
        self.cooldown = max(0.0, float(cooldown_sec))
        self._max = max(1, int(max_entries))
        self._rate_window_s = max(1.0, float(rate_window_s))
        self.alert_per_min = float(alert_per_min)
        self._lock = threading.Lock()
        self._last: OrderedDict = OrderedDict()
        self._error_times: deque = deque()
        self._suppressed_times: deque = deque()
        self.dropped = 0

    def set_cooldown(self, cooldown_sec: float) -> None:
        self.cooldown = max(0.0, float(cooldown_sec))

    def _prune_window(self, bucket: deque, now: float) -> None:
        cutoff = now - self._rate_window_s
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def error_rate_per_min(self) -> float:
        now = time.monotonic()
        with self._lock:
            self._prune_window(self._error_times, now)
            return float(len(self._error_times))

    def suppressed_rate_per_min(self) -> float:
        now = time.monotonic()
        with self._lock:
            self._prune_window(self._suppressed_times, now)
            return float(len(self._suppressed_times))

    def snapshot(self) -> dict:
        rate = self.error_rate_per_min()
        suppressed = self.suppressed_rate_per_min()
        return {
            "LOG_ERROR_RATE_PER_MIN": round(rate, 2),
            "LOG_ERROR_SUPPRESSED_PER_MIN": round(suppressed, 2),
            "LOG_ERROR_ALERT": bool(rate > self.alert_per_min),
            "LOG_ERROR_COOLDOWN_S": self.cooldown,
            "LOG_ERROR_DEDUPE_ENTRIES": len(self._last),
        }

    def filter(self, record: logging.LogRecord) -> bool:
        now_mono = time.monotonic()
        is_error = record.levelno >= logging.ERROR
        key = (record.pathname, record.lineno, record.funcName, record.getMessage())
        with self._lock:
            if is_error:
                self._error_times.append(now_mono)
                self._prune_window(self._error_times, now_mono)
            if self.cooldown <= 0:
                return True
            last = self._last.get(key)
            if last is not None and (now_mono - last) < self.cooldown:
                self.dropped += 1
                if is_error:
                    self._suppressed_times.append(now_mono)
                    self._prune_window(self._suppressed_times, now_mono)
                return False
            self._last[key] = now_mono
            self._last.move_to_end(key)
            while len(self._last) > self._max:
                self._last.popitem(last=False)
        return True
