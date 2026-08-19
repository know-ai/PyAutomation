# -*- coding: utf-8 -*-
"""Audit trail for HMI Socket.IO client lifecycle.

Connect, disconnect, reconnect and rejected connections are persisted in Events.
Session rows live in PostgreSQL (``hmi_sessions``) for global multi-worker counts.
Fail-safe: never raises into the Socket.IO path.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from .hmi_session_store import count_sessions, remove_session, upsert_session
from .system_event_audit import clip, get_system_user, persist_system_event

_CLASSIFICATION = "HMI"

_PRIORITY = {
    "CONNECTED": 2,
    "DISCONNECTED": 3,
    "RECONNECTED": 2,
    "CONNECTION_REJECTED": 3,
}

_CRITICITY = {
    "CONNECTED": 2,
    "DISCONNECTED": 3,
    "RECONNECTED": 2,
    "CONNECTION_REJECTED": 4,
}

_MESSAGE = {
    "CONNECTED": "HMI client connected",
    "DISCONNECTED": "HMI client disconnected",
    "RECONNECTED": "HMI client reconnected",
    "CONNECTION_REJECTED": "HMI client connection rejected",
}


def socket_request_origin() -> str:
    """Client IP in a Socket.IO handler. Never raises."""
    try:
        from flask import request

        forwarded = request.headers.get("X-Forwarded-For") or ""
        if forwarded:
            return clip(forwarded.split(",")[0].strip(), 64)
        remote = request.environ.get("REMOTE_ADDR") or getattr(request, "remote_addr", None) or ""
        return clip(remote, 64)
    except Exception:
        return ""


def _edge_label() -> str:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        if not getattr(scope, "enabled", False):
            return ""
        site = clip(getattr(scope, "site", None) or "", 32)
        area = clip(getattr(scope, "area", None) or "", 32)
        node_id = clip(getattr(scope, "node_id", None) or "", 32)
        if site and area:
            edge = f"{site}.{area}"
        elif area:
            edge = area
        elif site:
            edge = site
        else:
            edge = ""
        if node_id:
            return clip(f"{edge} ({node_id})" if edge else node_id, 64)
        return edge
    except Exception:
        return ""


def resolve_connect_user(auth: Any) -> Tuple[Optional[object], str, str]:
    """Strict connect auth. Returns (user, username, reject_reason). Never logs token."""
    auth = auth if isinstance(auth, dict) else {}
    token = clip(auth.get("token") or "", 512)
    if not token:
        return None, "anonymous", "missing_token"

    try:
        from ..extensions.api import Api
        from ..modules.users.users import Users

        users = Users()
        user, err, _status = Api._resolve_session_user(token)
        if user is not None:
            return user, clip(getattr(user, "username", None) or "unknown", 64), ""
        if err:
            code = str(err.get("code") or "")
            if code == "SESSION_SUPERSEDED":
                return None, "revoked-session", "session_superseded"
            if code == "AUTH_BACKEND_UNAVAILABLE":
                return None, "unknown", "auth_backend_unavailable"
            if code == "SESSION_INVALID":
                return None, "unknown", "invalid_token"
        if users.is_revoked_token(token):
            return None, "revoked-session", "session_superseded"
    except Exception:
        logging.getLogger("pyautomation").debug(
            "HMI socket connect auth resolution skipped",
            exc_info=True,
        )
    return None, "unknown", "invalid_token"


def _is_reconnect_auth(auth: Any) -> bool:
    auth = auth if isinstance(auth, dict) else {}
    value = auth.get("reconnect")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def record_hmi_socket_event(
    action: str,
    *,
    username: str = "",
    origin: str = "",
    sid: str = "",
    edge: str = "",
    reason: str = "",
    active_clients: int = 0,
    user=None,
) -> bool:
    """Persist a structured HMI Socket.IO lifecycle event. Never raises."""
    try:
        action_key = str(action or "").upper()
        if action_key not in _MESSAGE:
            logging.getLogger("pyautomation").warning(
                "HMI socket audit skipped: unknown action %s", action
            )
            return False

        audit_user = user or get_system_user()
        if audit_user is None:
            logging.getLogger("pyautomation").warning(
                "HMI socket audit event skipped: system user is not available"
            )
            return False

        parts = []
        subject = clip(username or "anonymous", 64)
        if subject:
            parts.append(f"username={subject}")
        origin_clip = clip(origin, 64)
        if origin_clip:
            parts.append(f"origin={origin_clip}")
        sid_clip = clip(sid, 32)
        if sid_clip:
            parts.append(f"sid={sid_clip}")
        edge_clip = clip(edge, 64)
        if edge_clip:
            parts.append(f"edge={edge_clip}")
        parts.append(f"active_clients={max(0, int(active_clients))}")
        reason_clip = clip(reason, 80)
        if reason_clip:
            parts.append(f"reason={reason_clip}")

        description = clip("; ".join(parts) if parts else action_key.lower(), 256)

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
            "Failed to persist HMI socket audit event",
            exc_info=True,
        )
        return False


def attempt_hmi_socket_connect(*, auth=None, sid: str = "") -> bool:
    """Validate token, upsert PG session, emit connect/reconnect event.

    Returns True when the Socket.IO connection should be accepted. Never raises.
    """
    try:
        sid = clip(sid or "", 64)
        if not sid:
            return False

        origin = socket_request_origin()
        edge = _edge_label()
        user, username, reject_reason = resolve_connect_user(auth)

        if user is None:
            record_hmi_socket_event(
                "CONNECTION_REJECTED",
                username=username,
                origin=origin,
                sid=sid,
                edge=edge,
                reason=reject_reason or "invalid_token",
                active_clients=count_sessions(),
            )
            return False

        if not upsert_session(sid=sid, username=username, origin=origin):
            record_hmi_socket_event(
                "CONNECTION_REJECTED",
                username=username,
                origin=origin,
                sid=sid,
                edge=edge,
                reason="session_store_unavailable",
                active_clients=0,
                user=user,
            )
            return False

        action = "RECONNECTED" if _is_reconnect_auth(auth) else "CONNECTED"
        active = count_sessions()
        record_hmi_socket_event(
            action,
            username=username,
            origin=origin,
            sid=sid,
            edge=edge,
            active_clients=active,
            user=user,
        )
        return True
    except Exception:
        logging.getLogger("pyautomation").error(
            "HMI socket connect attempt failed",
            exc_info=True,
        )
        return False


def register_hmi_socket_disconnect(*, sid: str = "", reason: str = "") -> None:
    """Remove PG session and persist disconnect event. Never raises."""
    try:
        sid = clip(sid or "", 64)
        if not sid:
            return

        session = remove_session(sid)
        if session is None:
            return

        edge = session.area
        if session.node_id:
            edge = clip(f"{session.area} ({session.node_id})", 64)

        record_hmi_socket_event(
            "DISCONNECTED",
            username=session.username,
            origin=session.origin,
            sid=session.sid,
            edge=edge,
            reason=reason,
            active_clients=count_sessions(session.node_id),
        )
    except Exception:
        logging.getLogger("pyautomation").error(
            "HMI socket disconnect audit failed",
            exc_info=True,
        )


def register_hmi_socket_heartbeat(*, sid: str = "") -> None:
    """Refresh session heartbeat in PostgreSQL. Never raises."""
    from .hmi_session_store import touch_heartbeat

    touch_heartbeat(sid)


def reset_registry_for_tests() -> None:
    """Backward-compatible test helper (PG rows cleared in integration tests)."""
    try:
        from ..dbmodels.hmi_sessions import HMISession

        if _get_db_for_tests() is not None:
            HMISession.delete().execute()
    except Exception:
        pass


def _get_db_for_tests():
    try:
        from .. import PyAutomation

        return PyAutomation().db_manager.get_db()
    except Exception:
        return None
