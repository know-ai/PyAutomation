# -*- coding: utf-8 -*-
"""Versioned tag-unit symbol migrations (spec 12 §9). Never auto-apply on boot."""
from __future__ import annotations

import fnmatch
import logging
import os
from typing import Any

from ..tags.unit_provenance import (
    UNIT_SOURCE_ENGINE,
    UNIT_SOURCE_IMPORTED,
    effective_unit_source,
    is_operator_locked,
)
from ..utils.ops_controls import OpsControlError
from ..utils.system_event_audit import clip, persist_system_event
from ..utils.unit_symbols import canonical_symbol

_LOGGER = logging.getLogger("pyautomation")

APPLY_ENV = "AUTOMATION_UNIT_MIGRATIONS_APPLY"

# Initial registry (CA-UNIT-10). Only engine/imported/NULL rows.
UNIT_MIGRATIONS: tuple[dict[str, str], ...] = (
    {
        "id": "2026.09.pi-bar-to-pa",
        "name_glob": "PI_*",
        "from_unit": "bar",
        "to_unit": "Pa",
        "variable": "Pressure",
    },
    {
        "id": "2026.09.fi-kgs-to-kgsec",
        "name_glob": "FI_*",
        "from_unit": "kg/s",
        "to_unit": "kg/sec",
        "variable": "MassFlow",
    },
)


def _name_matches(name: str, pattern: str) -> bool:
    short = str(name or "").split(".")[-1]
    return fnmatch.fnmatch(short, pattern) or fnmatch.fnmatch(str(name or ""), pattern)


def _row_symbols(row) -> tuple[str | None, str | None]:
    from ..tags.unit_provenance import unit_symbol_from_fk

    return unit_symbol_from_fk(getattr(row, "unit", None)), unit_symbol_from_fk(
        getattr(row, "display_unit", None)
    )


def _iter_tag_rows():
    from ..dbmodels.tags import Tags

    try:
        return list(Tags.select())
    except Exception:
        _LOGGER.debug("unit migrations: cannot read Tags", exc_info=True)
        return []


def _symbol_needs_migration(symbol: str | None, *, from_raw: str, to_raw: str) -> bool:
    """True when ``symbol`` is still the migration source and not the destination."""
    if symbol is None:
        return False
    from_c = canonical_symbol(from_raw) or from_raw
    to_c = canonical_symbol(to_raw) or to_raw
    if from_c == to_c:
        # Alias pair (kg/s ↔ kg/sec): only the literal source string is pending;
        # do not treat canonical(from) as already-done or we never migrate kg/s.
        if symbol == to_raw:
            return False
        return symbol == from_raw
    sym_c = canonical_symbol(symbol) or symbol
    if symbol == to_raw or sym_c == to_c:
        return False
    return symbol == from_raw or sym_c == from_c


def dry_run_unit_migrations() -> dict[str, Any]:
    """Return planned changes without writing. Safe on boot."""
    planned: list[dict[str, Any]] = []
    skipped_operator = 0
    for spec in UNIT_MIGRATIONS:
        from_raw = spec["from_unit"]
        to_raw = spec["to_unit"]
        for row in _iter_tag_rows():
            name = getattr(row, "name", "") or ""
            if not _name_matches(name, spec["name_glob"]):
                continue
            if is_operator_locked(getattr(row, "unit_source", None)):
                skipped_operator += 1
                continue
            unit_sym, display_sym = _row_symbols(row)
            needs_unit = _symbol_needs_migration(unit_sym, from_raw=from_raw, to_raw=to_raw)
            needs_display = _symbol_needs_migration(display_sym, from_raw=from_raw, to_raw=to_raw)
            if not needs_unit and not needs_display:
                continue
            planned.append(
                {
                    "migration_id": spec["id"],
                    "name": name,
                    "from_unit": from_raw,
                    "to_unit": to_raw,
                    "unit_source": effective_unit_source(getattr(row, "unit_source", None)),
                    "current_unit": unit_sym,
                    "current_display_unit": display_sym,
                }
            )
    return {
        "changes": planned,
        "count": len(planned),
        "skipped_operator": skipped_operator,
        "applied": False,
    }


def log_unit_migrations_dry_run() -> dict[str, Any]:
    report = dry_run_unit_migrations()
    if report["count"]:
        _LOGGER.warning(
            "Unit migrations pending (not applied on boot): count=%s skipped_operator=%s sample=%s",
            report["count"],
            report["skipped_operator"],
            report["changes"][:5],
        )
    else:
        _LOGGER.info("Unit migrations dry-run: no pending symbol changes")
    return report


def _apply_allowed(confirm: bool) -> bool:
    env = os.environ.get(APPLY_ENV, "").strip().lower()
    return bool(confirm) or env in {"1", "true", "yes", "on"}


def apply_unit_migrations(*, confirm: bool = False, user=None) -> dict[str, Any]:
    if not _apply_allowed(confirm):
        raise OpsControlError(
            "confirm=true or AUTOMATION_UNIT_MIGRATIONS_APPLY=1 required to apply unit migrations"
        )
    from ..dbmodels.tags import Tags, Units

    report = dry_run_unit_migrations()
    applied: list[dict[str, Any]] = []
    for change in report["changes"]:
        row = Tags.get_or_none(Tags.name == change["name"])
        if row is None:
            continue
        if is_operator_locked(getattr(row, "unit_source", None)):
            continue
        target = Units.read_by_unit(unit=change["to_unit"])
        if target is None:
            _LOGGER.warning(
                "Unit migration %s skipped: destination %s missing in Units",
                change["migration_id"],
                change["to_unit"],
            )
            continue
        from_sym = change["from_unit"]
        unit_sym, display_sym = _row_symbols(row)
        fields: dict[str, Any] = {"unit_source": UNIT_SOURCE_ENGINE}
        if (canonical_symbol(unit_sym) or unit_sym) == from_sym:
            fields["unit"] = target
        if (canonical_symbol(display_sym) or display_sym) == from_sym:
            fields["display_unit"] = target
        if "unit" not in fields and "display_unit" not in fields:
            continue
        Tags.put(id=row.id, **fields)
        try:
            from .. import PyAutomation
            from ..tags.unit_provenance import align_tag_to_persisted_units

            app = PyAutomation()
            live = app.cvt.get_tag_by_name(change["name"]) if hasattr(app, "cvt") else None
            if live is not None:
                align_tag_to_persisted_units(
                    live,
                    unit=change["to_unit"] if "unit" in fields else None,
                    display_unit=change["to_unit"] if "display_unit" in fields else None,
                    unit_source=UNIT_SOURCE_ENGINE,
                )
        except Exception:
            _LOGGER.debug("CVT align after unit migration skipped", exc_info=True)
        persist_system_event(
            message=clip(f"Unit migrated: {change['name']}", 256),
            description=clip(
                f"{change['from_unit']}→{change['to_unit']} ({change['migration_id']})",
                256,
            ),
            classification="Configuration",
            priority=2,
            criticity=3,
            user=user,
        )
        applied.append(change)
        _LOGGER.warning(
            "Unit migrated: %s %s→%s",
            change["name"],
            change["from_unit"],
            change["to_unit"],
        )
    return {
        "changes": applied,
        "count": len(applied),
        "skipped_operator": report["skipped_operator"],
        "applied": True,
    }
