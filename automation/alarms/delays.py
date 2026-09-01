# -*- coding: utf-8 -*-
"""ISA-18.2 On-Delay / Off-Delay helpers for process alarms."""
from __future__ import annotations

DEFAULT_ALARM_DELAY_S = 0.0
MAX_ALARM_DELAY_S = 3600.0
DEFAULT_ALARM_DELAY_UNITS = "seconds"


def clamp_alarm_delay(value, default: float = DEFAULT_ALARM_DELAY_S) -> float:
    """Return a delay in seconds in [0, 3600]. None / invalid → default (0 s)."""
    if value is None:
        return float(default)
    raw = getattr(value, "value", value)
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if seconds < 0.0:
        return 0.0
    if seconds > MAX_ALARM_DELAY_S:
        return MAX_ALARM_DELAY_S
    return seconds


def normalize_delay_units(value, default: str = DEFAULT_ALARM_DELAY_UNITS) -> str:
    text = str(value or default).strip().lower() or default
    return text[:16]
