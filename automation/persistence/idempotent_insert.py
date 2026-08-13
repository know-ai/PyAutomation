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

SECONDS_CEILING = 10_000_000_000  # unix seconds vs microseconds discriminator


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
        self._scale_second_timestamps(database, table)
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

    def _scale_second_timestamps(self, database, table: str) -> None:
        try:
            database.execute_sql(
                f"UPDATE {table} SET timestamp = timestamp * 1000000 "
                f"WHERE timestamp > 0 AND timestamp < {SECONDS_CEILING}"
            )
        except Exception:
            logging.getLogger("pyautomation").warning(
                "SAF: timestamp scale to microseconds skipped for %s",
                table,
                exc_info=True,
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
