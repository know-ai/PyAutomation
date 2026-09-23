# -*- coding: utf-8 -*-
"""Rate-limited log helpers for hot paths (alarms, SAF, catalog).

Mission-critical edges must not flood logs: one repeating condition logs at most
once per key per window. Never raises into callers.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

_LOCK = threading.Lock()
_LAST: dict[str, float] = {}
_DEFAULT_EVERY_S = 60.0


def clear_rate_limited_log_state() -> None:
    """Test helper: reset cooldown map."""
    with _LOCK:
        _LAST.clear()


def rate_limited_log(
    logger: logging.Logger,
    level: int,
    key: str,
    msg: str,
    *args: Any,
    every_s: float = _DEFAULT_EVERY_S,
    **kwargs: Any,
) -> bool:
    """Log at most once per ``key`` every ``every_s`` seconds.

    Returns True when a line was emitted.
    """
    now = time.monotonic()
    window = max(0.1, float(every_s or _DEFAULT_EVERY_S))
    with _LOCK:
        last = _LAST.get(key, 0.0)
        if (now - last) < window:
            return False
        _LAST[key] = now
    try:
        logger.log(level, msg, *args, **kwargs)
    except Exception:
        return False
    return True


def warning_once(logger: logging.Logger, key: str, msg: str, *args: Any, every_s: float = _DEFAULT_EVERY_S, **kwargs: Any) -> bool:
    return rate_limited_log(logger, logging.WARNING, key, msg, *args, every_s=every_s, **kwargs)


def error_once(logger: logging.Logger, key: str, msg: str, *args: Any, every_s: float = _DEFAULT_EVERY_S, **kwargs: Any) -> bool:
    return rate_limited_log(logger, logging.ERROR, key, msg, *args, every_s=every_s, **kwargs)


def info_once(logger: logging.Logger, key: str, msg: str, *args: Any, every_s: float = _DEFAULT_EVERY_S, **kwargs: Any) -> bool:
    return rate_limited_log(logger, logging.INFO, key, msg, *args, every_s=every_s, **kwargs)
