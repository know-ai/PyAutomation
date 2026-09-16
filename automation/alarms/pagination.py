# -*- coding: utf-8 -*-
"""Forced pagination clamps. SPEC-ISA18-2-CLOSURE-v3 INV-44 / INV-45 / INV-46."""
from __future__ import annotations

CATALOG_PAGE_MAX = 50
HISTORY_PAGE_MAX = 100
ACTIVE_PAGE_MAX = 50
FOOTER_TOP_N = 3


def clamp_page_size(value, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def clamp_catalog_page_size(value, default: int = 50) -> int:
    return clamp_page_size(value, default=default, maximum=CATALOG_PAGE_MAX)


def clamp_history_page_size(value, default: int = 100) -> int:
    return clamp_page_size(value, default=default, maximum=HISTORY_PAGE_MAX)


def clamp_active_page_size(value, default: int = 50) -> int:
    return clamp_page_size(value, default=default, maximum=ACTIVE_PAGE_MAX)
