# -*- coding: utf-8 -*-
"""PostgreSQL-backed HMI session registry (multi-worker global client count).

Fail-safe: never raises into Socket.IO handlers. Returns False/0/None on outage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..dbmodels.hmi_sessions import HMISession, utc_now

_LOGGER = logging.getLogger("pyautomation.hmi_sessions")


@dataclass
class StoredSession:
    sid: str
    node_id: str
    username: str
    origin: str
    area: str


def _close_historian_socket() -> None:
    try:
        from .db_connections import close_current_greenlet_connection, keep_historian_socket
        from .. import PyAutomation

        if not keep_historian_socket():
            close_current_greenlet_connection(getattr(PyAutomation(), "_db", None))
    except Exception:
        pass


def _get_db():
    try:
        from .. import PyAutomation
        from .db_connections import ensure_bound_connection

        app = PyAutomation()
        if not app.is_db_connected():
            return None
        db = app.db_manager.get_db()
        if db is None:
            return None
        try:
            ensure_bound_connection(db)
        except Exception:
            _LOGGER.debug("HMI session store DB unavailable", exc_info=True)
            return None
        return db
    except Exception:
        return None


def node_identity() -> tuple[str, str]:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
        node_id = (scope.node_id if scope.is_valid else None) or "local"
        area = (scope.area if scope.enabled and scope.area else None) or "local"
        return str(node_id)[:64], str(area)[:64]
    except Exception:
        return "local", "local"


def upsert_session(*, sid: str, username: str, origin: str) -> bool:
    """Insert or refresh a session row. Never raises."""
    sid = (sid or "")[:64]
    if not sid:
        return False
    if _get_db() is None:
        return False
    node_id, area = node_identity()
    now = utc_now()
    try:
        HMISession.insert(
            sid=sid,
            node_id=node_id,
            username=(username or "unknown")[:64],
            origin=(origin or "")[:45],
            area=area,
            connected_at=now,
            last_heartbeat=now,
        ).on_conflict(
            conflict_target=[HMISession.sid],
            update={
                HMISession.node_id: node_id,
                HMISession.username: (username or "unknown")[:64],
                HMISession.origin: (origin or "")[:45],
                HMISession.area: area,
                HMISession.last_heartbeat: now,
            },
        ).execute()
        return True
    except Exception:
        _LOGGER.debug("HMI session upsert failed", exc_info=True)
        return False
    finally:
        _close_historian_socket()


def remove_session(sid: str) -> Optional[StoredSession]:
    """Delete session row; return snapshot if it existed. Never raises."""
    sid = (sid or "")[:64]
    if not sid or _get_db() is None:
        return None
    try:
        row = HMISession.get_or_none(HMISession.sid == sid)
        if row is None:
            return None
        snapshot = StoredSession(
            sid=row.sid,
            node_id=row.node_id,
            username=row.username,
            origin=row.origin,
            area=row.area,
        )
        HMISession.delete().where(HMISession.sid == sid).execute()
        return snapshot
    except Exception:
        _LOGGER.debug("HMI session remove failed", exc_info=True)
        return None
    finally:
        _close_historian_socket()


def count_sessions(node_id: str | None = None) -> int:
    """Global active client count for this edge node. Never raises."""
    if _get_db() is None:
        return 0
    if node_id is None:
        node_id, _ = node_identity()
    try:
        return (
            HMISession.select()
            .where(HMISession.node_id == node_id)
            .count()
        )
    except Exception:
        _LOGGER.debug("HMI session count failed", exc_info=True)
        return 0
    finally:
        _close_historian_socket()


def touch_heartbeat(sid: str) -> bool:
    """Refresh last_heartbeat for an active session. Never raises."""
    sid = (sid or "")[:64]
    if not sid or _get_db() is None:
        return False
    now = utc_now()
    try:
        updated = (
            HMISession.update(last_heartbeat=now)
            .where(HMISession.sid == sid)
            .execute()
        )
        return bool(updated)
    except Exception:
        _LOGGER.debug("HMI session heartbeat failed", exc_info=True)
        return False
    finally:
        _close_historian_socket()


def cleanup_stale_sessions(stale_seconds: int = 120) -> int:
    """Remove orphan sessions (dead workers / lost disconnect). Never raises."""
    if _get_db() is None:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(30, int(stale_seconds)))
    try:
        return (
            HMISession.delete()
            .where(HMISession.last_heartbeat < cutoff)
            .execute()
        )
    except Exception:
        _LOGGER.debug("HMI session cleanup failed", exc_info=True)
        return 0
    finally:
        _close_historian_socket()
