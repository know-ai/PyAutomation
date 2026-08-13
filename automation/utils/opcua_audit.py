# -*- coding: utf-8 -*-
"""Audit trail for OPC UA client connection lifecycle.

Connection and reconnection against OPC UA servers must be persisted in the
Events log for industrial audits. This helper is fail-safe: it never raises
into the caller and never blocks the connection path if the event store is down.
"""
from __future__ import annotations

import logging
from .system_event_audit import clip, get_system_user, persist_system_event

_FAILURE_COOLDOWN_S = 60.0
_CLASSIFICATION = "OPC UA"

_PRIORITY = {
    "CONNECTED": 2,
    "CONNECTION_FAILED": 3,
    "DISCONNECTED": 3,
    "RECONNECTING": 3,
    "RECONNECTED": 2,
    "RECONNECT_FAILED": 4,
}

_CRITICITY = {
    "CONNECTED": 2,
    "CONNECTION_FAILED": 4,
    "DISCONNECTED": 4,
    "RECONNECTING": 3,
    "RECONNECTED": 3,
    "RECONNECT_FAILED": 5,
}

_MESSAGE = {
    "CONNECTED": "OPC UA client connected",
    "CONNECTION_FAILED": "OPC UA client connection failed",
    "DISCONNECTED": "OPC UA client disconnected",
    "RECONNECTING": "OPC UA client reconnecting",
    "RECONNECTED": "OPC UA client reconnected",
    "RECONNECT_FAILED": "OPC UA client reconnect failed",
}


def failure_cooldown_seconds() -> float:
    return _FAILURE_COOLDOWN_S


def _get_system_user():
    return get_system_user()


def record_opcua_connection_event(
    action: str,
    client_name: str,
    server_url: str = "",
    source: str = "",
    reason: str = "",
    error: str = "",
    attempts: int = 0,
    user=None,
) -> bool:
    """Persist a structured OPC UA connection event.

    Returns True if the event was stored. Never raises.
    """
    try:
        action_key = str(action or "").upper()
        if action_key not in _MESSAGE:
            action_key = "DISCONNECTED"

        audit_user = user or _get_system_user()
        if audit_user is None:
            logging.getLogger("pyautomation").warning(
                "OPC UA audit event skipped: system user is not available"
            )
            return False

        parts = [
            f"client={client_name or '-'}",
            f"url={server_url or '-'}",
        ]
        if source:
            parts.append(f"source={source}")
        if reason:
            parts.append(f"reason={reason}")
        if attempts:
            parts.append(f"attempts={int(attempts)}")
        if error:
            parts.append(f"error={error}")

        message = clip(f"{_MESSAGE[action_key]}: {client_name or '-'}", 256)
        description = clip("; ".join(parts), 256)

        return persist_system_event(
            message=message,
            description=description,
            classification=_CLASSIFICATION,
            priority=_PRIORITY[action_key],
            criticity=_CRITICITY[action_key],
            user=audit_user,
        )
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to persist OPC UA connection event",
            exc_info=True,
        )
        return False
