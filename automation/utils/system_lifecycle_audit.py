# -*- coding: utf-8 -*-
"""Audit trail for process boot.

A restart (operator, orchestrator or power loss) cannot be distinguished after
the fact. Record a single short "System started" event per process. Do not
treat the first historian connect as a plant event — that is boot, not an
outage.
"""
from __future__ import annotations

import logging
import threading

from .system_event_audit import persist_system_event

_CLASSIFICATION = "System"
_MESSAGE = "System started"

_lock = threading.Lock()
_recorded = False


def reset_system_lifecycle_audit() -> None:
    """Test helper. Never call from production paths."""
    global _recorded
    with _lock:
        _recorded = False


def record_system_started() -> bool:
    """Persist one boot event for this process. Never raises."""
    global _recorded
    try:
        with _lock:
            if _recorded:
                return False
            _recorded = True
        return persist_system_event(
            message=_MESSAGE,
            description="boot",
            classification=_CLASSIFICATION,
            priority=2,
            criticity=2,
        )
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to record system started event",
            exc_info=True,
        )
        return False
