# -*- coding: utf-8 -*-
"""Ordered catalog table registry (spec 11 §4). hmi_sessions is schema-only."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogTable:
    name: str
    replicate_rows: bool = True


# Parents before children. Names are SQL table names.
# Do not reorder to a "units first" list: variables→units, roles→users,
# alarmtypes/alarmstates→alarms and accesstype→opcuaserver would break FKs.
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
    CatalogTable("nodes"),
    CatalogTable("tags"),
    CatalogTable("machines"),
    CatalogTable("opcua"),
    CatalogTable("opcuaserver"),
    CatalogTable("alarms"),
    CatalogTable("tagsmachines"),
    CatalogTable("linearreferencinggeospatial"),
    CatalogTable("hmi_sessions", replicate_rows=False),
    CatalogTable("user_api_sessions", replicate_rows=False),
)

REPLICATED_TABLES: tuple[str, ...] = tuple(t.name for t in SYNC_ORDER if t.replicate_rows)
ALL_TABLES: tuple[str, ...] = tuple(t.name for t in SYNC_ORDER)

# Session tables stay in SYNC_ORDER for schema clones but are never pulled.
_SESSION_TABLES = frozenset({"hmi_sessions", "user_api_sessions"})
assert set(REPLICATED_TABLES) <= {t.name for t in SYNC_ORDER}
assert all(t in {c.name for c in SYNC_ORDER} for t in REPLICATED_TABLES)
assert _SESSION_TABLES.isdisjoint(REPLICATED_TABLES), (
    "REPLICATED_TABLES must be a subset of SYNC_ORDER (except hmi_sessions)"
)

# Small shared dictionaries. Always full-read so FK remap can resolve parent PKs
# even when the incremental pull of child tables (tags, alarms) has no parent diffs.
LOOKUP_TABLES: frozenset[str] = frozenset(
    {
        "datatypes",
        "alarmtypes",
        "alarmstates",
        "roles",
        "manufacturer",
        "variables",
        "accesstype",
        "units",
        "segment",
        "users",
    }
)

# Line-owned rows. Each edge pulls only its area / owner_node (plus unscoped globals).
PARTITIONED_TABLES: frozenset[str] = frozenset(
    {
        "tags",
        "alarms",
        "machines",
        "opcua",
        "tagsmachines",
    }
)

# Always full-read (area-filtered) so child FK remap can resolve remote parent PKs.
PARENT_TABLES: frozenset[str] = frozenset({"tags", "machines"})

# Depend on tags/machines. Never pull a child whose parent is not this edge.
CHILD_TABLES: frozenset[str] = frozenset({"alarms", "tagsmachines"})

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
