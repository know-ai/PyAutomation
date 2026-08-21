# -*- coding: utf-8 -*-
"""HMI session registry: PostgreSQL when available, in-memory fallback when not.

Fail-safe: never raises into Socket.IO handlers. Returns False/0/None on hard failure.
When the historian is down the edge still accepts sockets via ``_LOCAL_SESSIONS``.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..dbmodels.hmi_sessions import HMISession, utc_now

_LOGGER = logging.getLogger("pyautomation.hmi_sessions")

_LOCAL_LOCK = threading.Lock()
_LOCAL_SESSIONS: dict[str, dict] = {}


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


def _local_upsert(*, sid: str, username: str, origin: str) -> bool:
    node_id, area = node_identity()
    now = utc_now()
    with _LOCAL_LOCK:
        existing = _LOCAL_SESSIONS.get(sid)
        _LOCAL_SESSIONS[sid] = {
            "sid": sid,
            "node_id": node_id,
            "username": (username or "unknown")[:64],
            "origin": (origin or "")[:45],
            "area": area,
            "connected_at": existing["connected_at"] if existing else now,
            "last_heartbeat": now,
        }
    return True


def _local_remove(sid: str) -> Optional[StoredSession]:
    with _LOCAL_LOCK:
        row = _LOCAL_SESSIONS.pop(sid, None)
    if row is None:
        return None
    return StoredSession(
        sid=row["sid"],
        node_id=row["node_id"],
        username=row["username"],
        origin=row["origin"],
        area=row["area"],
    )


def _local_count(node_id: str) -> int:
    with _LOCAL_LOCK:
        return sum(1 for row in _LOCAL_SESSIONS.values() if row.get("node_id") == node_id)


def _local_touch(sid: str) -> bool:
    now = utc_now()
    with _LOCAL_LOCK:
        row = _LOCAL_SESSIONS.get(sid)
        if row is None:
            return False
        row["last_heartbeat"] = now
        return True


def _local_cleanup(stale_seconds: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(30, int(stale_seconds)))
    removed = 0
    with _LOCAL_LOCK:
        stale = [
            sid
            for sid, row in _LOCAL_SESSIONS.items()
            if (row.get("last_heartbeat") or cutoff) < cutoff
        ]
        for sid in stale:
            _LOCAL_SESSIONS.pop(sid, None)
            removed += 1
    return removed


def upsert_session(*, sid: str, username: str, origin: str) -> bool:
    """Insert or refresh a session. Uses in-memory store if historian is down."""
    sid = (sid or "")[:64]
    if not sid:
        return False
    if _get_db() is None:
        return _local_upsert(sid=sid, username=username, origin=origin)
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
        with _LOCAL_LOCK:
            _LOCAL_SESSIONS.pop(sid, None)
        return True
    except Exception:
        _LOGGER.debug("HMI session upsert failed; falling back to memory", exc_info=True)
        return _local_upsert(sid=sid, username=username, origin=origin)
    finally:
        _close_historian_socket()


def remove_session(sid: str) -> Optional[StoredSession]:
    """Delete session row; return snapshot if it existed. Never raises."""
    sid = (sid or "")[:64]
    if not sid:
        return None
    local = _local_remove(sid)
    if _get_db() is None:
        return local
    try:
        row = HMISession.get_or_none(HMISession.sid == sid)
        if row is None:
            return local
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
        return local
    finally:
        _close_historian_socket()


def count_sessions(node_id: str | None = None) -> int:
    """Active client count for this edge node. Never raises."""
    if node_id is None:
        node_id, _ = node_identity()
    if _get_db() is None:
        return _local_count(str(node_id))
    try:
        remote = (
            HMISession.select()
            .where(HMISession.node_id == node_id)
            .count()
        )
        return int(remote) + _local_count(str(node_id))
    except Exception:
        _LOGGER.debug("HMI session count failed", exc_info=True)
        return _local_count(str(node_id))
    finally:
        _close_historian_socket()


def touch_heartbeat(sid: str) -> bool:
    """Refresh last_heartbeat for an active session. Never raises."""
    sid = (sid or "")[:64]
    if not sid:
        return False
    if _get_db() is None:
        return _local_touch(sid)
    now = utc_now()
    try:
        updated = (
            HMISession.update(last_heartbeat=now)
            .where(HMISession.sid == sid)
            .execute()
        )
        if updated:
            return True
        return _local_touch(sid)
    except Exception:
        _LOGGER.debug("HMI session heartbeat failed", exc_info=True)
        return _local_touch(sid)
    finally:
        _close_historian_socket()


def cleanup_stale_sessions(stale_seconds: int = 120) -> int:
    """Remove orphan sessions (dead workers / lost disconnect). Never raises."""
    removed_local = _local_cleanup(stale_seconds)
    if _get_db() is None:
        return removed_local
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(30, int(stale_seconds)))
    try:
        removed_remote = (
            HMISession.delete()
            .where(HMISession.last_heartbeat < cutoff)
            .execute()
        )
        return int(removed_remote or 0) + removed_local
    except Exception:
        _LOGGER.debug("HMI session cleanup failed", exc_info=True)
        return removed_local
    finally:
        _close_historian_socket()
