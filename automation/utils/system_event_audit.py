# -*- coding: utf-8 -*-
"""Shared, fail-safe persistence for system audit events.

Connection auditors (OPC UA, database, …) must never raise into the caller
and must never block a connection path if the event store is unavailable.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from ..logger.events import EventsLoggerEngine
from ..modules.users.users import Users

MESSAGE_MAX = 256
DESCRIPTION_MAX = 256

_events_engine = EventsLoggerEngine()
_users = Users()
_system_user_lock = threading.Lock()
_system_user = None


def clip(text: Optional[str], max_len: int) -> str:
    normalized = " ".join(str(text or "").replace("\n", " ").split())
    if len(normalized) <= max_len:
        return normalized
    if max_len <= 1:
        return normalized[:max_len]
    return normalized[: max_len - 1] + "…"


def get_system_user():
    """Return the cached `system` user, or look it up. Never caches a miss."""
    global _system_user
    if _system_user is not None:
        return _system_user
    with _system_user_lock:
        if _system_user is not None:
            return _system_user
        try:
            user = _users.get_by_username(username="system")
            if user:
                _system_user = user
            return user
        except Exception:
            return None


def emit_event(event) -> None:
    if event is None:
        return
    try:
        from automation import PyAutomation

        app = PyAutomation()
        if app.sio:
            payload = event.serialize() if hasattr(event, "serialize") else event
            app.sio.emit("on.event", data=payload)
    except Exception:
        logging.getLogger("pyautomation").debug(
            "System audit event emit skipped",
            exc_info=True,
        )


def persist_system_event(
    *,
    message: str,
    description: str,
    classification: str,
    priority: int,
    criticity: int,
    user=None,
    timestamp: Optional[datetime] = None,
) -> bool:
    """Persist a structured system event.

    Returns True if the event was stored (journal and/or remote). Never raises.
    """
    try:
        audit_user = user or get_system_user()
        created = _events_engine.create(
            message=clip(message, MESSAGE_MAX),
            user=audit_user,
            description=clip(description, DESCRIPTION_MAX),
            classification=classification,
            priority=priority,
            criticity=criticity,
            timestamp=timestamp,
        )
        event = created[0] if isinstance(created, tuple) else created
        if event is None:
            return False
        emit_event(event)
        return True
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to persist system audit event",
            exc_info=True,
        )
        return False
