# -*- coding: utf-8 -*-
"""DatabaseHealthService — single owner of remote-DB reachability for the HMI."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

from .interfaces import (
    DB_UNAVAILABLE_MESSAGE,
    HealthSnapshot,
    IHealthProvider,
    IReconnectionHandler,
)

PROBE_TIMEOUT_S = 2.0
CACHE_TTL_S = 1.5
_LOGGER = logging.getLogger("pyautomation")
_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-health")


def _engine_label(dbtype: Optional[str]) -> str:
    raw = (dbtype or "database").strip().lower()
    return {
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "sqlite": "SQLite",
    }.get(raw, "Database")


def _run_with_timeout(fn, timeout_s: float):
    """Fail closed if SELECT 1 blocks longer than ``timeout_s``.

    Gevent workers hang for minutes on a dead TCP socket; a hard timeout keeps
    the health endpoint and 503 decorator off the hot path.
    """
    try:
        import gevent
        from gevent import Timeout as GeventTimeout
    except ImportError:
        gevent = None
        GeventTimeout = None

    if gevent is not None and GeventTimeout is not None:
        try:
            with GeventTimeout(timeout_s):
                return fn()
        except GeventTimeout:
            raise TimeoutError("database health probe timed out")

    future = _PROBE_EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout_s)
    except FuturesTimeout as exc:
        raise TimeoutError("database health probe timed out") from exc


class DatabaseHealthService(IHealthProvider, IReconnectionHandler):
    """Pings the remote historian with SELECT 1. Does not touch the SAF journal."""

    def __init__(self, timeout_s: float = PROBE_TIMEOUT_S, cache_ttl_s: float = CACHE_TTL_S):
        self._timeout_s = timeout_s
        self._cache_ttl_s = cache_ttl_s
        self._lock = threading.Lock()
        self._cached: Optional[HealthSnapshot] = None
        self._cached_at = 0.0

    def is_connected(self) -> bool:
        return self.snapshot().connected

    def snapshot(self, *, force: bool = False) -> HealthSnapshot:
        now = time.monotonic()
        with self._lock:
            if (
                not force
                and self._cached is not None
                and (now - self._cached_at) < self._cache_ttl_s
            ):
                return self._cached
        probed = self._probe()
        with self._lock:
            self._cached = probed
            self._cached_at = time.monotonic()
        return probed

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None
            self._cached_at = 0.0

    def reconnect(self) -> HealthSnapshot:
        """Ask the core to rebind the remote DB, then probe again."""
        from .. import PyAutomation

        self.invalidate()
        try:
            PyAutomation().reconnect_to_db(source="hmi")
        except Exception:
            _LOGGER.warning("HMI-triggered DB reconnect failed", exc_info=True)
        return self.snapshot(force=True)

    def _probe(self) -> HealthSnapshot:
        checked_at = time.time()
        engine = self._current_engine()
        db = self._db_handle()
        if db is None:
            return HealthSnapshot(
                connected=False,
                latency_ms=None,
                message=DB_UNAVAILABLE_MESSAGE,
                checked_at=checked_at,
                engine=engine,
            )

        started = time.perf_counter()
        try:
            _run_with_timeout(lambda: db.execute_sql("SELECT 1;"), self._timeout_s)
            latency_ms = (time.perf_counter() - started) * 1000.0
            return HealthSnapshot(
                connected=True,
                latency_ms=latency_ms,
                message=f"{engine} connected",
                checked_at=checked_at,
                engine=engine,
            )
        except Exception:
            _LOGGER.debug("Remote database health probe failed", exc_info=True)
            return HealthSnapshot(
                connected=False,
                latency_ms=None,
                message=DB_UNAVAILABLE_MESSAGE,
                checked_at=checked_at,
                engine=engine,
            )

    def _db_handle(self):
        try:
            from ..logger.datalogger import DataLoggerEngine

            db = DataLoggerEngine().logger.get_db()
            if db is not None:
                return db
        except Exception:
            _LOGGER.debug("DataLoggerEngine handle unavailable for health probe", exc_info=True)
        try:
            from .. import PyAutomation

            return PyAutomation().db_manager.get_db()
        except Exception:
            return None

    def _current_engine(self) -> str:
        try:
            from .. import PyAutomation

            cfg = PyAutomation().get_db_config() or {}
            return _engine_label(cfg.get("dbtype"))
        except Exception:
            return "Database"


_SERVICE: Optional[IHealthProvider] = None
_SERVICE_LOCK = threading.Lock()


def get_database_health_service() -> IHealthProvider:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = DatabaseHealthService()
        return _SERVICE


def set_database_health_service(service: Optional[IHealthProvider]) -> None:
    """Test seam: inject a mock IHealthProvider / IReconnectionHandler."""
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = service
