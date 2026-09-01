# -*- coding: utf-8 -*-
"""Open local catalog, create tables, dual-write helper."""
from __future__ import annotations

import logging

from .local_db import get_catalog_database, open_catalog_db
from .local_provider import LocalCatalogProvider
from .models import all_local_tables
from .provider import catalog_source, refresh_catalog_source
from .rows import row_to_raw
from .schema import pk_as_str, table_name_for_model
from .versions import edge_node_id, now_ms, touch_local, touch_remote

_LOGGER = logging.getLogger("pyautomation")


def bootstrap_local_catalog(path: str | None = None):
    """Always-on local mirror. Safe if called more than once."""
    db = open_catalog_db(path)
    db.create_tables(all_local_tables(), safe=True)
    from .partition import ensure_machine_name_partition
    from ..dbmodels.alarms import ensure_alarm_delay_schema

    ensure_machine_name_partition(db)
    ensure_alarm_delay_schema(db)
    refresh_catalog_source()
    return db


def mirror_historian_row(instance) -> None:
    """Copy a historian catalog row into the local mirror. Never raises."""
    try:
        if get_catalog_database() is None:
            return
        table = table_name_for_model(instance.__class__)
        raw = row_to_raw(instance)
        LocalCatalogProvider().upsert(table, raw, node_id=edge_node_id(), version=now_ms())
        pk = pk_as_str(instance)
        if catalog_source() == "remote":
            touch_remote(table, pk, node_id=edge_node_id(), version=now_ms(), resolved=True)
            touch_local(table, pk, node_id=edge_node_id(), version=now_ms(), resolved=True)
    except Exception:
        _LOGGER.debug("catalog mirror skipped", exc_info=True)


def write_catalog_row(table: str, row: dict) -> str | None:
    """Write to the active provider and always persist locally. Never raises."""
    try:
        from .provider import get_active

        provider = get_active()
        pk = provider.upsert(table, row, node_id=edge_node_id(), version=now_ms())
        if catalog_source() == "remote":
            LocalCatalogProvider().upsert(table, row, node_id=edge_node_id(), version=now_ms())
        return pk
    except Exception:
        _LOGGER.debug("catalog write skipped table=%s", table, exc_info=True)
        return None
