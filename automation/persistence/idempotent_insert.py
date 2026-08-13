# -*- coding: utf-8 -*-
"""Idempotent remote inserts — dialect-agnostic exact-once for TagValue.

Peewee's on_conflict_ignore() maps to:
  PostgreSQL / SQLite → INSERT ... ON CONFLICT DO NOTHING
  MySQL               → INSERT IGNORE

The replicator never sees SQL. This class's only job is conflict-safe flush.
"""
from __future__ import annotations

import logging
from typing import Mapping, Protocol, Sequence

from ..timebase import MICROSECONDS_FLOOR, SECONDS_CEILING


class IIdempotentInserter(Protocol):
    def insert_tag_values(self, rows: Sequence[Mapping]) -> int: ...


class IdempotentBatchInserter:
    """Single responsibility: write TagValue rows with ON CONFLICT DO NOTHING."""

    def __init__(self, model=None):
        self._model = model
        self._schema_ready = False

    def insert_tag_values(self, rows: Sequence[Mapping]) -> int:
        if not rows:
            return 0
        model = self._resolve_model()
        self.ensure_schema(model)
        query = model.insert_many(list(rows)).on_conflict_ignore()
        logger = logging.getLogger("pyautomation")
        try:
            sql, params = query.sql()
            logger.debug(
                "SAF TagValue INSERT sql=%s nparams=%s sample_params=%s",
                sql,
                len(params) if params else 0,
                (params[:10] if params else None),
            )
        except Exception:
            logger.debug("SAF TagValue INSERT sql unavailable", exc_info=True)
        query.execute()
        return len(rows)

    def ensure_schema(self, model=None) -> None:
        model = model or self._resolve_model()
        if self._schema_ready:
            return
        database = model._meta.database
        if database is None:
            return
        table = model._meta.table_name
        self._ensure_sample_uuid_column(database, table)
        self._widen_sample_uuid_column(database, table)
        self._normalize_timestamp_scale(database, table)
        self._ensure_unique_indexes(database, table)
        self._schema_ready = True

    def _resolve_model(self):
        if self._model is not None:
            return self._model
        from ..dbmodels.tags import TagValue

        return TagValue

    def _ensure_sample_uuid_column(self, database, table: str) -> None:
        columns = {column.name for column in database.get_columns(table)}
        if "sample_uuid" in columns:
            return
        database.execute_sql(f"ALTER TABLE {table} ADD COLUMN sample_uuid VARCHAR(255)")
        logging.getLogger("pyautomation").info("SAF: added sample_uuid to %s", table)

    def _widen_sample_uuid_column(self, database, table: str) -> None:
        logger = logging.getLogger("pyautomation")
        dialect = type(database).__name__.lower()
        try:
            if "postgres" in dialect:
                database.execute_sql(
                    f"ALTER TABLE {table} ALTER COLUMN sample_uuid TYPE VARCHAR(255)"
                )
            elif "mysql" in dialect:
                database.execute_sql(
                    f"ALTER TABLE {table} MODIFY COLUMN sample_uuid VARCHAR(255)"
                )
        except Exception:
            logger.warning("SAF: sample_uuid widen skipped for %s", table, exc_info=True)

    def _normalize_timestamp_scale(self, database, table: str) -> None:
        """Normalize TagValue.timestamp ticks to milliseconds (resolution=3).

        - unix seconds  → ×1000
        - unix µs (legacy resolution=6) → ÷1000 after collapsing same-ms duplicates

        Safe for UNIQUE (tag_id, timestamp): duplicate micro-pairs inside one ms
        are reduced to a single row before the scale change.
        """
        logger = logging.getLogger("pyautomation")
        try:
            database.execute_sql(
                f"UPDATE {table} SET timestamp = timestamp * 1000 "
                f"WHERE timestamp > 0 AND timestamp < {SECONDS_CEILING}"
            )
        except Exception:
            logger.warning(
                "SAF: timestamp scale seconds→ms skipped for %s",
                table,
                exc_info=True,
            )
            return
        try:
            self._collapse_microsecond_duplicates(database, table)
            database.execute_sql(
                f"UPDATE {table} SET timestamp = timestamp / 1000 "
                f"WHERE timestamp >= {MICROSECONDS_FLOOR}"
            )
        except Exception:
            logger.warning(
                "SAF: timestamp scale microseconds→ms skipped for %s",
                table,
                exc_info=True,
            )

    def _collapse_microsecond_duplicates(self, database, table: str) -> None:
        """Keep the lowest id per (tag_id, floor(ts_us/1000)) before ÷1000."""
        # Portable form (PostgreSQL + SQLite): delete via id list, not FROM alias.
        database.execute_sql(
            f"""
            DELETE FROM {table}
            WHERE id IN (
              SELECT tv.id FROM {table} AS tv
              WHERE tv.timestamp >= {MICROSECONDS_FLOOR}
                AND EXISTS (
                  SELECT 1 FROM {table} AS other
                  WHERE other.tag_id = tv.tag_id
                    AND other.timestamp >= {MICROSECONDS_FLOOR}
                    AND (other.timestamp / 1000) = (tv.timestamp / 1000)
                    AND other.id < tv.id
                )
            )
            """
        )

    def _ensure_unique_indexes(self, database, table: str) -> None:
        logger = logging.getLogger("pyautomation")
        statements = [
            (
                f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_sample_uuid_uidx "
                f"ON {table} (sample_uuid)"
            ),
            (
                f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_tag_timestamp_uidx "
                f"ON {table} (tag_id, timestamp)"
            ),
        ]
        for sql in statements:
            try:
                database.execute_sql(sql)
            except Exception:
                logger.warning("SAF: unique index not applied (%s)", sql, exc_info=True)
