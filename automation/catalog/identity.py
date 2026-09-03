# -*- coding: utf-8 -*-
"""Natural-key identity and FK remapping for catalog push/pull across databases.

Local SQLite and remote PG assign different autoincrement PKs for the same logical
row. Sync must match by natural key and rewrite FK integers to the destination DB.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

_LOGGER = logging.getLogger("pyautomation")

# table -> fields that uniquely identify a logical row (first hit wins)
NATURAL_KEYS: dict[str, tuple[tuple[str, ...], ...]] = {
    "datatypes": (("name",),),
    "alarmtypes": (("name",),),
    "alarmstates": (("name",),),
    "roles": (("name",),),
    "manufacturer": (("name",),),
    "variables": (("name",),),
    "accesstype": (("name",),),
    "units": (("unit",), ("name",)),
    "segment": (("name",),),
    "users": (("username",), ("identifier",)),
    "authz_grants": (("subject_type", "subject_id", "resource_key", "action"),),
    "tags": (("identifier",), ("name",)),
    "opcua": (("client_name",),),
    "opcuaserver": (("namespace",), ("name",)),
    "nodes": (("id",),),
    "machines": (("identifier",), ("area", "name"), ("name",)),
    "linearreferencinggeospatial": (("segment", "kp"), ("segment_id", "kp")),
    "alarms": (("identifier",), ("name", "area"), ("name",)),
    "tagsmachines": (("tag", "machine"), ("tag_id", "machine_id")),
}

# table -> (fk_field_name, parent_table, parent_lookup_fields)
# fk_field_name is the Peewee field name (also try f"{name}_id")
FK_SPECS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    "units": (("variable", "variables", ("name",)),),
    "segment": (("manufacturer", "manufacturer", ("name",)),),
    "users": (("role", "roles", ("name",)),),
    "tags": (
        ("unit", "units", ("name", "unit")),
        ("data_type", "datatypes", ("name",)),
        ("display_unit", "units", ("name", "unit")),
        ("segment", "segment", ("name",)),
    ),
    "opcuaserver": (("access_type", "accesstype", ("name",)),),
    "alarms": (
        ("tag", "tags", ("name", "identifier")),
        ("trigger_type", "alarmtypes", ("name",)),
        ("state", "alarmstates", ("name",)),
    ),
    "tagsmachines": (
        ("tag", "tags", ("name", "identifier")),
        ("machine", "machines", ("name", "identifier")),
    ),
    "linearreferencinggeospatial": (("segment", "segment", ("name",)),),
}


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def identity_key(table: str, row: dict) -> str | None:
    """Stable logical identity for a catalog row, or None if unknown."""
    candidates = NATURAL_KEYS.get(table) or ()
    for fields in candidates:
        parts = []
        ok = True
        for field in fields:
            value = row.get(field)
            if value is None and field.endswith("_id"):
                continue
            if value is None and not field.endswith("_id"):
                # try column form
                alt = f"{field}_id" if field + "_id" in row else None
                if alt:
                    value = row.get(alt)
            text = _norm(value)
            if not text:
                ok = False
                break
            # Unit symbols are case-sensitive (mm ≠ Mm ≠ MM). Never fold them.
            if table == "units":
                parts.append(text)
            elif field in ("name", "username", "client_name"):
                parts.append(text.upper())
            else:
                parts.append(text)
        if ok and parts:
            return "|".join(parts)
    # Fallback: explicit identifier-like fields
    for field in ("identifier", "username", "client_name", "namespace", "name", "id"):
        text = _norm(row.get(field))
        if text:
            if table == "units":
                return f"{field}:{text}"
            return f"{field}:{text.upper() if field in ('name', 'username', 'client_name') else text}"
    return None


def index_by_identity(table: str, rows: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        key = identity_key(table, row)
        if key:
            indexed[key] = row
        pk = row.get("_pk") or row.get("id")
        if pk is not None:
            indexed.setdefault(f"pk:{pk}", row)
    return indexed


def _fk_value(row: dict, field: str) -> Any:
    if field in row and row.get(field) is not None:
        return row.get(field)
    column = f"{field}_id"
    if column in row:
        return row.get(column)
    return None


def _parent_identity_from_source(
    parent_table: str,
    fk_value: Any,
    source_rows_by_pk: dict[str, dict],
    lookup_fields: tuple[str, ...],
) -> str | None:
    parent = source_rows_by_pk.get(str(fk_value)) or source_rows_by_pk.get(f"pk:{fk_value}")
    if parent is None:
        # Sometimes fk_value already is a natural key string
        return identity_key(parent_table, {lookup_fields[0]: fk_value}) if lookup_fields else None
    return identity_key(parent_table, parent)


def lookup_fk_parent(
    table: str,
    row: dict,
    field: str,
    *,
    local_index: dict[str, dict[str, dict]],
    remote_index: dict[str, dict[str, dict]],
) -> dict | None:
    """Return the parent catalog row for ``row[field]``, or None if unknown."""
    specs = FK_SPECS.get(table) or ()
    parent_table = None
    lookup_fields: tuple[str, ...] = ()
    for spec_field, spec_parent, spec_lookup in specs:
        if spec_field == field:
            parent_table = spec_parent
            lookup_fields = spec_lookup
            break
    if not parent_table:
        return None
    fk_value = _fk_value(row, field)
    if fk_value is None or fk_value == "":
        return None
    for index in (remote_index.get(parent_table) or {}, local_index.get(parent_table) or {}):
        found = index.get(f"pk:{fk_value}") or index.get(f"pk:{str(fk_value)}")
        if found:
            return found
        parent_key = _parent_identity_from_source(
            parent_table, fk_value, index, lookup_fields
        )
        if parent_key and parent_key in index:
            return index[parent_key]
    return None


def parent_fk_known(
    table: str,
    row: dict,
    *,
    local_index: dict[str, dict[str, dict]],
    remote_index: dict[str, dict[str, dict]],
    parents: tuple[str, ...] = ("tags", "machines"),
) -> bool:
    """True if every tags/machines FK on ``row`` resolves in local or remote indexes."""
    specs = FK_SPECS.get(table) or ()
    for field, parent_table, lookup_fields in specs:
        if parent_table not in parents:
            continue
        fk_value = _fk_value(row, field)
        if fk_value is None or fk_value == "":
            return False
        found = False
        for index in (remote_index.get(parent_table) or {}, local_index.get(parent_table) or {}):
            if f"pk:{fk_value}" in index or f"pk:{str(fk_value)}" in index:
                found = True
                break
            parent_key = _parent_identity_from_source(
                parent_table, fk_value, index, lookup_fields
            )
            if parent_key and parent_key in index:
                found = True
                break
        if not found:
            return False
    return True


def remap_row_fks(
    table: str,
    row: dict,
    *,
    source_index: dict[str, dict[str, dict]],
    dest_index: dict[str, dict[str, dict]],
) -> dict:
    """Rewrite FK integers in ``row`` from source DB ids to destination DB ids."""
    payload = dict(row)
    specs = FK_SPECS.get(table) or ()
    for field, parent_table, lookup_fields in specs:
        fk_value = _fk_value(payload, field)
        if fk_value is None or fk_value == "":
            continue
        source_parents = source_index.get(parent_table) or {}
        dest_parents = dest_index.get(parent_table) or {}
        parent_key = _parent_identity_from_source(
            parent_table, fk_value, source_parents, lookup_fields
        )
        if not parent_key:
            # Try treating fk_value as already an identity fragment
            for lf in lookup_fields:
                parent_key = identity_key(parent_table, {lf: fk_value})
                if parent_key and parent_key in dest_parents:
                    break
            else:
                parent_key = None
        dest_parent = dest_parents.get(parent_key) if parent_key else None
        if dest_parent is None:
            _LOGGER.debug(
                "catalog FK remap missed table=%s field=%s fk=%s parent_key=%s",
                table,
                field,
                fk_value,
                parent_key,
            )
            # Drop stale local FK so upsert does not point at the wrong remote row.
            payload.pop(field, None)
            payload.pop(f"{field}_id", None)
            continue
        dest_pk = dest_parent.get("_pk") or dest_parent.get("id")
        payload[field] = dest_pk
        payload[f"{field}_id"] = dest_pk
    return payload


def prepare_push_row(
    table: str,
    local_row: dict,
    *,
    local_index: dict[str, dict[str, dict]],
    remote_index: dict[str, dict[str, dict]],
) -> dict:
    """Build a remote-safe upsert payload from a local catalog row."""
    payload = remap_row_fks(
        table,
        local_row,
        source_index=local_index,
        dest_index=remote_index,
    )
    key = identity_key(table, local_row)
    remote_existing = remote_index.get(table, {}).get(key) if key else None
    # Never force local autoincrement id onto remote unless nodes (string PK).
    if table != "nodes":
        payload.pop("id", None)
        payload.pop("_pk", None)
        payload.pop("sid", None)
    if remote_existing is not None:
        remote_pk = remote_existing.get("_pk") or remote_existing.get("id")
        if remote_pk is not None:
            payload["_pk"] = remote_pk
            payload["id"] = remote_pk
    return payload


def prepare_pull_row(
    table: str,
    remote_row: dict,
    *,
    local_index: dict[str, dict[str, dict]],
    remote_index: dict[str, dict[str, dict]],
) -> dict:
    """Build a local-safe upsert payload from a remote catalog row."""
    payload = remap_row_fks(
        table,
        remote_row,
        source_index=remote_index,
        dest_index=local_index,
    )
    key = identity_key(table, remote_row)
    local_existing = local_index.get(table, {}).get(key) if key else None
    if table != "nodes":
        payload.pop("id", None)
        payload.pop("_pk", None)
        payload.pop("sid", None)
    if local_existing is not None:
        local_pk = local_existing.get("_pk") or local_existing.get("id")
        if local_pk is not None:
            payload["_pk"] = local_pk
            payload["id"] = local_pk
    return payload


def build_table_indexes(
    read_all: Callable[[str], list[dict]],
    tables: tuple[str, ...] | list[str],
) -> dict[str, dict[str, dict]]:
    return {table: index_by_identity(table, read_all(table)) for table in tables}
