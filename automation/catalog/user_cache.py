# -*- coding: utf-8 -*-
"""Cross-edge user cache: Read-Through to historian, invalidate local SQLite.

The historian (PostgreSQL) is the source of truth while reachable. catalog.db is
disaster-recovery only. Writes on any edge notify peers via PG NOTIFY (and Redis
Pub/Sub when configured) so other edges drop/refresh their local users row
without waiting for CatalogReplicatorWorker (30 s).
"""
from __future__ import annotations

import json
import logging

_LOGGER = logging.getLogger("pyautomation.user_cache")
PG_CHANNEL = "pya_user_invalidate"
REDIS_CHANNEL = "pya:user:invalidate"
_CHANNEL = PG_CHANNEL
_REDIS_CHANNEL = REDIS_CHANNEL


def _origin_node() -> str:
    try:
        from .versions import edge_node_id

        return str(edge_node_id() or "local")
    except Exception:
        return "local"


def delete_local_user(username: str) -> bool:
    """Remove a users row from catalog.db. Returns True if a row was deleted."""
    username = (username or "").strip()
    if not username:
        return False
    try:
        from .local_provider import LocalCatalogProvider

        provider = LocalCatalogProvider()
        row = provider.find_one("users", field="username", value=username)
        if row is None:
            return False
        pk = row.get("_pk") or row.get("id")
        if pk is not None:
            provider.delete("users", str(pk))
            return True
        return provider.delete_where("users", "username", username) > 0
    except Exception:
        _LOGGER.debug("local user delete skipped username=%s", username, exc_info=True)
        return False


def drop_cvt_user(username: str) -> None:
    try:
        from ..modules.users.users import users

        users.drop_cached_user(username)
    except Exception:
        _LOGGER.debug("CVT user drop skipped username=%s", username, exc_info=True)


def cache_user_locally(user) -> None:
    """Write-through historian user into catalog.db + CVT (warm offline cache)."""
    if user is None:
        return
    username = getattr(user, "username", None)
    if not username:
        return
    try:
        from ..modules.users.users import users

        if not users.check_username(username):
            role_name = "guest"
            try:
                role = getattr(user, "role", None)
                role_name = getattr(role, "name", None) or "guest"
            except Exception:
                pass
            users.signup(
                username=username,
                role_name=role_name,
                email=getattr(user, "email", None),
                password=getattr(user, "password", None),
                name=getattr(user, "name", None),
                lastname=getattr(user, "lastname", None),
                identifier=getattr(user, "identifier", None),
                encode_password=False,
            )
        else:
            mem = users.get_by_username(username)
            if mem is not None and getattr(user, "password", None):
                mem.password = user.password
    except Exception:
        _LOGGER.debug("CVT user cache skipped username=%s", username, exc_info=True)
    try:
        from .bootstrap import write_catalog_row

        write_catalog_row(
            "users",
            {
                "username": getattr(user, "username", None),
                "email": getattr(user, "email", None),
                "password": getattr(user, "password", None),
                "identifier": getattr(user, "identifier", None),
                "name": getattr(user, "name", None),
                "lastname": getattr(user, "lastname", None),
            },
        )
    except Exception:
        _LOGGER.debug("local catalog user cache skipped username=%s", username, exc_info=True)


def refresh_user_from_remote(username: str) -> bool:
    """Pull one user from the historian into local cache. No-op if remote down."""
    username = (username or "").strip()
    if not username:
        return False
    try:
        from .. import PyAutomation
        from ..dbmodels.users import Users

        app = PyAutomation()
        if not app.is_db_connected():
            return False
        row = Users.get_or_none(username=username)
        if row is None:
            delete_local_user(username)
            drop_cvt_user(username)
            return True
        cache_user_locally(row)
        return True
    except Exception:
        _LOGGER.debug("remote user refresh skipped username=%s", username, exc_info=True)
        return False


def apply_user_invalidate(*, username: str, origin: str = "") -> None:
    """Peer handler: drop stale local row unless we originated the write.

    Cache-aside: delete the SQLite/CVT copy so the next login Read-Through
    hits PostgreSQL. Do not re-hydrate here — that would hide CA-USER-04.
    """
    username = (username or "").strip()
    if not username:
        return
    if origin and origin == _origin_node():
        return
    delete_local_user(username)
    drop_cvt_user(username)


def notify_user_invalidated(username: str) -> None:
    """Notify other edges after a successful historian user write. Never raises."""
    username = (username or "").strip()
    if not username:
        return
    payload = json.dumps({"username": username, "origin": _origin_node()}, separators=(",", ":"))
    try:
        from .. import PyAutomation

        app = PyAutomation()
        db = app.db_manager.get_db() if app.is_db_connected() else None
        if db is not None:
            db.execute_sql("SELECT pg_notify(%s, %s)", (_CHANNEL, payload))
    except Exception:
        _LOGGER.debug("pg_notify user invalidate skipped", exc_info=True)
    try:
        from ..utils.redis_client import get_redis

        client = get_redis()
        if client is not None:
            client.publish(_REDIS_CHANNEL, payload)
    except Exception:
        _LOGGER.debug("redis publish user invalidate skipped", exc_info=True)


def parse_invalidate_payload(raw: str | bytes | None) -> tuple[str, str]:
    if raw is None:
        return "", ""
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        data = json.loads(text)
    except Exception:
        return text.strip(), ""
    if isinstance(data, dict):
        return str(data.get("username") or "").strip(), str(data.get("origin") or "").strip()
    return "", ""
