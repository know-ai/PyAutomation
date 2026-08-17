# -*- coding: utf-8 -*-
"""Classification and field rules for the operator logbook (Bitácora Eterna).

HTTP and HMI decide *what* to write; this module decides *how it is labelled*
so the operator notebook stays distinct from event/alarm comments and HMI telemetry.
"""
from __future__ import annotations

from typing import Optional

from .system_event_audit import clip

WATCHDOG_DESCRIPTION = "memory-watchdog"
CLASS_OPERATIONAL = "Operational"
CLASS_GENERAL = "General"
CLASS_EVENT = "Event"
CLASS_ALARM = "Alarm"
CLASS_SYSTEM = "System"
NOTEBOOK_CLASSIFICATIONS = (CLASS_OPERATIONAL, CLASS_GENERAL)
SHIFT_VALUES = frozenset({"morning", "afternoon", "night"})
MESSAGE_MAX = 256
DESCRIPTION_MAX = 256
USER_NAME_MAX = 64
AREA_MAX = 64
SHIFT_MAX = 32


def classify_write(
    *,
    event_id: object = None,
    alarm_summary_id: object = None,
    description: Optional[str] = None,
) -> str:
    """Server-side classification. The client does not choose the family."""
    if event_id not in (None, ""):
        return CLASS_EVENT
    if alarm_summary_id not in (None, ""):
        return CLASS_ALARM
    if (description or "").strip().lower() == WATCHDOG_DESCRIPTION:
        return CLASS_SYSTEM
    return CLASS_OPERATIONAL


def normalize_shift(value: Optional[str]) -> Optional[str]:
    key = (value or "").strip().lower()
    return key if key in SHIFT_VALUES else None


def clip_message(value: Optional[str]) -> str:
    return clip(value, MESSAGE_MAX)


def clip_description(value: Optional[str]) -> Optional[str]:
    text = clip(value, DESCRIPTION_MAX)
    return text or None


def clip_user_name(value: Optional[str]) -> Optional[str]:
    text = clip(value, USER_NAME_MAX)
    return text or None


def clip_area(value: Optional[str]) -> Optional[str]:
    text = clip(value, AREA_MAX)
    return text or None
