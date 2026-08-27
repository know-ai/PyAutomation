# -*- coding: utf-8 -*-
"""Gevent hub lag probe. Runs as a greenlet, never on the acquisition OS threads."""
from __future__ import annotations

import logging
import os
import threading
import time

_LOGGER = logging.getLogger("pyautomation")
_lock = threading.Lock()
_hub_lag_s = 0.0
_high_streak = 0
_started = False

DEFAULT_CRITICAL_S = 2.0
DEFAULT_STREAK = 3
_WATCH_INTERVAL_S = 0.05


def snapshot_hub_lag_ms() -> float:
    with _lock:
        return round(max(0.0, _hub_lag_s) * 1000.0, 1)


def start_hub_lag_watch() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    try:
        import gevent
    except Exception:
        _LOGGER.debug("hub lag watch skipped (no gevent)", exc_info=True)
        return

    def _loop():
        global _hub_lag_s, _high_streak
        while True:
            started = time.monotonic()
            gevent.sleep(_WATCH_INTERVAL_S)
            lag = max(0.0, time.monotonic() - started - _WATCH_INTERVAL_S)
            with _lock:
                _hub_lag_s = lag
            _maybe_recycle(lag)

    gevent.spawn(_loop)


def _maybe_recycle(lag_s: float) -> None:
    global _high_streak
    threshold = DEFAULT_CRITICAL_S
    try:
        threshold = float(os.environ.get("AUTOMATION_HUB_LAG_CRITICAL_S", str(DEFAULT_CRITICAL_S)))
    except (TypeError, ValueError):
        threshold = DEFAULT_CRITICAL_S
    if lag_s >= threshold:
        _high_streak += 1
    else:
        _high_streak = 0
        return
    if _high_streak < DEFAULT_STREAK:
        return
    _LOGGER.critical(
        "Hub event-loop lag %.3fs over %.3fs for %s samples; HMI on.tag is stalled",
        lag_s,
        threshold,
        _high_streak,
    )
    raw = os.environ.get("AUTOMATION_HUB_LAG_RECYCLE", "0").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return
    _LOGGER.critical("Recycle gunicorn worker (AUTOMATION_HUB_LAG_RECYCLE)")
    os._exit(75)
