# -*- coding: utf-8 -*-
"""Local SQLite catalog provider."""
from __future__ import annotations

import logging
from contextlib import nullcontext

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
            return [row_to_raw(row) for row in model.select().iterator()]
        except Exception:
            _LOGGER.debug("local catalog read_all failed table=%s", table, exc_info=True)
            return []

    def find_one(self, table: str, *, field: str, value) -> dict | None:
        """Indexed lookup by field/column. Avoids full-table ``read_all`` scans."""
        model = local_model(table)
        if model is None or get_catalog_database() is None or value is None:
            return None
        attr = None
        if hasattr(model, field):
            attr = getattr(model, field)
        else:
            for name, fld in model._meta.fields.items():
                if name == field or getattr(fld, "column_name", None) == field:
                    attr = getattr(model, name)
                    break
        if attr is None:
            return None
        try:
            row = model.get_or_none(attr == value)
            if row is None and isinstance(value, str) and field in ("name", "username", "unit"):
                # Case-insensitive fallback for small lookup tables only.
                fname = getattr(attr, "name", field)
                for candidate in model.select().iterator():
                    raw = getattr(candidate, fname, None)
                    if raw is not None and str(raw).upper() == value.upper():
                        return row_to_raw(candidate)
            return row_to_raw(row) if row is not None else None
        except Exception:
            _LOGGER.debug(
                "local catalog find_one failed table=%s field=%s", table, field, exc_info=True
            )
            return None

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

    def exists(self, table: str, row_id) -> bool:
        """True if the local catalog has this primary key."""
        if row_id is None or row_id == "":
            return False
        return self.read(table, str(row_id)) is not None

    def upsert(self, table: str, row: dict, *, node_id: str | None = None, version: int | None = None) -> str:
        model = local_model(table)
        if model is None:
            raise KeyError(table)
        inst = upsert_model(model, row)
        pk = pk_as_str(inst)
        touch_local(table, pk, version=version or now_ms(), node_id=node_id or edge_node_id())
        return pk

    def atomic(self):
        """One SQLite transaction (nested calls become savepoints)."""
        db = get_catalog_database()
        if db is None:
            return nullcontext()
        return db.atomic()

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

    def delete_where(self, table: str, field: str, value) -> int:
        """Delete rows matching field=value. Returns deleted count."""
        model = local_model(table)
        if model is None or get_catalog_database() is None or value is None:
            return 0
        attr = getattr(model, field, None)
        if attr is None:
            return 0
        try:
            return int(model.delete().where(attr == value).execute() or 0)
        except Exception:
            _LOGGER.debug(
                "local catalog delete_where failed table=%s field=%s", table, field, exc_info=True
            )
            return 0
