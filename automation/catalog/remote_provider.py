# -*- coding: utf-8 -*-
"""Historian Peewee catalog provider (existing proxy — never rebound).

Bulk reads prefer the dedicated replicator handle (``replica_db``) so interactive
API traffic on the main proxy is not starved by full-table catalog scans.
"""
from __future__ import annotations

import logging

from .replica_db import replica_read_all
from .rows import row_to_raw, upsert_model
from .schema import historian_models, pk_as_str
from .versions import edge_node_id, now_ms, touch_remote

_LOGGER = logging.getLogger("pyautomation")


class RemoteCatalogProvider:
    def __init__(self, *, prefer_replica_reads: bool = True):
        self._prefer_replica_reads = bool(prefer_replica_reads)

    def read_all(self, table: str) -> list[dict]:
        if self._prefer_replica_reads:
            rows = replica_read_all(table)
            if rows:
                return rows
            # Empty can mean empty table OR replica not ready — fall through once.
            from .replica_db import ensure_replica_database

            if ensure_replica_database() is not None:
                return rows
        model = historian_models().get(table)
        if model is None:
            return []
        try:
            return [row_to_raw(row) for row in model.select().iterator()]
        except Exception:
            _LOGGER.debug("remote catalog read_all failed table=%s", table, exc_info=True)
            return []

    def read(self, table: str, row_id: str) -> dict | None:
        model = historian_models().get(table)
        if model is None:
            return None
        pk = model._meta.primary_key
        row = model.get_or_none(getattr(model, pk.name) == row_id)
        if row is None:
            try:
                row = model.get_or_none(getattr(model, pk.name) == int(row_id))
            except (TypeError, ValueError):
                row = None
        return row_to_raw(row) if row is not None else None

    def upsert(self, table: str, row: dict, *, node_id: str | None = None, version: int | None = None) -> str:
        model = historian_models().get(table)
        if model is None:
            raise KeyError(table)
        inst = upsert_model(model, row)
        if inst is None:
            raise RuntimeError(f"remote catalog upsert returned None table={table}")
        pk = pk_as_str(inst)
        touch_remote(table, pk, version=version or now_ms(), node_id=node_id or edge_node_id())
        return pk

    def delete(self, table: str, row_id: str) -> None:
        model = historian_models().get(table)
        if model is None:
            return
        pk = model._meta.primary_key
        try:
            model.delete().where(getattr(model, pk.name) == row_id).execute()
        except Exception:
            model.delete().where(getattr(model, pk.name) == int(row_id)).execute()
