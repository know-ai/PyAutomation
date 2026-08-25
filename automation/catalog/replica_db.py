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
from datetime import datetime, timezone
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
        return _fetch_dicts(db, sql)
    except Exception:
        _LOGGER.debug("replica_read_all failed table=%s", table, exc_info=True)
        return []


def replica_watermark_ms() -> int:
    """MAX(catalog_versions.version). 0 if empty/unavailable."""
    db = ensure_replica_database()
    if db is None:
        return 0
    try:
        _ensure_connected(db)
        cursor = db.execute_sql("SELECT COALESCE(MAX(version), 0) FROM catalog_versions")
        row = cursor.fetchone()
        return int((row[0] if row else 0) or 0)
    except Exception:
        _LOGGER.debug("replica watermark query failed", exc_info=True)
        return 0


def replica_modified_row_ids(table: str, since_ms: int) -> list[str] | None:
    """Row ids in catalog_versions with version > since_ms. None = must full-scan."""
    db = ensure_replica_database()
    if db is None:
        return None
    try:
        _ensure_connected(db)
        cursor = db.execute_sql(
            "SELECT row_id FROM catalog_versions WHERE table_name = %s AND version > %s",
            (str(table), int(since_ms)),
        )
        return [str(row[0]) for row in cursor.fetchall() if row and row[0] is not None]
    except Exception:
        _LOGGER.debug("replica modified ids failed table=%s", table, exc_info=True)
        return None


def replica_read_pks(table: str, pks: list[str]) -> list[dict]:
    """SELECT * WHERE pk IN (...). Empty list if no ids."""
    if not pks:
        return []
    db = ensure_replica_database()
    if db is None:
        return []
    dialect = "mysql" if "mysql" in type(db).__name__.lower() else "postgresql"
    pk_col = "id"
    try:
        from .schema import historian_models

        model = historian_models().get(table)
        if model is not None:
            field = model._meta.primary_key
            pk_col = getattr(field, "column_name", None) or getattr(field, "name", None) or "id"
    except Exception:
        pass
    qtable = _quote_ident(str(table), dialect)
    qpk = _quote_ident(str(pk_col), dialect)
    chunk_rows: list[dict] = []
    try:
        _ensure_connected(db)
        for offset in range(0, len(pks), 200):
            chunk = pks[offset : offset + 200]
            placeholders = ",".join(["%s"] * len(chunk))
            sql = f"SELECT * FROM {qtable} WHERE {qpk} IN ({placeholders})"
            chunk_rows.extend(_fetch_dicts(db, sql, tuple(chunk)))
        return chunk_rows
    except Exception:
        _LOGGER.debug("replica_read_pks failed table=%s", table, exc_info=True)
        return []


def replica_read_updated_at_since(table: str, since_ms: int) -> list[dict]:
    """SELECT * WHERE updated_at/created_at > watermark. Missing columns → []."""
    db = ensure_replica_database()
    if db is None:
        return []
    dialect = "mysql" if "mysql" in type(db).__name__.lower() else "postgresql"
    qtable = _quote_ident(str(table), dialect)
    ts = datetime.fromtimestamp(max(0, int(since_ms)) / 1000.0, tz=timezone.utc)
    rows: list[dict] = []
    for column in ("updated_at", "created_at"):
        qcol = _quote_ident(column, dialect)
        sql = f"SELECT * FROM {qtable} WHERE {qcol} > %s"
        try:
            rows.extend(_fetch_dicts(db, sql, (ts,)))
        except Exception:
            _LOGGER.debug(
                "replica updated_at/created_at filter skipped table=%s col=%s",
                table,
                column,
                exc_info=True,
            )
    return rows


def replica_read_incremental(table: str, since_ms: int) -> list[dict]:
    """Changed rows since watermark: catalog_versions.version plus updated_at."""
    by_pk: dict[str, dict] = {}
    ids = replica_modified_row_ids(table, since_ms)
    if ids is None:
        return replica_read_all(table)
    for row in replica_read_pks(table, ids):
        pk = str(row.get("_pk") or row.get("id") or "")
        if pk:
            by_pk[pk] = row
    for row in replica_read_updated_at_since(table, since_ms):
        pk = str(row.get("_pk") or row.get("id") or "")
        if pk:
            by_pk[pk] = row
    return list(by_pk.values())


def _ensure_connected(db) -> None:
    if getattr(db, "is_closed", lambda: True)():
        db.connect(reuse_if_open=True)


def _fetch_dicts(db, sql: str, params=None) -> list[dict]:
    _ensure_connected(db)
    cursor = db.execute_sql(sql, params) if params is not None else db.execute_sql(sql)
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
