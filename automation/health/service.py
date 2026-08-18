# -*- coding: utf-8 -*-
"""DatabaseHealthService — single owner of remote-DB reachability for the HMI."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from ..utils.db_connections import probe_database
from .interfaces import (
    DB_UNAVAILABLE_MESSAGE,
    HealthSnapshot,
    IHealthProvider,
    IReconnectionHandler,
)

PROBE_TIMEOUT_S = 2.0
CACHE_TTL_S = 1.5
_LOGGER = logging.getLogger("pyautomation")


def _engine_label(dbtype: Optional[str]) -> str:
    raw = (dbtype or "database").strip().lower()
    return {
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "sqlite": "SQLite",
    }.get(raw, "Database")


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
            probe_database(db, timeout_s=self._timeout_s)
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
