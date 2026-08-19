# -*- coding: utf-8 -*-
"""User-alarm name qualification for multi-edge HMI creates (alarm.Site.Area.Base)."""
from __future__ import annotations

import os
from typing import NamedTuple


class AlarmNameError(ValueError):
    """Operator-facing alarm name validation failure (HTTP 400)."""


class QualifiedAlarmName(NamedTuple):
    name: str
    base_name: str


def alarm_name_validation_skipped(environ: dict | None = None) -> bool:
    env = os.environ if environ is None else environ
    raw = (env.get("AUTOMATION_SKIP_ALARM_VALIDATION") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _base_segment(name: str) -> str:
    parts = [p for p in (name or "").split(".") if p]
    return parts[-1] if parts else (name or "").strip()


def qualify_user_alarm_name(
    name: str,
    site: str | None,
    area: str | None,
) -> QualifiedAlarmName:
    """Qualify a manual HMI alarm name to ``alarm.Site.Area.Base``.

    Raises ``AlarmNameError`` for 2-part names, foreign 4-part names, and
    names with more than 4 parts (reserved for internal engine alarms).
    """
    raw = (name or "").strip()
    if not raw:
        raise AlarmNameError("Alarm name is required")
    if not site or not area:
        return QualifiedAlarmName(name=raw, base_name=_base_segment(raw))

    prefix = f"alarm.{site}.{area}"
    parts = [p for p in raw.split(".") if p]
    if len(parts) == 1:
        base = parts[0]
        return QualifiedAlarmName(name=f"{prefix}.{base}", base_name=base)
    if len(parts) == 2:
        raise AlarmNameError(
            f"Alarm name must be in format 'alarm.Site.Area.AlarmName' or just 'AlarmName'. "
            f"Use '{prefix}.{parts[-1]}'."
        )
    if len(parts) == 4:
        lead, input_site, input_area, base = parts
        if lead != "alarm":
            raise AlarmNameError("Alarm name must start with 'alarm.'")
        if input_site != site and input_area != area:
            raise AlarmNameError(
                f"Site/Area mismatch. This node is {site}.{area}. "
                f"Please use '{prefix}.{base}'."
            )
        if input_area != area:
            raise AlarmNameError(
                f"Area mismatch. This node is {site}.{area}. "
                f"Please use '{prefix}.{base}'."
            )
        if input_site != site:
            raise AlarmNameError(
                f"Site mismatch. This node is {site}.{area}. "
                f"Please use '{prefix}.{base}'."
            )
        return QualifiedAlarmName(name=raw, base_name=base)
    if len(parts) == 5:
        lead, input_site, input_area, base, suffix = parts
        if lead != "alarm":
            raise AlarmNameError("Alarm name must start with 'alarm.'")
        allowed_suffixes = {"HH", "H", "L", "LL", "B"}
        if suffix not in allowed_suffixes:
            raise AlarmNameError(
                "For user alarms, use 'alarm.Site.Area.AlarmName' or just 'AlarmName'. "
                "Names with more than 4 parts are reserved for the system."
            )
        if input_site != site and input_area != area:
            raise AlarmNameError(
                f"Site/Area mismatch. This node is {site}.{area}. "
                f"Please use '{prefix}.{base}.{suffix}'."
            )
        if input_area != area:
            raise AlarmNameError(
                f"Area mismatch. This node is {site}.{area}. "
                f"Please use '{prefix}.{base}.{suffix}'."
            )
        if input_site != site:
            raise AlarmNameError(
                f"Site mismatch. This node is {site}.{area}. "
                f"Please use '{prefix}.{base}.{suffix}'."
            )
        return QualifiedAlarmName(name=raw, base_name=f"{base}.{suffix}")
    if len(parts) > 4:
        raise AlarmNameError(
            "For user alarms, use 'alarm.Site.Area.AlarmName' or just 'AlarmName'. "
            "Names with more than 4 parts are reserved for the system."
        )
    raise AlarmNameError(
        "Invalid alarm name format. Use 'alarm.Site.Area.AlarmName' or just 'AlarmName'. "
        "Names with more than 4 parts are reserved for internal system alarms."
    )
