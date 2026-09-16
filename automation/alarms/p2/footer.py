# -*- coding: utf-8 -*-
"""Footer selector. Context: API. Complexity: O(A log A) A≤100. GATE-60."""
from __future__ import annotations

from .constants import _FOOTER_ACTIVE_CAP, _PRIORITY_DEFAULT


def footer_sort_key(elem: dict) -> tuple:
    """Context: API. Complexity: O(1) per elem."""
    try:
        prio = int(elem.get("priority") if elem.get("priority") is not None else _PRIORITY_DEFAULT)
    except (TypeError, ValueError):
        prio = _PRIORITY_DEFAULT
    ts = elem.get("last_transition_ts") or elem.get("timestamp") or ""
    return (prio, ts)


def select_footer(alarms: list, limit: int = 3) -> list:
    """Context: API. Complexity: O(A log A), A≤100."""
    capped = list(alarms)[:_FOOTER_ACTIVE_CAP]
    ordered = sorted(capped, key=footer_sort_key)
    # priority asc, timestamp desc within same priority
    by_prio: dict[int, list] = {}
    for item in ordered:
        prio = footer_sort_key(item)[0]
        by_prio.setdefault(prio, []).append(item)
    result = []
    for prio in sorted(by_prio):
        group = sorted(
            by_prio[prio],
            key=lambda e: e.get("last_transition_ts") or e.get("timestamp") or "",
            reverse=True,
        )
        result.extend(group)
        if len(result) >= limit:
            break
    return result[:limit]
