# -*- coding: utf-8 -*-
"""unit_source / alignment helpers (spec 12 §4 and §6)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

UNIT_SOURCE_ENGINE = "engine"
UNIT_SOURCE_OPERATOR = "operator"
UNIT_SOURCE_IMPORTED = "imported"
UNIT_SOURCES = frozenset(
    {UNIT_SOURCE_ENGINE, UNIT_SOURCE_OPERATOR, UNIT_SOURCE_IMPORTED}
)

_LOGGER = logging.getLogger("pyautomation")


def effective_unit_source(value) -> str:
    """NULL / blank legacy rows count as engine for migrations."""
    text = str(value or "").strip().lower()
    if not text:
        return UNIT_SOURCE_ENGINE
    return text


def is_operator_locked(value) -> bool:
    return effective_unit_source(value) == UNIT_SOURCE_OPERATOR


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def unit_symbol_from_fk(obj) -> str | None:
    """Best-effort symbol from a Units row, dict, or plain string."""
    if obj is None:
        return None
    if isinstance(obj, str):
        text = obj.strip()
        if not text or text.isdigit():
            return None
        return text
    symbol = getattr(obj, "unit", None)
    if symbol:
        return str(symbol)
    if isinstance(obj, dict):
        sym = obj.get("unit")
        if sym and not str(sym).isdigit():
            return str(sym)
        return None
    return None


def tag_eng_accepts_symbol(tag, symbol: str | None) -> bool:
    """True when the tag's EngUnit catalogue includes ``symbol``."""
    if not symbol or tag is None:
        return False
    from ..utils.unit_symbols import canonical_symbol

    needle = canonical_symbol(symbol) or symbol
    conversions = getattr(getattr(tag, "value", None), "conversions", None) or {}
    if conversions:
        return needle in conversions
    variable = getattr(tag, "variable", None)
    if variable:
        from ..variables import unit_belongs_to_variable

        return unit_belongs_to_variable(needle, variable)
    return False


def historian_units_need_engine_repair(tag, row) -> bool:
    """True when an engine-owned historian row disagrees with the live CVT tag."""
    if tag is None or row is None:
        return False
    if is_operator_locked(getattr(row, "unit_source", None)):
        return False
    from ..utils.unit_symbols import canonical_symbol

    cvt = canonical_symbol(getattr(tag, "unit", None)) or getattr(tag, "unit", None)
    hist = unit_symbol_from_fk(getattr(row, "unit", None))
    if not cvt or not hist:
        return False
    if cvt == hist:
        display_cvt = canonical_symbol(getattr(tag, "display_unit", None)) or getattr(
            tag, "display_unit", None
        )
        display_hist = unit_symbol_from_fk(getattr(row, "display_unit", None))
        if display_cvt and display_hist and display_cvt != display_hist:
            return True
        return False
    # Poisoned FK (e.g. Adimentional tag pointing at Volume.m3) must be rewritten.
    if not tag_eng_accepts_symbol(tag, hist):
        return True
    return True


def align_tag_to_persisted_units(tag, *, unit=None, display_unit=None, unit_source=None) -> None:
    """Point a live CVT tag at the symbols that already won in BD/catalog.

    Never applies a symbol the tag's EngUnit / variable cannot accept — that
    pattern is how cross-DB ``unit_id`` drift (SQLite id ≠ PG id) used to
    force ``m3`` onto ``Adimentional`` SYS.* tags.
    """
    if tag is None:
        return
    if unit:
        if not tag_eng_accepts_symbol(tag, unit):
            _LOGGER.debug(
                "Skip align unit=%s for tag=%s variable=%s (incompatible EngUnit)",
                unit,
                getattr(tag, "name", None),
                getattr(tag, "variable", None),
            )
        elif hasattr(tag, "set_unit"):
            try:
                tag.set_unit(unit=unit)
            except Exception:
                tag.unit = unit
        else:
            tag.unit = unit
    if display_unit:
        if not tag_eng_accepts_symbol(tag, display_unit):
            fallback = getattr(tag, "unit", None) or getattr(
                getattr(tag, "value", None), "unit", None
            )
            display_unit = fallback if tag_eng_accepts_symbol(tag, fallback) else None
        if display_unit:
            if hasattr(tag, "set_display_unit"):
                try:
                    tag.set_display_unit(unit=display_unit)
                except Exception:
                    tag.display_unit = display_unit
            else:
                tag.display_unit = display_unit
    if unit_source is not None:
        tag.unit_source = effective_unit_source(unit_source)


def align_tag_to_historian_row(tag, row) -> None:
    if tag is None or row is None:
        return
    align_tag_to_persisted_units(
        tag,
        unit=unit_symbol_from_fk(getattr(row, "unit", None)),
        display_unit=unit_symbol_from_fk(getattr(row, "display_unit", None)),
        unit_source=getattr(row, "unit_source", None),
    )
    locked = getattr(row, "unit_locked_at", None)
    if locked is not None:
        tag.unit_locked_at = locked
