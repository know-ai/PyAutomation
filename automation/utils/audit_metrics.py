# -*- coding: utf-8 -*-
"""Event-rate observability and anti-spam cooldowns for the audit trail.

Does not import the event store. Safe to call from journal, HTTP and loggers.
"""
from __future__ import annotations

import threading
import time
from collections import deque

EVENTS_ALERT_PER_MIN = 30.0
_WINDOW_S = 60.0

_lock = threading.Lock()
_times: deque[float] = deque()
_cooldowns: dict[str, float] = {}


def note_event_persisted() -> None:
    now = time.monotonic()
    with _lock:
        _times.append(now)
        _prune_locked(now)


def events_rate_per_min() -> float:
    now = time.monotonic()
    with _lock:
        _prune_locked(now)
        return float(len(_times))


def snapshot() -> dict:
    rate = events_rate_per_min()
    return {
        "EVENTS_RATE_PER_MIN": round(rate, 2),
        "EVENTS_RATE_ALERT": bool(rate > EVENTS_ALERT_PER_MIN),
        "EVENTS_RATE_ALERT_THRESHOLD": EVENTS_ALERT_PER_MIN,
    }


def cooldown_allows(key: str, seconds: float) -> bool:
    """True once, then False until ``seconds`` elapse for the same key."""
    if seconds <= 0:
        return True
    now = time.monotonic()
    with _lock:
        last = _cooldowns.get(key)
        if last is not None and (now - last) < seconds:
            return False
        _cooldowns[key] = now
        if len(_cooldowns) > 256:
            oldest = min(_cooldowns, key=_cooldowns.get)
            _cooldowns.pop(oldest, None)
        return True


def reset_audit_metrics() -> None:
    """Test helper."""
    with _lock:
        _times.clear()
        _cooldowns.clear()


def _prune_locked(now: float) -> None:
    cutoff = now - _WINDOW_S
    while _times and _times[0] < cutoff:
        _times.popleft()
