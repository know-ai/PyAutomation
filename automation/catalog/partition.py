# -*- coding: utf-8 -*-
"""Partition guard: a tag may only bind to a machine in the same area.

Cross-area tagsmachines rows break multi-edge catalogs (foreign machines leak
into the local SQLite replica). Call this at bind time and on catalog pull.
"""
from __future__ import annotations

import logging
from typing import Any


class CrossAreaBindError(ValueError):
    """tag.area and machine.area differ; the bind must not be persisted."""


def _is_mock(value: Any) -> bool:
    return type(value).__name__ in ("MagicMock", "Mock", "AsyncMock", "NonCallableMagicMock")


def row_area(row: Any) -> Any:
    """Area from a Peewee model, catalog dict, or in-memory object."""
    if row is None or _is_mock(row):
        return None
    if isinstance(row, dict):
        return row.get("area")
    area = getattr(row, "area", None)
    if _is_mock(area):
        return None
    return area


def normalize_area(value: Any) -> str:
    if value is None or _is_mock(value):
        return ""
    inner = getattr(value, "value", value)
    if inner is None or _is_mock(inner):
        return ""
    return str(inner).strip()


def daq_machine_name(scan_time_ms: Any, area: Any = None) -> str:
    """One DAQ poller per (area, scan_time). Isolated across edges.

    Single-edge / unset area keeps the historic ``DAQ-1000`` name so existing
    tests and monolitic plants stay compatible. Milliseconds are rounded so
    ``interval_s * 1000`` (e.g. 333 ms) does not become ``DAQ-332``.
    """
    try:
        ms = int(round(float(scan_time_ms)))
    except (TypeError, ValueError):
        ms = 0
    scoped = normalize_area(area)
    if scoped:
        return f"{scoped}.DAQ-{ms}"
    return f"DAQ-{ms}"


def areas_compatible(tag_area: Any, machine_area: Any) -> bool:
    """True when both empty (single-edge unset) or both set and equal."""
    tag = normalize_area(tag_area)
    machine = normalize_area(machine_area)
    if not tag and not machine:
        return True
    return bool(tag) and bool(machine) and tag == machine


def ensure_same_partition(
    tag_area: Any,
    machine_area: Any,
    *,
    tag_name: Any = None,
    machine_name: Any = None,
) -> None:
    if areas_compatible(tag_area, machine_area):
        return
    tag = normalize_area(tag_name) or "tag"
    machine = normalize_area(machine_name) or "machine"
    raise CrossAreaBindError(
        f"Tag area '{normalize_area(tag_area)}' does not match machine area "
        f"'{normalize_area(machine_area)}'. Cannot bind {tag} to {machine} cross-area."
    )


def bind_areas_from_objects(tag, machine, tag_row=None, machine_row=None) -> tuple[Any, Any]:
    """Prefer persisted catalog rows; fall back to in-memory Tag / StateMachine."""
    tag_area = row_area(tag_row)
    if tag_area is None:
        tag_area = row_area(tag)
    machine_area = row_area(machine_row)
    if machine_area is None:
        machine_area = row_area(machine)
        if machine_area is None:
            name = getattr(machine, "name", None)
            machine_area = getattr(name, "area", None) if name is not None and not _is_mock(name) else None
            if _is_mock(machine_area):
                machine_area = None
    return tag_area, machine_area


def ensure_machine_name_partition(db) -> None:
    """Drop global UNIQUE(machines.name); enforce (area, name) when area is set.

    PostgreSQL UNIQUE(area, name) without a predicate still allows two NULL-area
    rows with the same name. Application ``Machines.name_exist`` covers that case.
    """
    if db is None:
        return
    vendor = str(getattr(db, "vendor", "") or "").lower()
    logger = logging.getLogger("pyautomation")
    try:
        if vendor == "postgresql":
            db.execute_sql(
                'ALTER TABLE "machines" DROP CONSTRAINT IF EXISTS machines_name_key'
            )
            db.execute_sql("DROP INDEX IF EXISTS machines_area_name_idx")
            db.execute_sql(
                'CREATE UNIQUE INDEX IF NOT EXISTS machines_area_name_uidx '
                'ON "machines" (area, name) '
                "WHERE area IS NOT NULL AND btrim(area) <> ''"
            )
            return
        if vendor == "mysql":
            try:
                db.execute_sql("ALTER TABLE `machines` DROP INDEX `name`")
            except Exception:
                logger.debug("machines.name unique drop skipped", exc_info=True)
            try:
                db.execute_sql(
                    "CREATE UNIQUE INDEX machines_area_name_uidx ON `machines` (area, name)"
                )
            except Exception:
                logger.debug("machines (area, name) unique skipped", exc_info=True)
            return
        _drop_sqlite_machines_name_unique(db)
        db.execute_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS machines_area_name_uidx "
            "ON machines (area, name) "
            "WHERE area IS NOT NULL AND TRIM(area) <> ''"
        )
    except Exception:
        logger.debug("machines name partition migration skipped", exc_info=True)


def _drop_sqlite_machines_name_unique(db) -> None:
    try:
        cursor = db.execute_sql(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='machines'"
        )
        rows = cursor.fetchall() if cursor is not None else ()
    except Exception:
        rows = ()
    for name, sql in rows or ():
        compact = "".join(str(sql or "").upper().split())
        if "UNIQUE" in compact and "(NAME)" in compact:
            try:
                db.execute_sql(f'DROP INDEX IF EXISTS "{name}"')
            except Exception:
                pass
    for legacy in ("machines_name", "machines_name_key"):
        try:
            db.execute_sql(f"DROP INDEX IF EXISTS {legacy}")
        except Exception:
            pass

