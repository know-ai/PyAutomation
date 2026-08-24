# -*- coding: utf-8 -*-
"""Ordered catalog table registry (spec 11 §4). hmi_sessions is schema-only."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogTable:
    name: str
    replicate_rows: bool = True


# Parents before children. Names are SQL table names.
SYNC_ORDER: tuple[CatalogTable, ...] = (
    CatalogTable("datatypes"),
    CatalogTable("alarmtypes"),
    CatalogTable("alarmstates"),
    CatalogTable("roles"),
    CatalogTable("manufacturer"),
    CatalogTable("variables"),
    CatalogTable("accesstype"),
    CatalogTable("units"),
    CatalogTable("segment"),
    CatalogTable("users"),
    CatalogTable("tags"),
    CatalogTable("opcua"),
    CatalogTable("opcuaserver"),
    CatalogTable("nodes"),
    CatalogTable("machines"),
    CatalogTable("linearreferencinggeospatial"),
    CatalogTable("alarms"),
    CatalogTable("tagsmachines"),
    CatalogTable("hmi_sessions", replicate_rows=False),
    CatalogTable("user_api_sessions", replicate_rows=False),
)

REPLICATED_TABLES: tuple[str, ...] = tuple(t.name for t in SYNC_ORDER if t.replicate_rows)
ALL_TABLES: tuple[str, ...] = tuple(t.name for t in SYNC_ORDER)

CATALOG_TABLES_COUNT = len(REPLICATED_TABLES)
HISTORIAN_DBTYPES = ("postgresql", "mysql")


def historian_dbtype_allowed(dbtype: str | None) -> bool:
    return str(dbtype or "").lower() in HISTORIAN_DBTYPES


def historian_models():
    """Lazy import to avoid circulars at module import."""
    from ..dbmodels import (
        AccessType,
        AlarmStates,
        AlarmTypes,
        Alarms,
        DataTypes,
        HMISession,
        UserApiSession,
        LinearReferencingGeospatial,
        Machines,
        Manufacturer,
        Nodes,
        OPCUA,
        OPCUAServer,
        Roles,
        Segment,
        Tags,
        TagsMachines,
        Units,
        Users,
        Variables,
    )

    return {
        "datatypes": DataTypes,
        "alarmtypes": AlarmTypes,
        "alarmstates": AlarmStates,
        "roles": Roles,
        "manufacturer": Manufacturer,
        "variables": Variables,
        "accesstype": AccessType,
        "units": Units,
        "segment": Segment,
        "users": Users,
        "tags": Tags,
        "opcua": OPCUA,
        "opcuaserver": OPCUAServer,
        "nodes": Nodes,
        "machines": Machines,
        "linearreferencinggeospatial": LinearReferencingGeospatial,
        "alarms": Alarms,
        "tagsmachines": TagsMachines,
        "hmi_sessions": HMISession,
        "user_api_sessions": UserApiSession,
    }


def table_name_for_model(model) -> str:
    return str(model._meta.table_name)


def pk_as_str(row) -> str:
    if row is None:
        raise ValueError("Cannot read primary key from None catalog row")
    pk = getattr(row, "_pk", None)
    if pk is None and hasattr(row, "_meta"):
        pk_field = row._meta.primary_key
        pk = getattr(row, pk_field.name, None)
    if isinstance(pk, tuple):
        return "|".join(str(part) for part in pk)
    if pk is None:
        raise ValueError(f"Catalog row has no primary key: {type(row)!r}")
    return str(pk)
