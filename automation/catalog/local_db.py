# -*- coding: utf-8 -*-
"""SQLite handle for ./db/catalog.db — never the SAF journal or historian."""
from __future__ import annotations

import logging
import os
import threading

from peewee import Proxy, SqliteDatabase

_LOGGER = logging.getLogger("pyautomation")

catalog_proxy = Proxy()

_DEFAULT_PATH = os.path.join(".", "db", "catalog.db")
_lock = threading.Lock()
_database: SqliteDatabase | None = None
_path = _DEFAULT_PATH


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
