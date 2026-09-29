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


def scoped_display_name(friendly: str) -> str:
    """Globally unique Tags.display_name in multi-edge (area prefix)."""
    label = str(friendly or "").strip()
    if not label:
        return label
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        if getattr(scope, "enabled", False) and getattr(scope, "area", None):
            return f"{scope.area} · {label}"
    except Exception:
        pass
    return label


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
            display_name=scoped_display_name("Database Disconnected"),
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
            display_name=scoped_display_name(f"OPCUA {client_name} Disconnected"),
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
            if getattr(client, "_awaiting_embedded", False):
                continue
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
        new_display = scoped_display_name(f"OPCUA {new_client_name} Disconnected")

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


def connection_client_from_alarm(alarm_name: str) -> str | None:
    """Client name encoded in ``ALM.OPCUA.<client>``. Complexity: O(1)."""
    marker = ".ALM.OPCUA."
    text = str(alarm_name or "")
    if marker not in text:
        return None
    client = text.split(marker, 1)[1].strip()
    return client or None


def _client_still_defined(client_name: str) -> bool:
    app = _app()
    manager = getattr(app, "opcua_client_manager", None)
    getter = getattr(manager, "get", None)
    if callable(getter):
        try:
            if getter(client_name) is not None:
                return True
        except Exception:
            return True
    try:
        from ..dbmodels import OPCUA

        if OPCUA.get_by_client_name(client_name=client_name) is not None:
            return True
    except Exception:
        return True
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        for row in LocalCatalogProvider().read_all("opcua"):
            if str(row.get("client_name") or "") == client_name:
                return True
    except Exception:
        return True
    return False


def retire_orphan_connection_alarm(alarm_name: str, tag_name: str) -> bool:
    """Drop a connection alarm whose OPC UA client is already gone. Complexity: O(1)."""
    client_name = connection_client_from_alarm(alarm_name)
    if not client_name or _client_still_defined(client_name):
        return False
    app = _app()
    if app.cvt.get_tag_by_name(tag_name) is not None:
        return False
    _LOGGER.debug(
        "Retired OPC UA connection alarm %s; client %s is no longer defined",
        alarm_name,
        client_name,
    )
    remove_opcua_connection_alarm(client_name)
    return True


def _retire_catalog_alarm(alarm_name: str) -> None:
    """Logical-delete the historian row when the alarm is not in memory yet."""
    from ..dbmodels.alarms import Alarms

    try:
        row = Alarms.read_by_name(name=alarm_name)
    except Exception:
        row = None
    identifier = getattr(row, "identifier", None) if row is not None else None
    app = _app()
    if identifier and getattr(app, "is_db_connected", lambda: False)():
        try:
            app.alarms_engine.delete(id=identifier)
            return
        except Exception:
            _LOGGER.debug("historian connection-alarm retire skipped name=%s", alarm_name, exc_info=True)
    if not identifier:
        return
    try:
        from ..catalog.mutations import soft_delete_alarm_local

        soft_delete_alarm_local(identifier=identifier)
    except Exception:
        _LOGGER.debug("local connection-alarm retire skipped name=%s", alarm_name, exc_info=True)


def remove_opcua_connection_alarm(client_name: str) -> None:
    """Drop the alarm and tag when the OPC UA client connection is deleted."""
    try:
        if not client_name:
            return
        app = _app()
        alarm_name = opcua_alarm_name(client_name)
        tag_name = opcua_tag_name(client_name)
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
        if alarm is not None:
            app.delete_alarm(id=alarm.identifier)
        else:
            _retire_catalog_alarm(alarm_name)
        tag = app.cvt.get_tag_by_name(tag_name)
        if tag is not None:
            blocked = app.delete_tag(id=tag.id)
            if blocked:
                _LOGGER.warning("OPC UA connection tag %s was not removed: %s", tag_name, blocked)
        try:
            from ..opcua_server.runtime import release_watched_name

            server = getattr(app, "opcua_server", None)
            release_watched_name(server, tag_name)
            release_watched_name(server, alarm_name)
        except Exception:
            _LOGGER.debug("OPC UA watch release skipped client=%s", client_name, exc_info=True)
    except Exception:
        _LOGGER.error(
            "Failed to remove OPC UA connection alarm for %s",
            client_name,
            exc_info=True,
        )


def _revive_inactive_tag(app, tag_name: str) -> str | None:
    """Force ``active`` so the next create reuses the catalog row. Complexity: O(1)."""
    identifier = None
    if getattr(app, "is_db_connected", lambda: False)():
        try:
            from ..dbmodels.tags import Tags

            row = Tags.read_by_name(tag_name)
        except Exception:
            row = None
        if row is not None:
            identifier = getattr(row, "identifier", None)
            if not bool(getattr(row, "active", True)):
                Tags.put(id=row.id, active=True)
    try:
        from ..catalog.mutations import reactivate_tag_local

        local_id = reactivate_tag_local(name=tag_name, identifier=identifier)
        identifier = identifier or local_id
    except Exception:
        _LOGGER.debug("Connection alarm tag reactivate skipped name=%s", tag_name, exc_info=True)
    return str(identifier) if identifier else None


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
        revived_id = _revive_inactive_tag(app, tag_name)
        create_kwargs = {}
        if revived_id:
            create_kwargs["id"] = revived_id
        tag, _ = app.create_tag(
            name=tag_name,
            unit=_TAG_UNIT,
            variable=_TAG_VARIABLE,
            data_type=_TAG_DATA_TYPE,
            description=tag_description,
            display_name=display_name,
            skip_validation=True,
            **create_kwargs,
        )
        if tag is None:
            tag = app.cvt.get_tag_by_name(tag_name)
    if tag is None:
        from .rate_limited_log import warning_once

        warning_once(
            _LOGGER,
            f"connection-alarm-tag-missing:{alarm_name}",
            "Cannot create connection alarm '%s': tag '%s' missing",
            alarm_name,
            tag_name,
        )
        return

    historian_ok = True
    if getattr(app, "is_db_connected", lambda: False)():
        try:
            from ..catalog.runtime_tag import ensure_tag_historian_catalog

            historian_ok = bool(
                ensure_tag_historian_catalog(tag, reason=f"connection-alarm:{alarm_name}")
            )
        except Exception:
            try:
                app.logger_engine.set_tag(tag=tag)
            except Exception:
                _LOGGER.debug("Connection alarm tag persist skipped", exc_info=True)

    alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
    if alarm is None:
        if getattr(app, "is_db_connected", lambda: False)() and not historian_ok:
            from .rate_limited_log import warning_once

            warning_once(
                _LOGGER,
                f"connection-alarm-historian:{alarm_name}",
                "Deferred connection alarm '%s': tag '%s' not in historian Tags",
                alarm_name,
                tag_name,
            )
            return
        alarm, _ = app.create_alarm(
            name=alarm_name,
            tag=tag_name,
            alarm_type=_ALARM_TYPE,
            trigger_value=True,
            description=alarm_description,
            skip_validation=True,
        )
        return

    bound = ""
    subject = getattr(alarm, "tag", None)
    if isinstance(subject, str):
        bound = subject
    elif subject is not None:
        bound = str(getattr(subject, "name", "") or "")
    trigger = getattr(alarm, "alarm_setpoint", None)
    kind = getattr(getattr(trigger, "type", None), "value", None) or str(getattr(trigger, "type", "") or "")
    if bound != tag_name or str(kind).upper() not in {"BOOL", "BOOLEAN"}:
        from .rate_limited_log import info_once

        info_once(
            _LOGGER,
            f"diagnostic-rebind:{alarm_name}",
            "Rebinding diagnostic alarm %s from %s/%s onto %s/BOOL",
            alarm_name,
            bound or "?",
            kind or "?",
            tag_name,
        )
        try:
            app.update_alarm(
                id=alarm.identifier,
                tag=tag_name,
                alarm_type=_ALARM_TYPE,
                trigger_value=True,
                description=alarm_description,
            )
        except Exception:
            _LOGGER.warning("Diagnostic alarm rebind failed for %s", alarm_name, exc_info=True)
            return
        rebound = app.alarm_manager.get_alarm_by_name(alarm_name)
        if rebound is not None:
            try:
                from datetime import datetime, timezone

                current = (getattr(rebound.current_state, "name", None) or "").lower()
                if current == "unack_alarm":
                    rebound.normal_condition()
                    current = (getattr(rebound.current_state, "name", None) or "").lower()
                if current == "rtn_unack":
                    rebound._apply_acknowledge(datetime.now(timezone.utc))
                elif current == "ack_alarm":
                    rebound.normal_condition()
                value = getattr(tag, "value", None)
                if value is not None:
                    ts = getattr(tag, "timestamp", None) or datetime.now(timezone.utc)
                    rebound.notify(tag=tag.name, value=value, timestamp=ts)
            except Exception:
                _LOGGER.debug("Diagnostic alarm rebind notify skipped for %s", alarm_name, exc_info=True)
        return

    desired = (alarm_description or "").strip()
    current = (getattr(alarm, "description", None) or "").strip()
    if desired and desired != current:
        # Refresh description (e.g. PERF thresholds) in CVT + local catalog + historian.
        try:
            app.update_alarm(id=alarm.identifier, description=desired)
            return
        except Exception:
            _LOGGER.debug("Alarm description refresh skipped for %s", alarm_name, exc_info=True)

    if getattr(app, "is_db_connected", lambda: False)():
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
