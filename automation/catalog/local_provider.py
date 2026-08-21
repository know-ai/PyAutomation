# -*- coding: utf-8 -*-
"""Local SQLite catalog provider."""
from __future__ import annotations

import logging

from .local_db import get_catalog_database
from .models import local_model
from .rows import row_to_raw, upsert_model
from .schema import pk_as_str
from .versions import edge_node_id, now_ms, touch_local

_LOGGER = logging.getLogger("pyautomation")


class LocalCatalogProvider:
    def read_all(self, table: str) -> list[dict]:
        model = local_model(table)
        if model is None or get_catalog_database() is None:
            return []
        try:
            return [row_to_raw(row) for row in model.select()]
        except Exception:
            _LOGGER.debug("local catalog read_all failed table=%s", table, exc_info=True)
            return []

    def read(self, table: str, row_id: str) -> dict | None:
        model = local_model(table)
        if model is None or get_catalog_database() is None:
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
        model = local_model(table)
        if model is None:
            raise KeyError(table)
        inst = upsert_model(model, row)
        pk = pk_as_str(inst)
        touch_local(table, pk, version=version or now_ms(), node_id=node_id or edge_node_id())
        return pk

    def delete(self, table: str, row_id: str) -> None:
        model = local_model(table)
        if model is None:
            return
        pk = model._meta.primary_key
        q = model.delete().where(getattr(model, pk.name) == row_id)
        try:
            q.execute()
        except Exception:
            model.delete().where(getattr(model, pk.name) == int(row_id)).execute()
