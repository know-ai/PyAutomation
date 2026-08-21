# -*- coding: utf-8 -*-
"""ICatalogProvider: local SQLite vs historian Peewee."""
from __future__ import annotations

import logging
from typing import Protocol

_LOGGER = logging.getLogger("pyautomation")

_SOURCE = "local"


def set_catalog_source(source: str) -> None:
    global _SOURCE
    _SOURCE = "remote" if source == "remote" else "local"


def catalog_source() -> str:
    return _SOURCE


def refresh_catalog_source() -> str:
    try:
        from automation import PyAutomation

        connected = bool(PyAutomation().is_db_connected())
    except Exception:
        connected = False
    set_catalog_source("remote" if connected else "local")
    return catalog_source()


class CatalogProvider(Protocol):
    def read_all(self, table: str) -> list[dict]:
        ...

    def read(self, table: str, row_id: str) -> dict | None:
        ...

    def upsert(self, table: str, row: dict) -> str:
        ...

    def delete(self, table: str, row_id: str) -> None:
        ...


def get_active() -> CatalogProvider:
    refresh_catalog_source()
    if catalog_source() == "remote":
        from .remote_provider import RemoteCatalogProvider

        return RemoteCatalogProvider()
    from .local_provider import LocalCatalogProvider

    return LocalCatalogProvider()
