# -*- coding: utf-8 -*-
"""Gevent hub lag probe. Runs as a greenlet, never on the acquisition OS threads.

``snapshot_hub_lag_ms()`` is the delay of the *event-loop*, not the metrics
sampler. ``MetricsSamplerWorker`` is a ``threading.Thread``, but gunicorn
``gevent.monkey.patch_all()`` turns that into a hub greenlet: a 2 s sample
would look like sustained hub lag and flap ``ALM.PERF.HUB_LAG``. Sampler ticks
must wrap work in ``exclude_from_hub_lag()``.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager

_LOGGER = logging.getLogger("pyautomation")
_lock = threading.Lock()
_hub_lag_s = 0.0
_interval_started = 0.0
_paused_s = 0.0
_pause_started = 0.0
_pause_depth = 0
_high_streak = 0
_started = False

DEFAULT_CRITICAL_S = 2.0
DEFAULT_STREAK = 3
_WATCH_INTERVAL_S = 0.05


def _pause_open_s(now: float, pause_started: float) -> float:
    if pause_started <= 0.0:
        return 0.0
    return max(0.0, now - pause_started)


def snapshot_hub_lag_ms() -> float:
    """Last completed interval, plus in-flight overshoot, minus sampler pause."""
    now = time.monotonic()
    with _lock:
        last = max(0.0, _hub_lag_s)
        started = _interval_started
        paused_s = _paused_s
        pause_started = _pause_started
    inflight = 0.0
    if started > 0.0:
        inflight = max(
            0.0,
            now - started - _WATCH_INTERVAL_S - paused_s - _pause_open_s(now, pause_started),
        )
    return round(max(last, inflight) * 1000.0, 1)


def reset_hub_lag_for_tests() -> None:
    """Test helper: drop measured lag without touching the watch greenlet flag."""
    global _hub_lag_s, _interval_started, _paused_s, _pause_started, _pause_depth, _high_streak
    with _lock:
        _hub_lag_s = 0.0
        _interval_started = 0.0
        _paused_s = 0.0
        _pause_started = 0.0
        _pause_depth = 0
        _high_streak = 0


def inject_hub_lag_for_tests(*, lag_s: float = 0.0, interval_started: float | None = None) -> None:
    """Test helper: publish a lag sample (and optional in-flight sleep start)."""
    global _hub_lag_s, _interval_started, _paused_s, _pause_started, _pause_depth
    with _lock:
        _hub_lag_s = max(0.0, float(lag_s))
        _interval_started = 0.0 if interval_started is None else float(interval_started)
        _paused_s = 0.0
        _pause_started = 0.0
        _pause_depth = 0


def _begin_pause() -> None:
    global _pause_started, _pause_depth
    with _lock:
        if _pause_depth == 0:
            _pause_started = time.monotonic()
        _pause_depth += 1


def _end_pause() -> None:
    global _pause_started, _pause_depth, _paused_s
    now = time.monotonic()
    with _lock:
        if _pause_depth <= 0:
            return
        _pause_depth -= 1
        if _pause_depth == 0 and _pause_started > 0.0:
            _paused_s += max(0.0, now - _pause_started)
            _pause_started = 0.0


@contextmanager
def exclude_from_hub_lag():
    """Do not count this work as event-loop lag (metrics sampler tick)."""
    _begin_pause()
    try:
        yield
    finally:
        _end_pause()


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
        global _hub_lag_s, _interval_started, _paused_s
        while True:
            try:
                started = time.monotonic()
                with _lock:
                    _interval_started = started
                    _paused_s = 0.0
                gevent.sleep(_WATCH_INTERVAL_S)
                now = time.monotonic()
                with _lock:
                    paused_s = _paused_s + _pause_open_s(now, _pause_started)
                    lag = max(0.0, now - started - _WATCH_INTERVAL_S - paused_s)
                    _hub_lag_s = lag
                    _interval_started = 0.0
                    _paused_s = 0.0
                _maybe_recycle(lag)
            except Exception:
                _LOGGER.debug("hub lag probe tick failed", exc_info=True)
                try:
                    gevent.sleep(_WATCH_INTERVAL_S)
                except Exception:
                    time.sleep(_WATCH_INTERVAL_S)

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
