# -*- coding: utf-8 -*-
"""Ensure Variables/Units use the frozen stable IDs on historian and SAF catalog.

PostgreSQL and SQLite previously auto-assigned different primary keys for the
same engineering symbol (e.g. PG ``adim=168`` vs local ``adim=165``). Tag
``unit_id`` integers then crossed the mirror and poisoned EngUnits.

This module inserts/reconciles catalogue rows so both databases always share
``stable_catalogue.STABLE_*`` ids. Safe on first boot, upgrade, and re-hydrate.
"""
from __future__ import annotations

import logging

from .stable_catalogue import (
    STABLE_UNIT_ID_BY_SYMBOL,
    STABLE_UNITS,
    STABLE_VARIABLES,
)

_LOGGER = logging.getLogger("pyautomation")
_TEMP_BASE = 900_000


def _exec(db, sql: str, params: tuple = ()) -> None:
    """Run SQL with placeholders compatible with PG (``%s``) and SQLite (``?``)."""
    name = type(db).__name__.lower()
    if "sqlite" in name:
        db.execute_sql(sql.replace("%s", "?"), params)
    else:
        db.execute_sql(sql.replace("?", "%s"), params)


def _reset_serial(db, table: str) -> None:
    if db is None:
        return
    try:
        db.execute_sql(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
        )
        return
    except Exception:
        pass
    try:
        db.execute_sql(
            f"UPDATE sqlite_sequence SET seq = "
            f"(SELECT MAX(id) FROM {table}) WHERE name = '{table}'"
        )
    except Exception:
        pass


def _unit_var_fk(row) -> int:
    raw = getattr(row, "variable_id_id", None)
    if raw is not None:
        return int(raw)
    rel = getattr(row, "variable_id", None)
    if rel is None:
        return 0
    return int(getattr(rel, "id", rel))


def ensure_stable_catalogue_historian() -> dict:
    """Idempotent: variables/units in the live Peewee historian use stable ids."""
    from ..dbmodels.tags import Units, Variables

    stats = {"variables_fixed": 0, "units_fixed": 0, "tag_fks": 0}
    db = Variables._meta.database

    if Variables.select().count() == 0 and Units.select().count() == 0:
        with db.atomic():
            for vid, vname in STABLE_VARIABLES:
                Variables.insert(id=vid, name=vname).execute()
            for uid, name, symbol, var_id in STABLE_UNITS:
                Units.insert(id=uid, name=name, unit=symbol, variable_id=var_id).execute()
        stats["variables_fixed"] = len(STABLE_VARIABLES)
        stats["units_fixed"] = len(STABLE_UNITS)
        _reset_serial(db, "variables")
        _reset_serial(db, "units")
        _LOGGER.info("Stable catalogue historian cold-seeded: %s", stats)
        return stats

    with db.atomic():
        for vid, vname in STABLE_VARIABLES:
            row = Variables.get_or_none(Variables.name == vname)
            if row is None:
                clash = Variables.get_or_none(Variables.id == vid)
                if clash is not None:
                    temp = _TEMP_BASE + int(clash.id)
                    _exec(
                        db,
                        "UPDATE variables SET id = %s WHERE id = %s",
                        (temp, vid),
                    )
                    _exec(
                        db,
                        "UPDATE units SET variable_id = %s WHERE variable_id = %s",
                        (temp, vid),
                    )
                Variables.insert(id=vid, name=vname).execute()
                stats["variables_fixed"] += 1
                continue
            if int(row.id) == int(vid):
                continue
            old_id = int(row.id)
            clash = Variables.get_or_none(Variables.id == vid)
            if clash is not None and str(clash.name) != vname:
                temp = _TEMP_BASE + int(clash.id)
                _exec(db, "UPDATE variables SET id = %s WHERE id = %s", (temp, vid))
                _exec(
                    db,
                    "UPDATE units SET variable_id = %s WHERE variable_id = %s",
                    (temp, vid),
                )
            _exec(
                db,
                "UPDATE units SET variable_id = %s WHERE variable_id = %s",
                (vid, old_id),
            )
            _exec(db, "UPDATE variables SET id = %s WHERE id = %s", (vid, old_id))
            stats["variables_fixed"] += 1

        for uid, name, symbol, var_id in STABLE_UNITS:
            row = Units.get_or_none(Units.unit == symbol)
            if row is not None and int(row.id) == int(uid):
                if row.name != name or _unit_var_fk(row) != int(var_id):
                    Units.update(name=name, variable_id=var_id).where(Units.id == uid).execute()
                continue

            clash = Units.get_or_none(Units.id == uid)
            if clash is not None and str(clash.unit) != symbol:
                temp = _TEMP_BASE + int(clash.id)
                _repoint_unit_fks(db, int(clash.id), temp)
                _exec(db, "UPDATE units SET id = %s WHERE id = %s", (temp, uid))

            if row is None:
                Units.insert(id=uid, name=name, unit=symbol, variable_id=var_id).execute()
                stats["units_fixed"] += 1
                continue

            old_id = int(row.id)
            if old_id != uid:
                _repoint_unit_fks(db, old_id, uid)
                # Move row to stable PK (delete+insert if UPDATE id blocked).
                try:
                    _exec(
                        db,
                        "UPDATE units SET id = %s, name = %s, variable_id = %s WHERE id = %s",
                        (uid, name, var_id, old_id),
                    )
                except Exception:
                    Units.delete().where(Units.id == old_id).execute()
                    if Units.get_or_none(Units.id == uid) is None:
                        Units.insert(
                            id=uid, name=name, unit=symbol, variable_id=var_id
                        ).execute()
                    else:
                        Units.update(name=name, unit=symbol, variable_id=var_id).where(
                            Units.id == uid
                        ).execute()
                stats["units_fixed"] += 1
            else:
                Units.update(name=name, variable_id=var_id).where(Units.id == uid).execute()

        stats["tag_fks"] += _heal_tag_fks_by_symbol(db)
        try:
            Units.delete().where(Units.id >= _TEMP_BASE).execute()
            Variables.delete().where(Variables.id >= _TEMP_BASE).execute()
        except Exception:
            pass

    _reset_serial(db, "variables")
    _reset_serial(db, "units")
    if stats["variables_fixed"] or stats["units_fixed"] or stats["tag_fks"]:
        _LOGGER.info("Stable catalogue historian reconciled: %s", stats)
    return stats


def _repoint_unit_fks(db, old_id: int, new_id: int) -> None:
    if old_id == new_id:
        return
    for sql in (
        "UPDATE tags SET unit_id = %s WHERE unit_id = %s",
        "UPDATE tags SET display_unit_id = %s WHERE display_unit_id = %s",
        "UPDATE tagvalue SET unit_id = %s WHERE unit_id = %s",
    ):
        try:
            _exec(db, sql, (new_id, old_id))
        except Exception:
            pass


def _heal_tag_fks_by_symbol(db) -> int:
    """Set tag unit FKs from the unit row's symbol → stable id."""
    n = 0
    try:
        # Placeholder style: use %s; _exec not used for SELECT fetch.
        name = type(db).__name__.lower()
        sql = (
            "SELECT t.id, u.unit AS usym, du.unit AS dsym, t.unit_id, t.display_unit_id "
            "FROM tags t "
            "LEFT JOIN units u ON u.id = t.unit_id "
            "LEFT JOIN units du ON du.id = t.display_unit_id"
        )
        cur = db.execute_sql(sql)
        rows = list(cur.fetchall())
    except Exception:
        return 0
    for tid, usym, dsym, uid, duid in rows:
        want = STABLE_UNIT_ID_BY_SYMBOL.get(usym) if usym else None
        dwant = STABLE_UNIT_ID_BY_SYMBOL.get(dsym) if dsym else None
        sets = []
        params = []
        if want and int(uid or 0) != int(want):
            sets.append("unit_id = %s")
            params.append(want)
        if dwant and int(duid or 0) != int(dwant):
            sets.append("display_unit_id = %s")
            params.append(dwant)
        if not sets:
            continue
        params.append(tid)
        try:
            _exec(
                db,
                f"UPDATE tags SET {', '.join(sets)} WHERE id = %s",
                tuple(params),
            )
            n += 1
        except Exception:
            pass
    return n

def ensure_stable_catalogue_local() -> dict:
    """Idempotent: local SAF ``catalog.db`` variables/units use the same stable ids."""
    from ..catalog.local_db import get_catalog_database
    from ..catalog.local_provider import LocalCatalogProvider
    from ..catalog.seed import _upsert

    stats = {"variables_fixed": 0, "units_fixed": 0, "tag_fks": 0}
    if get_catalog_database() is None:
        return stats

    provider = LocalCatalogProvider()
    existing_units = {str(r.get("unit")): r for r in provider.read_all("units")}
    existing_vars = {str(r.get("name")): r for r in provider.read_all("variables")}

    for vid, vname in STABLE_VARIABLES:
        row = existing_vars.get(vname)
        cur = int((row or {}).get("id") or (row or {}).get("_pk") or 0) if row else 0
        if row is not None and cur == vid:
            continue
        _upsert("variables", {"id": vid, "_pk": vid, "name": vname})
        stats["variables_fixed"] += 1

    # Refresh and place units at stable ids.
    old_by_symbol = {
        str(r.get("unit")): int(r.get("id") or r.get("_pk") or 0)
        for r in provider.read_all("units")
        if r.get("unit")
    }
    for uid, name, symbol, var_id in STABLE_UNITS:
        old_id = old_by_symbol.get(symbol)
        _upsert(
            "units",
            {
                "id": uid,
                "_pk": uid,
                "name": name,
                "unit": symbol,
                "variable_id": var_id,
            },
        )
        if old_id is None or old_id != uid:
            stats["units_fixed"] += 1
        if old_id and old_id != uid:
            _repoint_local_tag_fks(provider, old_id, uid)
            stats["tag_fks"] += 1
            # Drop leftover row at old_id if still present with same symbol.
            try:
                db = get_catalog_database()
                if db is not None:
                    db.execute_sql(
                        "DELETE FROM units WHERE id = ? AND unit = ? AND id != ?",
                        (old_id, symbol, uid),
                    )
            except Exception:
                pass

    stats["tag_fks"] += _heal_local_tag_fks_by_symbol(provider)

    try:
        db = get_catalog_database()
        _reset_serial(db, "variables")
        _reset_serial(db, "units")
    except Exception:
        _LOGGER.debug("local stable catalogue serial reset skipped", exc_info=True)

    if stats["variables_fixed"] or stats["units_fixed"] or stats["tag_fks"]:
        _LOGGER.info("Stable catalogue local reconciled: %s", stats)
    return stats


def _repoint_local_tag_fks(provider, old_id: int, new_id: int) -> None:
    from ..catalog.seed import _upsert

    for row in provider.read_all("tags"):
        dirty = False
        payload = dict(row)
        if int(row.get("unit_id") or 0) == old_id:
            payload["unit_id"] = new_id
            payload["unit"] = new_id
            dirty = True
        if int(row.get("display_unit_id") or 0) == old_id:
            payload["display_unit_id"] = new_id
            payload["display_unit"] = new_id
            dirty = True
        if dirty:
            if row.get("_pk") is not None:
                payload["_pk"] = row.get("_pk")
            if row.get("id") is not None:
                payload["id"] = row.get("id")
            _upsert("tags", payload)


def _heal_local_tag_fks_by_symbol(provider) -> int:
    from ..catalog.seed import _upsert

    units_by_id = {}
    for r in provider.read_all("units"):
        for key in ("id", "_pk"):
            if r.get(key) is not None:
                units_by_id[str(r.get(key))] = r
    n = 0
    for row in provider.read_all("tags"):
        payload = dict(row)
        dirty = False
        for field, id_field in (("unit", "unit_id"), ("display_unit", "display_unit_id")):
            pk = row.get(id_field) if row.get(id_field) is not None else row.get(field)
            urow = units_by_id.get(str(pk)) if pk is not None else None
            sym = (urow or {}).get("unit")
            want = STABLE_UNIT_ID_BY_SYMBOL.get(sym) if sym else None
            if want and int(pk or 0) != int(want):
                payload[id_field] = want
                payload[field] = want
                dirty = True
        if dirty:
            if row.get("_pk") is not None:
                payload["_pk"] = row.get("_pk")
            if row.get("id") is not None:
                payload["id"] = row.get("id")
            _upsert("tags", payload)
            n += 1
    return n


def ensure_stable_catalogue(*, historian: bool = True, local: bool = True) -> dict:
    """Run both sides. Never raises."""
    out = {"historian": {}, "local": {}}
    if historian:
        try:
            out["historian"] = ensure_stable_catalogue_historian()
        except Exception:
            _LOGGER.warning("Stable catalogue historian ensure failed", exc_info=True)
    if local:
        try:
            out["local"] = ensure_stable_catalogue_local()
        except Exception:
            _LOGGER.warning("Stable catalogue local ensure failed", exc_info=True)
    return out
