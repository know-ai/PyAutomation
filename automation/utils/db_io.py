# -*- coding: utf-8 -*-
"""Bounded I/O for remote historians (PostgreSQL / MySQL).

libpq and the MySQL client talk over C sockets. Those calls do not yield to
gevent. Under ``gevent.monkey.patch_all()`` (gunicorn GeventWebSocketWorker)
a ``connect()`` or ``SELECT 1`` against an unreachable host freezes the whole
hub — including Socket.IO ``on.tag`` — until the OS TCP timeout fires
(~30–180 s for SYN retries; minutes for a half-open socket).

This module:
1. Injects ``connect_timeout`` / TCP keepalives so libpq fails in seconds.
2. Runs uncooperative client I/O on the gevent hub threadpool (real OS
   threads) so the event loop keeps emitting HMI events while the probe waits.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, TypeVar

_LOGGER = logging.getLogger("pyautomation")

DEFAULT_CONNECT_TIMEOUT_S = 5
DEFAULT_PROBE_TIMEOUT_S = 2
_MAX_CONNECT_TIMEOUT_S = 30

_T = TypeVar("_T")
_FALLBACK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="db-io")
_DEAD_LOCK = threading.Lock()
_DEAD_UNTIL = 0.0


def connect_timeout_s() -> int:
    """Seconds libpq/MySQL may spend on TCP connect. Env: AUTOMATION_DB_CONNECT_TIMEOUT."""
    raw = os.environ.get("AUTOMATION_DB_CONNECT_TIMEOUT", str(DEFAULT_CONNECT_TIMEOUT_S))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_CONNECT_TIMEOUT_S
    return max(1, min(value, _MAX_CONNECT_TIMEOUT_S))


def probe_timeout_s() -> float:
    """Seconds a SELECT 1 / health probe may block. Env: AUTOMATION_DB_PROBE_TIMEOUT."""
    raw = os.environ.get("AUTOMATION_DB_PROBE_TIMEOUT", str(DEFAULT_PROBE_TIMEOUT_S))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(DEFAULT_PROBE_TIMEOUT_S)
    return max(0.2, min(value, float(_MAX_CONNECT_TIMEOUT_S)))


def apply_remote_db_kwargs(dbtype: str, kwargs: dict[str, Any] | None) -> dict[str, Any]:
    """Copy kwargs and set fail-fast TCP options for PostgreSQL / MySQL.

    Does not override keys the caller already provided. SQLite is unchanged.
    """
    out = dict(kwargs or {})
    kind = (dbtype or "").strip().lower()
    budget = connect_timeout_s()
    if kind in ("postgresql", "postgres"):
        out.setdefault("connect_timeout", budget)
        out.setdefault("application_name", "PyAutomationIO")
        out.setdefault("keepalives", 1)
        out.setdefault("keepalives_idle", 3)
        out.setdefault("keepalives_interval", 1)
        out.setdefault("keepalives_count", 3)
    elif kind == "mysql":
        out.setdefault("connect_timeout", budget)
        out.setdefault("read_timeout", budget)
        out.setdefault("write_timeout", budget)
    return out


def probe_is_cooling_down() -> bool:
    """True while a recent dead-peer probe is still in cooldown (skip stacked SELECT 1)."""
    with _DEAD_LOCK:
        return time.monotonic() < _DEAD_UNTIL


def mark_remote_db_dead(cooldown_s: float | None = None) -> None:
    global _DEAD_UNTIL
    # Default must outlast libpq connect_timeout so health/watchdog do not
    # stampede the threadpool (and the log) during an outage.
    hold = float(max(float(connect_timeout_s()), 8.0) if cooldown_s is None else cooldown_s)
    with _DEAD_LOCK:
        _DEAD_UNTIL = time.monotonic() + max(0.2, hold)


def mark_remote_db_live() -> None:
    global _DEAD_UNTIL
    with _DEAD_LOCK:
        _DEAD_UNTIL = 0.0


# Peewee/psycopg2 surfaces these when reconnect closes another greenlet's socket.
# Not data loss: local catalog + SAF journal remain source of truth until retry.
_STALE_HANDLE_MARKERS = (
    "connection already closed",
    "cursor already closed",
    "connection is closed",
    "closed this connection",
)


def is_stale_historian_handle(exc: BaseException | str | None) -> bool:
    """True when the remote handle died during reconnect/socket swap (safe to retry)."""
    text = str(exc or "").lower()
    return any(marker in text for marker in _STALE_HANDLE_MARKERS)


def log_historian_link_issue(
    logger: logging.Logger,
    exc: BaseException | str | None,
    *,
    where: str,
    action: str = "write",
) -> None:
    """Log link failures without implying data loss when the handle was only swapped."""
    if is_stale_historian_handle(exc):
        logger.info(
            "Historian socket replaced during reconnect (%s in %s). "
            "No data loss — local catalog/SAF keep the truth; retry uses the new link.",
            action,
            where,
        )
        logger.debug("stale historian handle detail: %s", exc, exc_info=isinstance(exc, BaseException))
        return
    reason = str(exc).split("\n", 1)[0][:180] if exc is not None else "unreachable"
    logger.warning(
        "Remote historian unreachable during %s (%s): %s. "
        "Edge keeps running on local catalog/SAF; will retry. No historical loss while journaled.",
        action,
        where,
        reason,
    )


def run_uncooperative_db_call(fn: Callable[[], _T], timeout_s: float | None = None) -> _T:
    """Run a libpq/MySQL call off the gevent hub.

    ``gevent.Timeout`` around ``psycopg2.connect`` does **not** work: the C
    stack never switches greenlets, so the timeout cannot fire until libpq
    returns. Hub threadpool uses native OS threads; ``.get(timeout=)`` *does*
    yield, so Socket.IO keeps running.
    """
    budget = float(probe_timeout_s() if timeout_s is None else timeout_s)
    try:
        from gevent import Timeout as GeventTimeout
        from gevent.hub import get_hub
    except ImportError:
        GeventTimeout = None
        get_hub = None

    pool = None
    if get_hub is not None:
        try:
            pool = get_hub().threadpool
        except Exception:
            _LOGGER.debug("gevent hub threadpool unavailable; using fallback executor", exc_info=True)
            pool = None

    if pool is not None:
        async_result = pool.spawn(fn)
        try:
            return async_result.get(timeout=budget)
        except GeventTimeout as exc:
            raise TimeoutError("database I/O timed out") from exc

    future = _FALLBACK_EXECUTOR.submit(fn)
    try:
        return future.result(timeout=budget)
    except FuturesTimeout as exc:
        raise TimeoutError("database I/O timed out") from exc
