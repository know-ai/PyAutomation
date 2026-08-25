# -*- coding: utf-8 -*-
"""HMI session registry: local Redis sidecar, then in-process RAM.

Hot path (connect / disconnect / ping) never touches PostgreSQL. Redis is the
loopback sidecar for this edge; ``_fallback_cache`` is the last-resort mirror
when the sidecar is unset or down. PG ``hmi_sessions`` is a background snapshot
only (HmiSessionSyncWorker).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..dbmodels.hmi_sessions import HMISession, utc_now

_LOGGER = logging.getLogger("pyautomation.hmi_sessions")

_REDIS_SESS_PREFIX = "hmi:sess:"
_REDIS_NODE_PREFIX = "hmi:sessions:"
_DEFAULT_TTL_S = 60


def session_ttl_s() -> int:
    try:
        return max(15, int(os.environ.get("AUTOMATION_REDIS_SESSION_TTL") or _DEFAULT_TTL_S))
    except (TypeError, ValueError):
        return _DEFAULT_TTL_S


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


class HmiSessionStore:
    """Redis sidecar + RAM fallback. Never raises into Socket.IO handlers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._fallback_cache: dict[str, set[str]] = {}
        self._fallback_meta: dict[str, dict] = {}

    def reset_for_tests(self) -> None:
        with self._lock:
            self._fallback_cache.clear()
            self._fallback_meta.clear()

    def upsert(self, *, sid: str, username: str, origin: str) -> bool:
        """Hot path. Redis then RAM. Never PostgreSQL. Never raises."""
        sid = (sid or "")[:64]
        if not sid:
            return False
        node_id, area = node_identity()
        record = self._record(
            sid=sid, node_id=node_id, username=username, origin=origin, area=area
        )
        self._redis_upsert(record)
        self._ram_upsert(record)
        return True

    def remove(self, sid: str) -> Optional[StoredSession]:
        """Hot path. Redis then RAM. Never PostgreSQL. Never raises."""
        sid = (sid or "")[:64]
        if not sid:
            return None
        redis_snap = self._redis_remove(sid)
        ram_snap = self._ram_remove(sid)
        return redis_snap or ram_snap

    def count(self, node_id: str | None = None) -> int:
        if node_id is None:
            node_id, _ = node_identity()
        remote = self._redis_count(str(node_id))
        if remote is not None:
            return int(remote)
        with self._lock:
            return len(self._fallback_cache.get(str(node_id)) or ())

    def touch(self, sid: str) -> bool:
        sid = (sid or "")[:64]
        if not sid:
            return False
        redis_ok = self._redis_touch(sid)
        ram_ok = self._ram_touch(sid)
        return bool(redis_ok or ram_ok)

    def get_active_sids(self, node_id: str | None = None) -> set[str]:
        if node_id is None:
            node_id, _ = node_identity()
        node_id = str(node_id)
        client = self._redis()
        if client is not None:
            try:
                return set(client.smembers(_REDIS_NODE_PREFIX + node_id) or ())
            except Exception:
                _LOGGER.debug("Redis HMI smembers failed", exc_info=True)
        with self._lock:
            return set(self._fallback_cache.get(node_id) or ())

    def session_records(self, node_id: str | None = None) -> list[dict]:
        sids = self.get_active_sids(node_id)
        if node_id is None:
            node_id, _ = node_identity()
        records = []
        for sid in sids:
            rec = self._lookup(sid, default_node=str(node_id))
            if rec is not None:
                records.append(rec)
        return records

    def cleanup_stale(self, stale_seconds: int = 120) -> int:
        node_id, _ = node_identity()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(30, int(stale_seconds)))
        removed = 0
        with self._lock:
            stale = [
                sid
                for sid, row in self._fallback_meta.items()
                if (row.get("last_heartbeat") or cutoff) < cutoff
            ]
            for sid in stale:
                meta = self._fallback_meta.pop(sid, None)
                if meta:
                    bucket = self._fallback_cache.get(meta.get("node_id") or node_id)
                    if bucket is not None:
                        bucket.discard(sid)
                    removed += 1
        removed += self._redis_prune_node(node_id)
        return removed

    def _record(self, *, sid: str, node_id: str, username: str, origin: str, area: str) -> dict:
        now = utc_now()
        with self._lock:
            existing = self._fallback_meta.get(sid)
            connected_at = existing["connected_at"] if existing else now
        return {
            "sid": sid,
            "node_id": node_id,
            "username": (username or "unknown")[:64],
            "origin": (origin or "")[:45],
            "area": area,
            "connected_at": connected_at,
            "last_heartbeat": now,
        }

    def _lookup(self, sid: str, *, default_node: str) -> dict | None:
        client = self._redis()
        if client is not None:
            try:
                raw = client.get(_REDIS_SESS_PREFIX + sid)
                if raw:
                    data = json.loads(raw)
                    data["sid"] = sid
                    data.setdefault("node_id", default_node)
                    return data
            except Exception:
                _LOGGER.debug("Redis HMI session get failed", exc_info=True)
        with self._lock:
            meta = self._fallback_meta.get(sid)
            if meta is None:
                if sid in (self._fallback_cache.get(default_node) or ()):
                    return {
                        "sid": sid,
                        "node_id": default_node,
                        "username": "unknown",
                        "origin": "",
                        "area": "local",
                    }
                return None
            return dict(meta)

    def _ram_upsert(self, record: dict) -> None:
        sid = record["sid"]
        node_id = record["node_id"]
        with self._lock:
            self._fallback_cache.setdefault(node_id, set()).add(sid)
            self._fallback_meta[sid] = dict(record)

    def _ram_remove(self, sid: str) -> Optional[StoredSession]:
        with self._lock:
            meta = self._fallback_meta.pop(sid, None)
            node_id = (meta or {}).get("node_id") or node_identity()[0]
            bucket = self._fallback_cache.get(node_id)
            if bucket is not None:
                bucket.discard(sid)
        if meta is None:
            return None
        return StoredSession(
            sid=str(meta.get("sid") or sid),
            node_id=str(meta.get("node_id") or node_id),
            username=str(meta.get("username") or "unknown"),
            origin=str(meta.get("origin") or ""),
            area=str(meta.get("area") or "local"),
        )

    def _ram_touch(self, sid: str) -> bool:
        now = utc_now()
        with self._lock:
            row = self._fallback_meta.get(sid)
            if row is None:
                return False
            row["last_heartbeat"] = now
            return True

    def _redis(self):
        from .redis_client import get_redis

        return get_redis()

    def _redis_upsert(self, record: dict) -> bool:
        client = self._redis()
        if client is None:
            return False
        sid = record["sid"]
        node_id = record["node_id"]
        ttl = session_ttl_s()
        payload = dict(record)
        for key in ("connected_at", "last_heartbeat"):
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        try:
            pipe = client.pipeline(transaction=True)
            pipe.setex(_REDIS_SESS_PREFIX + sid, ttl, json.dumps(payload))
            pipe.sadd(_REDIS_NODE_PREFIX + node_id, sid)
            pipe.expire(_REDIS_NODE_PREFIX + node_id, ttl)
            pipe.execute()
            return True
        except Exception:
            _LOGGER.debug("Redis HMI session upsert failed; using RAM fallback", exc_info=True)
            return False

    def _redis_remove(self, sid: str) -> Optional[StoredSession]:
        client = self._redis()
        if client is None:
            return None
        try:
            raw = client.get(_REDIS_SESS_PREFIX + sid)
            record = json.loads(raw) if raw else {}
            node_id = record.get("node_id") or node_identity()[0]
            pipe = client.pipeline(transaction=True)
            pipe.delete(_REDIS_SESS_PREFIX + sid)
            pipe.srem(_REDIS_NODE_PREFIX + node_id, sid)
            pipe.execute()
            if not record:
                return None
            return StoredSession(
                sid=str(record.get("sid") or sid),
                node_id=str(record.get("node_id") or node_id),
                username=str(record.get("username") or "unknown"),
                origin=str(record.get("origin") or ""),
                area=str(record.get("area") or "local"),
            )
        except Exception:
            _LOGGER.debug("Redis HMI session remove failed; using RAM fallback", exc_info=True)
            return None

    def _redis_count(self, node_id: str) -> int | None:
        client = self._redis()
        if client is None:
            return None
        try:
            return int(client.scard(_REDIS_NODE_PREFIX + node_id) or 0)
        except Exception:
            _LOGGER.debug("Redis HMI session count failed", exc_info=True)
            return None

    def _redis_touch(self, sid: str) -> bool:
        client = self._redis()
        if client is None:
            return False
        ttl = session_ttl_s()
        try:
            raw = client.get(_REDIS_SESS_PREFIX + sid)
            ok = bool(client.expire(_REDIS_SESS_PREFIX + sid, ttl))
            if raw:
                try:
                    node_id = json.loads(raw).get("node_id") or node_identity()[0]
                    client.expire(_REDIS_NODE_PREFIX + node_id, ttl)
                except Exception:
                    pass
            return ok
        except Exception:
            _LOGGER.debug("Redis HMI session heartbeat failed", exc_info=True)
            return False

    def _redis_prune_node(self, node_id: str) -> int:
        client = self._redis()
        if client is None:
            return 0
        removed = 0
        try:
            sids = client.smembers(_REDIS_NODE_PREFIX + node_id) or set()
            for sid in list(sids):
                if not client.exists(_REDIS_SESS_PREFIX + sid):
                    client.srem(_REDIS_NODE_PREFIX + node_id, sid)
                    removed += 1
        except Exception:
            _LOGGER.debug("Redis HMI session prune failed", exc_info=True)
        return removed


_STORE = HmiSessionStore()
# Spec ARC-03: auditors look for this name on the store.
_fallback_cache = _STORE._fallback_cache


def reset_hmi_sessions_for_tests() -> None:
    _STORE.reset_for_tests()


def upsert_session(*, sid: str, username: str, origin: str) -> bool:
    """Insert or refresh a session. Redis or memory only — never PostgreSQL."""
    return _STORE.upsert(sid=sid, username=username, origin=origin)


def remove_session(sid: str) -> Optional[StoredSession]:
    """Delete session; return snapshot if it existed. Never raises. Never hits PG."""
    return _STORE.remove(sid)


def count_sessions(node_id: str | None = None) -> int:
    """Active client count for this edge node. Redis/memory — never PostgreSQL."""
    return _STORE.count(node_id)


def touch_heartbeat(sid: str) -> bool:
    """Refresh TTL / last_heartbeat. Never raises. Never hits PG."""
    return _STORE.touch(sid)


def get_active_sids(node_id: str | None = None) -> set[str]:
    return _STORE.get_active_sids(node_id)


def cleanup_stale_sessions(stale_seconds: int = 120) -> int:
    """Prune memory + Redis sets. PG stale rows are handled by sync_sessions_to_pg."""
    return _STORE.cleanup_stale(stale_seconds)


def sync_sessions_to_pg(node_id: str | None = None) -> int:
    """Background batch snapshot of this edge's live sids into PostgreSQL."""
    if node_id is None:
        node_id, _ = node_identity()
    node_id = str(node_id)
    records = _STORE.session_records(node_id)
    db = _get_db()
    if db is None:
        return 0
    try:
        from .db_connections import ephemeral_historian

        with ephemeral_historian(db):
            return int(HMISession.upsert_batch(node_id=node_id, sessions=records) or 0)
    except Exception:
        _LOGGER.debug("HMI session PG snapshot skipped", exc_info=True)
        return 0
    finally:
        _close_historian_socket()


def flush_pg_snapshot(budget: int = 64) -> int:
    """Backward-compatible alias for the background snapshot worker."""
    return sync_sessions_to_pg()
