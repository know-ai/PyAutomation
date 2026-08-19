# -*- coding: utf-8 -*-
"""Boolean connection alarms for OPC UA clients and the historian database.

One alarm is created per connection (not per reconnect). The trigger is BOOL:
True means disconnected. The existing ISA 18.2 state machine owns the rest of
the lifecycle (Unacknowledged, Acknowledged, RTN Unacknowledged, Normal).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

_LOGGER = logging.getLogger("pyautomation")

DB_TAG_NAME = "SYS.DB.Disconnected"
DB_ALARM_NAME = "ALM.DB.Connection"
DB_TAG_DESCRIPTION = "True when the historian database is disconnected"
DB_ALARM_DESCRIPTION = "Historian database connection lost"

_TAG_UNIT = "adim"
_TAG_VARIABLE = "Adimentional"
_TAG_DATA_TYPE = "boolean"
_ALARM_TYPE = "BOOL"


def _scoped_name(name: str) -> str:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        if scope.enabled and scope.is_valid:
            return f"{scope.area}.{name}"
    except Exception:
        pass
    return name


def db_tag_name() -> str:
    return _scoped_name(DB_TAG_NAME)


def db_alarm_name() -> str:
    return _scoped_name(DB_ALARM_NAME)


def opcua_tag_name(client_name: str) -> str:
    return _scoped_name(f"SYS.OPCUA.{_sanitize(client_name)}.Disconnected")


def opcua_alarm_name(client_name: str) -> str:
    return _scoped_name(f"ALM.OPCUA.{_sanitize(client_name)}")


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
    return cleaned.strip("._-") or "unnamed"


def _app():
    from automation import PyAutomation

    return PyAutomation()


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(value)


def _connection_alarms_deferred(app) -> bool:
    manager = getattr(app, "opcua_client_manager", None)
    return bool(getattr(manager, "_defer_connection_alarms", False))


def ensure_db_connection_alarm() -> None:
    """Create the database connection BOOL alarm once. Never raises."""
    try:
        app = _app()
        _ensure_bool_alarm(
            app,
            tag_name=db_tag_name(),
            alarm_name=db_alarm_name(),
            tag_description=DB_TAG_DESCRIPTION,
            alarm_description=DB_ALARM_DESCRIPTION,
            display_name="Database Disconnected",
        )
    except Exception:
        _LOGGER.error("Failed to ensure database connection alarm", exc_info=True)


def ensure_opcua_connection_alarm(client_name: str) -> None:
    """Create the OPC UA client connection BOOL alarm once. Never raises."""
    try:
        if not client_name:
            return
        app = _app()
        _ensure_bool_alarm(
            app,
            tag_name=opcua_tag_name(client_name),
            alarm_name=opcua_alarm_name(client_name),
            tag_description=f"True when OPC UA client '{client_name}' is disconnected",
            alarm_description=f"OPC UA client '{client_name}' connection lost",
            display_name=f"OPCUA {client_name} Disconnected",
        )
    except Exception:
        _LOGGER.error(
            "Failed to ensure OPC UA connection alarm for %s",
            client_name,
            exc_info=True,
        )


def set_db_disconnected(disconnected: bool) -> None:
    """Drive the database connection alarm from the live link state. Never raises."""
    try:
        ensure_db_connection_alarm()
        _write_disconnected(db_tag_name(), disconnected)
    except Exception:
        _LOGGER.error("Failed to update database connection alarm", exc_info=True)


def set_opcua_disconnected(client_name: str, disconnected: bool) -> None:
    """Drive the OPC UA connection alarm from the live session state. Never raises."""
    try:
        if not client_name:
            return
        app = _app()
        if _connection_alarms_deferred(app):
            return
        ensure_opcua_connection_alarm(client_name)
        _write_disconnected(opcua_tag_name(client_name), disconnected)
    except Exception:
        _LOGGER.error(
            "Failed to update OPC UA connection alarm for %s",
            client_name,
            exc_info=True,
        )


def sync_opcua_connection_alarms() -> None:
    """Ensure one alarm per configured client and align it with is_connected()."""
    try:
        app = _app()
        clients = getattr(getattr(app, "opcua_client_manager", None), "_clients", {}) or {}
        for client_name, client in list(clients.items()):
            try:
                disconnected = not bool(client.is_connected())
            except Exception:
                disconnected = True
            set_opcua_disconnected(client_name, disconnected)
    except Exception:
        _LOGGER.error("Failed to sync OPC UA connection alarms", exc_info=True)


def rename_opcua_connection_alarm(old_client_name: str, new_client_name: str) -> None:
    """Keep the same alarm instance when an OPC UA client is renamed. Never raises."""
    try:
        if not old_client_name or not new_client_name or old_client_name == new_client_name:
            return
        if opcua_tag_name(old_client_name) == opcua_tag_name(new_client_name):
            return
        app = _app()
        old_tag_name = opcua_tag_name(old_client_name)
        new_tag_name = opcua_tag_name(new_client_name)
        old_alarm_name = opcua_alarm_name(old_client_name)
        new_alarm_name = opcua_alarm_name(new_client_name)
        new_display = f"OPCUA {new_client_name} Disconnected"

        tag = app.cvt.get_tag_by_name(old_tag_name)
        if tag is not None:
            app.update_tag(
                id=tag.id,
                name=new_tag_name,
                display_name=new_display,
                description=f"True when OPC UA client '{new_client_name}' is disconnected",
            )

        alarm = app.alarm_manager.get_alarm_by_name(old_alarm_name)
        if alarm is not None:
            app.update_alarm(
                id=alarm.identifier,
                name=new_alarm_name,
                tag=new_tag_name,
                description=f"OPC UA client '{new_client_name}' connection lost",
            )
    except Exception:
        _LOGGER.error(
            "Failed to rename OPC UA connection alarm from %s to %s",
            old_client_name,
            new_client_name,
            exc_info=True,
        )


def remove_opcua_connection_alarm(client_name: str) -> None:
    """Drop the alarm and tag when the OPC UA client connection is deleted."""
    try:
        if not client_name:
            return
        app = _app()
        alarm = app.alarm_manager.get_alarm_by_name(opcua_alarm_name(client_name))
        if alarm is not None:
            app.delete_alarm(id=alarm.identifier)
        tag = app.cvt.get_tag_by_name(opcua_tag_name(client_name))
        if tag is not None:
            app.delete_tag(id=tag.id)
    except Exception:
        _LOGGER.error(
            "Failed to remove OPC UA connection alarm for %s",
            client_name,
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
    elif getattr(app, "is_db_connected", lambda: False)():
        try:
            app.logger_engine.set_tag(tag=tag)
        except Exception:
            _LOGGER.debug("Connection alarm tag persist skipped", exc_info=True)

    if tag is None:
        _LOGGER.warning("Cannot create connection alarm '%s': tag '%s' missing", alarm_name, tag_name)
        return

    alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
    if alarm is None:
        alarm, _ = app.create_alarm(
            name=alarm_name,
            tag=tag_name,
            alarm_type=_ALARM_TYPE,
            trigger_value=True,
            description=alarm_description,
            skip_validation=True,
        )
    elif getattr(app, "is_db_connected", lambda: False)():
        try:
            app.alarms_engine.create(
                id=alarm.identifier,
                name=alarm.name,
                tag=tag_name,
                trigger_type=_ALARM_TYPE,
                trigger_value=True,
                description=alarm_description,
            )
        except Exception:
            _LOGGER.debug("Connection alarm persist skipped", exc_info=True)


def _write_disconnected(tag_name: str, disconnected: bool) -> None:
    app = _app()
    tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        return
    current = False
    try:
        current = _as_bool(getattr(tag.value, "value", False))
    except Exception:
        current = False
    if current is bool(disconnected):
        return
    timestamp = datetime.now(timezone.utc)
    app.cvt.set_value(id=tag.id, value=bool(disconnected), timestamp=timestamp)
