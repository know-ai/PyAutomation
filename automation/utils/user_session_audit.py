# -*- coding: utf-8 -*-
"""Audit trail for user session and identity actions.

Login, logout and account-administration changes must appear in the Events
log. Never persist passwords, tokens or raw request bodies. Never raise into
the authentication path if the event store is down.
"""
from __future__ import annotations

import logging

from .system_event_audit import clip, get_system_user, persist_system_event

_CLASSIFICATION = "User"

_PRIORITY = {
    "LOGIN": 2,
    "LOGIN_FAILED": 3,
    "LOGOUT": 2,
    "SIGNUP": 2,
    "PASSWORD_CHANGED": 3,
    "PASSWORD_RESET": 4,
    "ROLE_UPDATED": 4,
}

_CRITICITY = {
    "LOGIN": 2,
    "LOGIN_FAILED": 4,
    "LOGOUT": 2,
    "SIGNUP": 2,
    "PASSWORD_CHANGED": 4,
    "PASSWORD_RESET": 5,
    "ROLE_UPDATED": 5,
}

_MESSAGE = {
    "LOGIN": "User logged in",
    "LOGIN_FAILED": "User login failed",
    "LOGOUT": "User logged out",
    "SIGNUP": "User account created",
    "PASSWORD_CHANGED": "User password changed",
    "PASSWORD_RESET": "User password reset",
    "ROLE_UPDATED": "User role updated",
}


def record_user_session_event(
    action: str,
    user=None,
    username: str = "",
    actor=None,
    extra: str = "",
) -> bool:
    """Persist a structured user-session / identity event.

    Returns True if the event was stored. Never raises.
    """
    try:
        action_key = str(action or "").upper()
        if action_key not in _MESSAGE:
            logging.getLogger("pyautomation").warning(
                "User session audit skipped: unknown action %s", action
            )
            return False

        claimed = clip(username, 64)
        actor_name = clip(getattr(actor, "username", "") or "", 64)
        subject_name = clip(getattr(user, "username", "") or claimed, 64)

        parts = []
        if subject_name:
            parts.append(f"username={subject_name}")
        if actor_name and actor_name != subject_name:
            parts.append(f"actor={actor_name}")
        extra_clip = clip(extra, 120)
        if extra_clip:
            parts.append(extra_clip)
        description = " ".join(parts) if parts else action_key.lower()

        audit_user = user or actor or get_system_user()
        if audit_user is None:
            logging.getLogger("pyautomation").warning(
                "User session audit event skipped: no audit user available"
            )
            return False

        return persist_system_event(
            message=_MESSAGE[action_key],
            description=description,
            classification=_CLASSIFICATION,
            priority=_PRIORITY[action_key],
            criticity=_CRITICITY[action_key],
            user=audit_user,
        )
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to record user session audit event",
            exc_info=True,
        )
        return False
