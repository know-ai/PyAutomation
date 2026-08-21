# -*- coding: utf-8 -*-
"""O(1) catalog sync metrics snapshot."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .schema import CATALOG_TABLES_COUNT


@dataclass
class CatalogMetrics:
    source: str = "local"
    last_success_utc: str | None = None
    pending_rows: int = 0
    conflict_count: int = 0
    tables_count: int = CATALOG_TABLES_COUNT
    consecutive_failures: int = 0
    local_only_since_utc: str | None = None


_lock = threading.Lock()
_metrics = CatalogMetrics()


def snapshot() -> dict:
    with _lock:
        return {
            "CATALOG_SOURCE": _metrics.source,
            "CATALOG_SYNC_LAST_SUCCESS_UTC": _metrics.last_success_utc,
            "CATALOG_SYNC_PENDING_ROWS": int(_metrics.pending_rows),
            "CATALOG_SYNC_CONFLICT_COUNT": int(_metrics.conflict_count),
            "CATALOG_TABLES_COUNT": int(_metrics.tables_count),
        }


def update(**kwargs) -> None:
    with _lock:
        for key, value in kwargs.items():
            if hasattr(_metrics, key):
                setattr(_metrics, key, value)


def metrics() -> CatalogMetrics:
    return _metrics
