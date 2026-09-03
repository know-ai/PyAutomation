# -*- coding: utf-8 -*-
"""ACL invalidation bus: Redis intra-edge, pg_notify cross-edge.

Redis never stores grants — the payload is only a version timestamp.
Source of truth remains PostgreSQL; catalog.db is offline fallback.
"""
from __future__ import annotations

import json
import logging

from .store import reload_cache

_LOGGER = logging.getLogger("pyautomation.authz")

PG_CHANNEL = "pya_authz_invalidate"
REDIS_CHANNEL = "pya:authz:invalidate"


def _origin_node() -> str:
    try:
        from ..catalog.versions import edge_node_id

        return str(edge_node_id() or "local")
    except Exception:
        return "local"


def _now_ms() -> int:
    try:
        from ..catalog.versions import now_ms

        return int(now_ms())
    except Exception:
        import time

        return int(time.time() * 1000)


def parse_authz_payload(raw: str | bytes | None) -> tuple[int, str]:
    """Return (version, origin). Accepts JSON or a bare integer timestamp."""
    if raw is None:
        return 0, ""
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text.strip()
    if not text:
        return 0, ""
    try:
        data = json.loads(text)
    except Exception:
        if text.isdigit():
            return int(text), ""
        return 0, ""
    if isinstance(data, dict):
        version_raw = data.get("version") or 0
        try:
            version = int(version_raw)
        except (TypeError, ValueError):
            version = 0
        return version, str(data.get("origin") or "").strip()
    if isinstance(data, int):
        return int(data), ""
    return 0, ""


def apply_authz_invalidate(
    *,
    version: int = 0,
    origin: str = "",
    reason: str = "notify",
) -> int:
    """Reload RAM cache if ``version`` is newer than the local stamp.

    Origin is not skipped: sibling gunicorn workers on the publishing edge
    still need Redis; the same process no-ops via store version compare.
    """
    del origin  # documented for payload symmetry with user_cache
    incoming = int(version or 0)
    if incoming <= 0:
        incoming = _now_ms()
    return reload_cache(reason=reason, version=incoming)


def notify_authz_invalidated(version: int | None = None) -> int:
    """Publish invalidation after a successful grant write. Never raises."""
    stamp = int(version or 0) or _now_ms()
    payload = json.dumps(
        {"version": stamp, "origin": _origin_node()},
        separators=(",", ":"),
    )
    try:
        from automation import PyAutomation

        app = PyAutomation()
        db = app.db_manager.get_db() if app.is_db_connected() else None
        if db is not None:
            db.execute_sql("SELECT pg_notify(%s, %s)", (PG_CHANNEL, payload))
    except Exception:
        _LOGGER.debug("pg_notify authz invalidate skipped", exc_info=True)
    try:
        from ..utils.redis_client import get_redis

        client = get_redis()
        if client is not None:
            client.publish(REDIS_CHANNEL, payload)
    except Exception:
        _LOGGER.debug("redis publish authz invalidate skipped", exc_info=True)
    return stamp
