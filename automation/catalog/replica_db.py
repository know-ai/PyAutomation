# -*- coding: utf-8 -*-
"""Dedicated Peewee Database for CatalogReplicatorWorker remote I/O.

The main historian proxy stays owned by the API / LoggerWorker (gevent). The
replicator is an OS thread: giving it its own libpq/MySQL handle avoids
socket / backend contention with interactive HMI requests. Models are never
rebound — remote reads use SQL on this handle.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

_LOGGER = logging.getLogger("pyautomation")
_REPLICA_LOCK = threading.Lock()
_replica_db: Any | None = None


def _quote_ident(name: str, dialect: str) -> str:
    if dialect == "mysql":
        return f"`{name}`"
    return f'"{name}"'


def ensure_replica_database():
    """Open (once) a secondary historian handle for catalog sync. Never raises."""
    global _replica_db
    with _REPLICA_LOCK:
        if _replica_db is not None:
            return _replica_db
        try:
            from automation import PyAutomation
            from ..utils.db_connections import (
                TrackedPostgresqlDatabase,
                TrackedMySQLDatabase,
                force_historian_connect,
                REGISTRY,
            )
            from ..utils.db_io import apply_remote_db_kwargs

            app = PyAutomation()
            cfg = dict(app.get_db_config() or {})
            dbtype = str(cfg.get("dbtype") or "").lower()
            if dbtype not in ("postgresql", "postgres", "mysql"):
                return None
            kwargs = {k: v for k, v in cfg.items() if k != "dbtype"}
            kwargs = apply_remote_db_kwargs(dbtype, kwargs)
            kwargs.pop("max_connections", None)
            kwargs.pop("stale_timeout", None)
            kwargs.pop("timeout", None)
            kwargs["application_name"] = "PyAutomationIO-catalog-replicator"
            with force_historian_connect():
                if dbtype in ("postgresql", "postgres"):
                    db_name = kwargs.pop("name", None) or kwargs.pop("database", None)
                    if not db_name:
                        primary = getattr(app, "_db", None)
                        db_name = getattr(primary, "database", None)
                    if not db_name:
                        return None
                    _replica_db = TrackedPostgresqlDatabase(db_name, **kwargs)
                else:
                    db_name = kwargs.pop("name", None) or kwargs.pop("database", None)
                    if not db_name:
                        primary = getattr(app, "_db", None)
                        db_name = getattr(primary, "database", None)
                    if not db_name:
                        return None
                    _replica_db = TrackedMySQLDatabase(db_name, **kwargs)
                REGISTRY.bind_instance(_replica_db)
                _replica_db.connect(reuse_if_open=True)
            _LOGGER.info("Catalog replicator dedicated historian handle ready")
            return _replica_db
        except Exception:
            _LOGGER.debug("catalog replica database open failed", exc_info=True)
            _replica_db = None
            return None


def reset_replica_database() -> None:
    """Drop the dedicated handle (e.g. after historian reconnect/config change)."""
    global _replica_db
    with _REPLICA_LOCK:
        db = _replica_db
        _replica_db = None
    if db is None:
        return
    try:
        closer = getattr(db, "close_all", None)
        if callable(closer):
            closer()
        elif hasattr(db, "close"):
            db.close()
    except Exception:
        _LOGGER.debug("catalog replica database reset skipped", exc_info=True)


def replica_read_all(table: str) -> list[dict]:
    """SELECT * via the dedicated handle. Falls back to [] on error."""
    db = ensure_replica_database()
    if db is None:
        return []
    dialect = "mysql" if "mysql" in type(db).__name__.lower() else "postgresql"
    sql = f"SELECT * FROM {_quote_ident(str(table), dialect)}"
    try:
        if getattr(db, "is_closed", lambda: True)():
            db.connect(reuse_if_open=True)
        cursor = db.execute_sql(sql)
        description = cursor.description or ()
        columns = [col[0] for col in description]
        rows: list[dict] = []
        for raw in cursor.fetchall():
            item = {columns[i]: raw[i] for i in range(len(columns))}
            pk = item.get("id")
            if pk is not None:
                item["_pk"] = str(pk)
            rows.append(item)
        return rows
    except Exception:
        _LOGGER.debug("replica_read_all failed table=%s", table, exc_info=True)
        return []


def close_replica_thread_connection() -> None:
    """Drop this OS-thread's socket so idle cycles do not hold a PG backend."""
    db = _replica_db
    if db is None:
        return
    try:
        if hasattr(db, "close"):
            db.close()
    except Exception:
        _LOGGER.debug("replica thread connection close skipped", exc_info=True)
