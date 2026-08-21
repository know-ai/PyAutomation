# -*- coding: utf-8 -*-
"""Sidecar catalog_versions on local mirror and historian."""
from __future__ import annotations

import logging
import os
import time

from ..dbmodels.catalog_versions import CatalogVersions
from .local_db import get_catalog_database
from .models import CatalogVersionsLocal

_LOGGER = logging.getLogger("pyautomation")


def now_ms() -> int:
    return int(time.time() * 1000)


def edge_node_id() -> str:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        node_id = getattr(scope, "node_id", None)
        if node_id:
            return str(node_id)
    except Exception:
        pass
    return os.environ.get("AUTOMATION_NODE_ID") or "edge"


def _touch(model, table: str, row_id: str, *, version: int | None, node_id: str | None, resolved: bool) -> int:
    stamp = int(version if version is not None else now_ms())
    node = node_id if node_id is not None else edge_node_id()
    existing = model.get_or_none((model.table_name == table) & (model.row_id == str(row_id)))
    if existing is None:
        model.create(
            table_name=table,
            row_id=str(row_id),
            version=stamp,
            node_id=node,
            conflict_resolved=bool(resolved),
        )
        return stamp
    existing.version = stamp
    existing.node_id = node
    existing.conflict_resolved = bool(resolved)
    existing.save()
    return stamp


def touch_local(table: str, row_id: str, *, version: int | None = None, node_id: str | None = None, resolved: bool = False) -> int:
    if get_catalog_database() is None:
        return now_ms()
    return _touch(CatalogVersionsLocal, table, row_id, version=version, node_id=node_id, resolved=resolved)


def touch_remote(table: str, row_id: str, *, version: int | None = None, node_id: str | None = None, resolved: bool = False) -> int:
    try:
        return _touch(CatalogVersions, table, row_id, version=version, node_id=node_id, resolved=resolved)
    except Exception:
        _LOGGER.debug("catalog_versions remote touch skipped table=%s row=%s", table, row_id, exc_info=True)
        return now_ms()


def get_local(table: str, row_id: str):
    if get_catalog_database() is None:
        return None
    return CatalogVersionsLocal.get_or_none(
        (CatalogVersionsLocal.table_name == table) & (CatalogVersionsLocal.row_id == str(row_id))
    )


def get_remote(table: str, row_id: str):
    try:
        return CatalogVersions.get_or_none(
            (CatalogVersions.table_name == table) & (CatalogVersions.row_id == str(row_id))
        )
    except Exception:
        return None


def list_local_pending(edge: str | None = None) -> list:
    if get_catalog_database() is None:
        return []
    node = edge or edge_node_id()
    return list(
        CatalogVersionsLocal.select().where(
            (CatalogVersionsLocal.node_id == node) & (CatalogVersionsLocal.conflict_resolved == False)  # noqa: E712
        )
    )


def pending_count() -> int:
    try:
        return len(list_local_pending())
    except Exception:
        return 0
