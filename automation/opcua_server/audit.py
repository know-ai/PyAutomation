"""Audited failures for the embedded OPC UA server."""

from __future__ import annotations

import logging

_LOG = logging.getLogger("pyautomation")


def capability_fallback(capability: str, fallback: str, criticity: int = 2) -> None:
    """One audited fallback. criticity defaults to 2. Never raises."""
    message = f"OPC UA capability fallback: {capability}"
    description = f"fallback={fallback}"
    _LOG.warning("%s | %s", message, description)
    try:
        from ..utils.system_event_audit import persist_system_event

        persist_system_event(
            message=message,
            description=description,
            classification="System",
            priority=3,
            criticity=criticity,
        )
    except Exception:
        _LOG.debug("OPC UA capability fallback audit skipped", exc_info=True)


def audit_failure(message: str, description: str, criticity: int = 3) -> None:
    """WARNING plus persist_system_event. Never raises. Complexity: O(1) plus one write."""
    _LOG.warning("%s | %s", message, description)
    try:
        from ..utils.system_event_audit import persist_system_event

        persist_system_event(
            message=message,
            description=description,
            classification="System",
            priority=3,
            criticity=criticity,
        )
    except Exception:
        _LOG.debug("OPC UA audit event skipped", exc_info=True)
