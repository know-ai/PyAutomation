# -*- coding: utf-8 -*-
"""DatabaseHealthService — single owner of remote-DB reachability for the HMI."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
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
CONTACT_PATH = os.path.join(".", "db", "db_last_contact.json")
_PERSIST_MIN_S = 2.0
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
        self._contact_path = CONTACT_PATH
        self._last_contact_iso: Optional[str] = None
        self._last_persist_mono = 0.0
        self._load_last_contact()

    def is_connected(self) -> bool:
        return self.snapshot().connected

    def last_contact_iso(self) -> Optional[str]:
        """UTC timestamp of the last successful talk with the remote database."""
        with self._lock:
            return self._last_contact_iso

    def note_contact(self, when: Optional[datetime] = None) -> None:
        """Remember a successful probe or journal flush. Never raises."""
        moment = when or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        iso = moment.astimezone(timezone.utc).isoformat()
        persist = False
        with self._lock:
            if self._last_contact_iso is not None and iso < self._last_contact_iso:
                return
            self._last_contact_iso = iso
            now = time.monotonic()
            if now - self._last_persist_mono >= _PERSIST_MIN_S:
                self._last_persist_mono = now
                persist = True
            path = self._contact_path
        if persist:
            self._persist_last_contact(path, iso)

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
            self.note_contact()
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

    def _load_last_contact(self) -> None:
        try:
            with open(self._contact_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            iso = raw.get("last_contact_utc") if isinstance(raw, dict) else None
            if isinstance(iso, str) and iso.strip():
                self._last_contact_iso = iso.strip()
        except Exception:
            return

    def _persist_last_contact(self, path: str, iso: str) -> None:
        try:
            directory = os.path.dirname(path) or "."
            os.makedirs(directory, exist_ok=True)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump({"last_contact_utc": iso}, handle)
            os.replace(tmp_path, path)
        except Exception:
            _LOGGER.debug("db last-contact persist skipped", exc_info=True)

    def _current_engine(self) -> str:
        try:
            from .. import PyAutomation

            cfg = PyAutomation().get_db_config() or {}
            return _engine_label(cfg.get("dbtype"))
        except Exception:
            return "Database"


_SERVICE: Optional[IHealthProvider] = None
_SERVICE_LOCK = threading.Lock()


def note_database_contact() -> None:
    """Stamp a successful remote-database round trip. Never raises."""
    try:
        service = get_database_health_service()
        note = getattr(service, "note_contact", None)
        if callable(note):
            note()
    except Exception:
        _LOGGER.debug("db last-contact stamp skipped", exc_info=True)


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
