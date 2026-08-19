# -*- coding: utf-8 -*-
"""O(1) HTTP request counters for the node performance snapshot.

Hot-path increments only. Window counts are amortized O(1) via a deque prune.
Never queries the historian or OPC.
"""
from __future__ import annotations

import threading
import time
from collections import deque

_WINDOW_S = 60.0

_lock = threading.Lock()
_total = 0
_in_flight = 0
_5xx_total = 0
_req_times: deque[float] = deque()
_5xx_times: deque[float] = deque()


def on_request() -> None:
    now = time.monotonic()
    global _total, _in_flight
    with _lock:
        _total += 1
        _in_flight += 1
        _req_times.append(now)
        _prune_locked(now)


def on_response(status_code: int) -> None:
    now = time.monotonic()
    global _in_flight, _5xx_total
    code = int(status_code or 0)
    with _lock:
        _in_flight = max(0, _in_flight - 1)
        if code >= 500:
            _5xx_total += 1
            _5xx_times.append(now)
        _prune_locked(now)


def snapshot() -> dict:
    now = time.monotonic()
    with _lock:
        _prune_locked(now)
        return {
            "HTTP_REQUESTS_TOTAL": _total,
            "HTTP_REQUESTS_1M": len(_req_times),
            "HTTP_5XX_TOTAL": _5xx_total,
            "HTTP_5XX_1M": len(_5xx_times),
            "HTTP_IN_FLIGHT": _in_flight,
        }


def reset_http_metrics() -> None:
    """Test helper."""
    global _total, _in_flight, _5xx_total
    with _lock:
        _total = 0
        _in_flight = 0
        _5xx_total = 0
        _req_times.clear()
        _5xx_times.clear()


def install_http_metrics(flask_app) -> None:
    if flask_app is None or getattr(flask_app, "_pya_http_metrics", False):
        return

    from flask import g

    def _close(status_code: int) -> None:
        if not getattr(g, "_pya_http_open", False):
            return
        g._pya_http_open = False
        on_response(status_code)

    @flask_app.before_request
    def _pya_http_metrics_begin():
        on_request()
        g._pya_http_open = True

    @flask_app.after_request
    def _pya_http_metrics_end(response):
        try:
            _close(getattr(response, "status_code", 0) or 0)
        except Exception:
            _close(0)
        return response

    @flask_app.teardown_request
    def _pya_http_metrics_teardown(exc):
        try:
            if getattr(g, "_pya_http_open", False):
                _close(500 if exc is not None else 0)
        except Exception:
            pass

    flask_app._pya_http_metrics = True


def _prune_locked(now: float) -> None:
    cutoff = now - _WINDOW_S
    while _req_times and _req_times[0] < cutoff:
        _req_times.popleft()
    while _5xx_times and _5xx_times[0] < cutoff:
        _5xx_times.popleft()
