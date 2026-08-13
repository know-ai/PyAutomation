# -*- coding: utf-8 -*-
"""Audit trail for core ↔ database connection lifecycle.

While the database is down the Events table cannot be written. This auditor
keeps a small in-memory buffer (one DISCONNECTED, one RECONNECTING, and at
most one CONNECTION_FAILED per outage) and flushes it when the link returns,
preserving original timestamps. Reconnect failures are summarized on the
RECONNECTED event instead of being queued every watchdog cycle.

Never include credentials in event descriptions. Never raise into the caller.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from .system_event_audit import (
    DESCRIPTION_MAX,
    clip,
    persist_system_event,
)

_CLASSIFICATION = "Database"
_PENDING_CAP = 8
_SENSITIVE_KEYS = {"password", "passwd", "pwd", "secret", "token"}

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
    "CONNECTED": "Database connected",
    "CONNECTION_FAILED": "Database connection failed",
    "DISCONNECTED": "Database disconnected",
    "RECONNECTING": "Database reconnecting",
    "RECONNECTED": "Database reconnected",
    "RECONNECT_FAILED": "Database reconnect failed",
}

_REPLACEABLE_ACTIONS = frozenset({"CONNECTION_FAILED", "RECONNECT_FAILED"})
_SKIP_ON_RECOVERY = frozenset({"RECONNECT_FAILED"})


@dataclass
class PendingAuditEvent:
    action: str
    description: str
    timestamp: datetime


def summarize_db_config(config: Optional[dict]) -> str:
    """Build a credential-free summary of the DB target for event descriptions."""
    if not isinstance(config, dict) or not config:
        return "target=unknown"

    dbtype = str(config.get("dbtype") or "unknown")
    if dbtype.lower() == "sqlite":
        return f"type=sqlite dbfile={config.get('dbfile') or '-'}"

    parts = [f"type={dbtype}"]
    for key in ("host", "port", "name", "user"):
        if key in _SENSITIVE_KEYS:
            continue
        value = config.get(key)
        if value is not None and str(value) != "":
            parts.append(f"{key}={value}")
    return " ".join(parts) if len(parts) > 1 else f"type={dbtype}"


def build_db_event_description(
    target: str = "",
    source: str = "",
    reason: str = "",
    attempts: int = 0,
    error: str = "",
) -> str:
    parts = []
    if target:
        parts.append(target)
    if source:
        parts.append(f"source={source}")
    if reason:
        parts.append(f"reason={reason}")
    if attempts:
        parts.append(f"attempts={int(attempts)}")
    if error:
        parts.append(f"error={error}")
    return clip("; ".join(parts) if parts else "target=unknown", DESCRIPTION_MAX)


class DatabaseConnectionAuditor:
    """Tracks core↔DB lifecycle and persists Events without flooding the log."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._state = "unknown"
            self._ever_connected = False
            self._attempts = 0
            self._last_error = ""
            self._target = "target=unknown"
            self._pending: list[PendingAuditEvent] = []

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def pending_actions(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(item.action for item in self._pending)

    def notify_connect_success(self, source: str = "connect", target: str = "") -> None:
        try:
            with self._lock:
                self._remember_target(target)
                self._flush_locked(skip_actions=_SKIP_ON_RECOVERY)
                action = (
                    "RECONNECTED"
                    if self._state == "disconnected" and self._ever_connected
                    else "CONNECTED"
                )
                description = build_db_event_description(
                    target=self._target,
                    source=source,
                    attempts=self._attempts if action == "RECONNECTED" else 0,
                    error=self._last_error if action == "RECONNECTED" else "",
                )
                self._emit_locked(action, description)
                self._mark_connected()
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database connect-success audit failed",
                exc_info=True,
            )

    def notify_connect_failure(
        self,
        source: str = "connect",
        target: str = "",
        error: str = "",
    ) -> None:
        try:
            with self._lock:
                self._remember_target(target)
                self._last_error = str(error or "")
                if self._state == "connected":
                    self._state = "disconnected"
                description = build_db_event_description(
                    target=self._target,
                    source=source,
                    reason="initial-connect",
                    error=self._last_error,
                )
                self._emit_locked("CONNECTION_FAILED", description)
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database connect-failure audit failed",
                exc_info=True,
            )

    def notify_link_lost(self, source: str = "watchdog", target: str = "") -> None:
        try:
            with self._lock:
                if self._state != "connected":
                    return
                self._remember_target(target)
                self._state = "disconnected"
                self._attempts = 0
                description = build_db_event_description(
                    target=self._target,
                    source=source,
                    reason="connection-lost",
                )
                self._emit_locked("DISCONNECTED", description)
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database link-lost audit failed",
                exc_info=True,
            )

    def notify_reconnect_attempt(self, source: str = "reconnect", target: str = "") -> None:
        try:
            with self._lock:
                self._remember_target(target)
                self._attempts += 1
                if self._state == "connected" or self._attempts != 1:
                    return
                description = build_db_event_description(
                    target=self._target,
                    source=source,
                    reason="watchdog-reconnect" if source == "watchdog" else "reconnect",
                    attempts=self._attempts,
                )
                self._emit_locked("RECONNECTING", description)
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database reconnect-attempt audit failed",
                exc_info=True,
            )

    def notify_reconnect_success(self, source: str = "reconnect", target: str = "") -> None:
        try:
            with self._lock:
                self._remember_target(target)
                self._flush_locked(skip_actions=_SKIP_ON_RECOVERY)
                action = "RECONNECTED" if self._ever_connected else "CONNECTED"
                description = build_db_event_description(
                    target=self._target,
                    source=source,
                    attempts=self._attempts,
                    error=self._last_error,
                )
                self._emit_locked(action, description)
                self._mark_connected()
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database reconnect-success audit failed",
                exc_info=True,
            )

    def notify_reconnect_failure(
        self,
        source: str = "reconnect",
        target: str = "",
        error: str = "",
    ) -> None:
        """Remember the last error; do not enqueue a row per watchdog cycle."""
        try:
            with self._lock:
                self._remember_target(target)
                self._last_error = str(error or "")
                if self._state == "connected":
                    self._state = "disconnected"
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database reconnect-failure audit failed",
                exc_info=True,
            )

    def notify_disconnect_requested(self, source: str = "disconnect", target: str = "") -> None:
        try:
            with self._lock:
                if self._state != "connected":
                    return
                self._remember_target(target)
                description = build_db_event_description(
                    target=self._target,
                    source=source,
                    reason="requested",
                )
                self._emit_locked("DISCONNECTED", description)
                self._state = "disconnected"
                self._attempts = 0
                self._last_error = ""
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database disconnect audit failed",
                exc_info=True,
            )

    def flush(self) -> None:
        try:
            with self._lock:
                self._flush_locked(skip_actions=_SKIP_ON_RECOVERY)
        except Exception:
            logging.getLogger("pyautomation").error(
                "Database audit flush failed",
                exc_info=True,
            )

    def _remember_target(self, target: str) -> None:
        if target:
            self._target = target

    def _mark_connected(self) -> None:
        self._state = "connected"
        self._ever_connected = True
        self._attempts = 0
        self._last_error = ""
        self._pending = [
            item for item in self._pending if item.action not in _SKIP_ON_RECOVERY
        ]

    def _emit_locked(self, action: str, description: str, timestamp: Optional[datetime] = None) -> None:
        action_key = action if action in _MESSAGE else "DISCONNECTED"
        ts = timestamp or datetime.now(timezone.utc)
        persisted = False
        try:
            persisted = bool(
                persist_system_event(
                    message=_MESSAGE[action_key],
                    description=description,
                    classification=_CLASSIFICATION,
                    priority=_PRIORITY[action_key],
                    criticity=_CRITICITY[action_key],
                    timestamp=ts,
                )
            )
        except Exception:
            logging.getLogger("pyautomation").debug(
                "Database audit persist skipped",
                exc_info=True,
            )
        if persisted:
            return
        self._enqueue_locked(action_key, description, ts)

    def _enqueue_locked(self, action: str, description: str, timestamp: datetime) -> None:
        item = PendingAuditEvent(action=action, description=description, timestamp=timestamp)
        if action in _REPLACEABLE_ACTIONS:
            self._pending = [pending for pending in self._pending if pending.action != action]
        elif any(pending.action == action for pending in self._pending):
            return
        if len(self._pending) >= _PENDING_CAP:
            self._pending.pop(0)
        self._pending.append(item)

    def _flush_locked(self, skip_actions: Iterable[str] = ()) -> None:
        skip = frozenset(skip_actions)
        remaining: list[PendingAuditEvent] = []
        for item in self._pending:
            if item.action in skip:
                continue
            action_key = item.action if item.action in _MESSAGE else "DISCONNECTED"
            persisted = False
            try:
                persisted = bool(
                    persist_system_event(
                        message=_MESSAGE[action_key],
                        description=item.description,
                        classification=_CLASSIFICATION,
                        priority=_PRIORITY[action_key],
                        criticity=_CRITICITY[action_key],
                        timestamp=item.timestamp,
                    )
                )
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "Database audit flush persist skipped",
                    exc_info=True,
                )
            if not persisted:
                remaining.append(item)
        self._pending = remaining


database_connection_auditor = DatabaseConnectionAuditor()
