# -*- coding: utf-8 -*-
"""Helpers for plant-wide historian reads.

Runtime catalog queries stay partitioned by node area. Historical GET/POST
reads are global unless the client opts into an ``area`` filter.
"""
from __future__ import annotations

_GLOBAL_AREA_TOKENS = frozenset({"", "all", "*", "plant", "global"})


def optional_area(value: str | None) -> str | None:
    """Return a concrete area filter, or ``None`` for a plant-wide query.

    Blank values and tokens ``all`` / ``*`` / ``plant`` / ``global`` omit the
    filter. The node identity is never inferred here.
    """
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in _GLOBAL_AREA_TOKENS:
        return None
    return normalized
