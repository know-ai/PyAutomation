# -*- coding: utf-8 -*-
"""Canonical unit symbols and aliases (spec 12 §8).

Kept in ``utils`` so ``EngUnit`` can canonicalize without importing ``variables``
(circular: variable classes subclass EngUnit).
"""
from __future__ import annotations

UNIT_ALIASES: dict[str, str] = {
    "kg/s": "kg/sec",
    "m3/s": "m3/sec",
    "m³": "m3",
    "m³/s": "m3/sec",
    "m³/sec": "m3/sec",
    "m³/min": "m3/min",
    "m³/hr": "m3/hr",
    "m³/day": "m3/day",
    "°K": "K",
    "barg": "bar",
}


def canonical_symbol(symbol: str | None) -> str | None:
    """Return the catalogue symbol for ``symbol``, or the stripped original."""
    if symbol is None:
        return None
    needle = str(symbol).strip()
    if not needle:
        return None
    return UNIT_ALIASES.get(needle, needle)
