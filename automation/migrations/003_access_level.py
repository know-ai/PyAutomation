"""Backfill the integer access bitmask on databases created earlier."""

from __future__ import annotations


def apply(db=None) -> None:
    from ..dbmodels.opcua_server import OPCUAServer, ensure_access_level_column

    if db is not None:
        OPCUAServer._meta.database = db
    ensure_access_level_column(db)
