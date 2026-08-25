# -*- coding: utf-8 -*-
"""Optional Redis client for HMI session hot path (AUTOMATION_REDIS_URL).

Fail-open: if Redis is unset or unreachable, callers use in-memory fallback.
Never raise into Socket.IO handlers.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

_LOGGER = logging.getLogger("pyautomation.redis")
_LOCK = threading.Lock()
_CLIENT: Any = None
_NEXT_RETRY_MONO = 0.0
_RETRY_S = 5.0


def redis_url() -> str:
    return (os.environ.get("AUTOMATION_REDIS_URL") or "").strip()


def warn_if_redis_unconfigured() -> None:
    """ARC-05: production should set AUTOMATION_REDIS_URL (local sidecar). Fail-open."""
    if redis_url():
        return
    message = (
        "AUTOMATION_REDIS_URL is unset; HMI sessions use in-process RAM fallback. "
        "In production each edge must run a redis-session sidecar "
        "(redis://redis-session:6379/0)."
    )
    _LOGGER.warning(message)
    print(f"[WARNING] {message}")


def reset_redis_for_tests() -> None:
    global _CLIENT, _NEXT_RETRY_MONO
    with _LOCK:
        _CLIENT = None
        _NEXT_RETRY_MONO = 0.0


def get_redis(*, force: bool = False) -> Any | None:
    """Return a live Redis client or None. Cheap to call on the Socket.IO path."""
    global _CLIENT, _NEXT_RETRY_MONO
    url = redis_url()
    if not url:
        return None
    now = time.monotonic()
    with _LOCK:
        if _CLIENT is not None and not force:
            return _CLIENT
        if not force and now < _NEXT_RETRY_MONO:
            return None
        try:
            import redis as redis_lib

            client = redis_lib.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=0.05,
                socket_timeout=0.05,
                health_check_interval=15,
            )
            client.ping()
            _CLIENT = client
            _NEXT_RETRY_MONO = 0.0
            return _CLIENT
        except Exception:
            _CLIENT = None
            _NEXT_RETRY_MONO = now + _RETRY_S
            _LOGGER.debug("Redis unavailable; HMI sessions use memory fallback", exc_info=True)
            return None
