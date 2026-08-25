# -*- coding: utf-8 -*-
"""ISA-18.2 BOOL alarms for catalog sync (fail-safe, never raises).

Acknowledgment is operator-only. Clearing the BOOL moves Unacknowledged →
RTN Unacknowledged and stays there until the operator acks. Repeating the
same BOOL value must not re-annunciate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..utils.connection_alarms import scoped_display_name

_LOGGER = logging.getLogger("pyautomation")

_TAG_UNIT = "adim"
_TAG_VARIABLE = "Adimentional"
_TAG_DATA_TYPE = "boolean"
_ALARM_TYPE = "BOOL"


def _scoped(name: str) -> str:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        if scope.enabled and scope.is_valid:
            return f"{scope.area}.{name}"
    except Exception:
        pass
    return name


def _app():
    from automation import PyAutomation

    return PyAutomation()


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return bool(value)


def _ensure(tag_name: str, alarm_name: str, tag_description: str, alarm_description: str, display: str) -> None:
    app = _app()
    tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        tag, _ = app.create_tag(
            name=tag_name,
            unit=_TAG_UNIT,
            variable=_TAG_VARIABLE,
            data_type=_TAG_DATA_TYPE,
            description=tag_description,
            display_name=display,
            skip_validation=True,
        )
        if tag is None:
            tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
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


def _write(tag_name: str, value: bool) -> None:
    """Edge-trigger only. Same value must not call set_value (no re-annunciate)."""
    app = _app()
    tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        return
    try:
        current = _as_bool(getattr(tag.value, "value", False))
    except Exception:
        current = False
    desired = bool(value)
    if current == desired:
        return
    app.cvt.set_value(id=tag.id, value=desired, timestamp=datetime.now(timezone.utc))


def set_sync_failed(active: bool) -> None:
    try:
        tag = _scoped("SYS.CATALOG.SyncFailed")
        alarm = _scoped("ALM.CATALOG.SyncFailed")
        _ensure(
            tag,
            alarm,
            "True when catalog sync failed repeatedly",
            "Catalog sync failed",
            scoped_display_name("Catalog sync failed"),
        )
        _write(tag, bool(active))
    except Exception:
        _LOGGER.debug("ALM.CATALOG.SyncFailed skipped", exc_info=True)


def set_conflict(active: bool) -> None:
    try:
        tag = _scoped("SYS.CATALOG.Conflict")
        alarm = _scoped("ALM.CATALOG.Conflict")
        _ensure(
            tag,
            alarm,
            "True when unresolved catalog sync conflicts remain",
            "Catalog sync conflict",
            scoped_display_name("Catalog conflict"),
        )
        _write(tag, bool(active))
    except Exception:
        _LOGGER.debug("ALM.CATALOG.Conflict skipped", exc_info=True)


def set_orphan_rows(active: bool) -> None:
    try:
        tag = _scoped("SYS.CATALOG.OrphanRows")
        alarm = _scoped("ALM.CATALOG.OrphanRows")
        _ensure(
            tag,
            alarm,
            "True when catalog child rows keep missing parent FKs after repeated sync cycles",
            "Catalog orphan rows",
            scoped_display_name("Catalog orphan rows"),
        )
        _write(tag, bool(active))
    except Exception:
        _LOGGER.debug("ALM.CATALOG.OrphanRows skipped", exc_info=True)


def set_remote_inconsistency(active: bool) -> None:
    try:
        tag = _scoped("SYS.CATALOG.RemoteInconsistency")
        alarm = _scoped("ALM.CATALOG.RemoteInconsistency")
        _ensure(
            tag,
            alarm,
            "True when remote tagsmachines rows bind a tag to a machine in another area",
            "Catalog remote inconsistency",
            scoped_display_name("Catalog remote inconsistency"),
        )
        _write(tag, bool(active))
    except Exception:
        _LOGGER.debug("ALM.CATALOG.RemoteInconsistency skipped", exc_info=True)


def set_local_only(active: bool) -> None:
    try:
        tag = _scoped("SYS.CATALOG.LocalOnly")
        alarm = _scoped("ALM.CATALOG.LocalOnly")
        _ensure(
            tag,
            alarm,
            "True when this edge has used only the local catalog for over one hour",
            "Catalog local-only too long",
            scoped_display_name("Catalog local only"),
        )
        _write(tag, bool(active))
    except Exception:
        _LOGGER.debug("ALM.CATALOG.LocalOnly skipped", exc_info=True)
