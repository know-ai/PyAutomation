# -*- coding: utf-8 -*-
"""SQLite handle for ./db/catalog.db — never the SAF journal or historian."""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

from peewee import Proxy, SqliteDatabase

_LOGGER = logging.getLogger("pyautomation")

catalog_proxy = Proxy()

_DEFAULT_PATH = os.path.join(".", "db", "catalog.db")
_lock = threading.Lock()
_database: SqliteDatabase | None = None
_path = _DEFAULT_PATH
_compact_lock = threading.Lock()
_last_catalog_checkpoint_mono = 0.0
_last_catalog_compact_mono = 0.0


def catalog_path() -> str:
    return _path


def get_catalog_database() -> SqliteDatabase | None:
    return _database


def open_catalog_db(path: str | None = None) -> SqliteDatabase:
    """Open/create the local catalog mirror. Idempotent. Never raises to caller via wrapper."""
    global _database, _path
    with _lock:
        target = os.path.abspath(path or _DEFAULT_PATH)
        if _database is not None and os.path.abspath(_path) == target:
            return _database
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)
        db = SqliteDatabase(
            target,
            pragmas={
                "journal_mode": "wal",
                "foreign_keys": 1,
                "cache_size": -8000,
                "synchronous": 1,
                "temp_store": "MEMORY",
            },
        )
        db.connect(reuse_if_open=True)
        catalog_proxy.initialize(db)
        _database = db
        _path = target
        _LOGGER.info("Local catalog mirror opened path=%s", target)
        return db


def close_catalog_db() -> None:
    global _database
    with _lock:
        if _database is not None:
            try:
                _database.close()
            except Exception:
                _LOGGER.debug("catalog.db close skipped", exc_info=True)
            _database = None


def compact_catalog_idle(
    *,
    min_freelist_bytes: int = 64 * 1024 * 1024,
    min_interval_s: float = 3600.0,
) -> dict[str, int]:
    """Truncate WAL and VACUUM catalog.db. Never holds the SAF journal lock."""
    global _last_catalog_checkpoint_mono, _last_catalog_compact_mono
    path = os.path.abspath(_path)
    result = {"checkpointed": 0, "vacuumed": 0, "freelist_bytes": 0, "skipped": 0}
    if not os.path.exists(path):
        result["skipped"] = 1
        return result
    with _compact_lock:
        conn = None
        try:
            conn = sqlite3.connect(path, timeout=5.0)
            conn.execute("PRAGMA busy_timeout=5000")
            now = time.monotonic()
            wal_path = path + "-wal"
            wal_bytes = 0
            try:
                wal_bytes = int(os.path.getsize(wal_path))
            except OSError:
                wal_bytes = 0
            if wal_bytes >= 8 * 1024 * 1024 or (now - _last_catalog_checkpoint_mono) >= 30.0:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                _last_catalog_checkpoint_mono = now
                result["checkpointed"] = 1
            page = conn.execute("PRAGMA page_size").fetchone()
            free = conn.execute("PRAGMA freelist_count").fetchone()
            page_size = int(page[0] if page else 0)
            free_pages = int(free[0] if free else 0)
            freelist_bytes = max(0, page_size * free_pages)
            result["freelist_bytes"] = freelist_bytes
            if (
                min_freelist_bytes > 0
                and freelist_bytes >= min_freelist_bytes
                and (now - _last_catalog_compact_mono) >= min_interval_s
            ):
                conn.commit()
                conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
                conn.execute("VACUUM")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                _last_catalog_compact_mono = time.monotonic()
                _last_catalog_checkpoint_mono = _last_catalog_compact_mono
                result["vacuumed"] = 1
                _LOGGER.warning(
                    "catalog.db compact done path=%s freelist_bytes=%s",
                    path,
                    freelist_bytes,
                )
        except sqlite3.Error:
            _LOGGER.debug("catalog.db compact skipped (busy or locked)", exc_info=True)
            result["skipped"] = 1
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
        return result
