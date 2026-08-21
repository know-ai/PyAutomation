# -*- coding: utf-8 -*-
"""ISA-18.2 BOOL alarms for process-variable quality (BAD / stale).

Lazy-created per process tag. Independent from ALM.OPCUA.* (link) and from
process setpoints. Never raises into the acquisition path.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from .connection_alarms import scoped_display_name

_LOGGER = logging.getLogger("pyautomation")

_TAG_UNIT = "adim"
_TAG_VARIABLE = "Adimentional"
_TAG_DATA_TYPE = "boolean"
_ALARM_TYPE = "BOOL"

_SKIP_PREFIXES = (
    "SYS.",
    "ALM.",
    "SYS.QUALITY.",
    "ALM.QUALITY.",
)


def _scoped_name(name: str) -> str:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        if scope.enabled and scope.is_valid:
            return f"{scope.area}.{name}"
    except Exception:
        pass
    return name


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
    return cleaned.strip("._-") or "unnamed"


def quality_tag_name(process_tag_name: str) -> str:
    return _scoped_name(f"SYS.QUALITY.{_sanitize(process_tag_name)}")


def quality_alarm_name(process_tag_name: str) -> str:
    return _scoped_name(f"ALM.QUALITY.{_sanitize(process_tag_name)}")


def is_quality_subject(tag) -> bool:
    """True when this process tag may own an ALM.QUALITY.* alarm."""
    name = getattr(tag, "name", None) or ""
    if not name:
        return False
    if name.endswith(".f"):
        return False
    if name.startswith(_SKIP_PREFIXES):
        return False
    if ".SYS.QUALITY." in name or name.startswith("SYS.QUALITY."):
        return False
    if ".ALM.QUALITY." in name or name.startswith("ALM.QUALITY."):
        return False
    if ".QUALITY." in name and (name.startswith("SYS.") or ".SYS." in name):
        return False
    return True


def _app():
    from automation import PyAutomation

    return PyAutomation()


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(value)


def ensure_quality_alarm(process_tag_name: str) -> None:
    """Create the quality BOOL alarm once. Never raises."""
    try:
        if not process_tag_name:
            return
        app = _app()
        tag_name = quality_tag_name(process_tag_name)
        alarm_name = quality_alarm_name(process_tag_name)
        display = scoped_display_name(f"Quality {process_tag_name}")
        _ensure_bool_alarm(
            app,
            tag_name=tag_name,
            alarm_name=alarm_name,
            tag_description=f"True when process tag '{process_tag_name}' is BAD or stale",
            alarm_description=f"Signal quality BAD/stale on '{process_tag_name}'",
            display_name=display,
        )
    except Exception:
        _LOGGER.error(
            "Failed to ensure quality alarm for %s",
            process_tag_name,
            exc_info=True,
        )


def set_quality_degraded(process_tag_name: str, degraded: bool) -> None:
    """Drive ALM.QUALITY.<tag> from PV quality. Never raises."""
    try:
        if not process_tag_name:
            return
        ensure_quality_alarm(process_tag_name)
        _write_bool(quality_tag_name(process_tag_name), bool(degraded))
    except Exception:
        _LOGGER.error(
            "Failed to update quality alarm for %s",
            process_tag_name,
            exc_info=True,
        )


def _ensure_bool_alarm(
    app,
    *,
    tag_name: str,
    alarm_name: str,
    tag_description: str,
    alarm_description: str,
    display_name: str,
) -> None:
    tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        tag, _ = app.create_tag(
            name=tag_name,
            unit=_TAG_UNIT,
            variable=_TAG_VARIABLE,
            data_type=_TAG_DATA_TYPE,
            description=tag_description,
            display_name=display_name,
            skip_validation=True,
        )
        if tag is None:
            tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        _LOGGER.warning("Cannot create quality alarm '%s': tag '%s' missing", alarm_name, tag_name)
        return

    alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
    if alarm is None:
        app.create_alarm(
            name=alarm_name,
            tag=tag_name,
            alarm_type=_ALARM_TYPE,
            trigger_value=True,
            description=alarm_description,
            skip_validation=True,
        )


def _write_bool(tag_name: str, value: bool) -> None:
    app = _app()
    tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        return
    current = False
    try:
        current = _as_bool(getattr(tag.value, "value", False))
    except Exception:
        current = False
    if current is bool(value):
        return
    timestamp = datetime.now(timezone.utc)
    app.cvt.set_value(id=tag.id, value=bool(value), timestamp=timestamp)
