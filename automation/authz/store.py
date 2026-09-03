# -*- coding: utf-8 -*-
"""In-memory ACL cache. Reloaded at boot, after grant writes, and on invalidate.

Hot path is O(1) dict lookup. PostgreSQL/SQLite are never queried in authorize().
Redis is not a grant store — see invalidate.py for the invalidation bus.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Iterable

_LOGGER = logging.getLogger("pyautomation.authz")

_lock = threading.RLock()
# (subject_type, subject_id, resource_key, action) -> effect
_grants: dict[tuple[str, str, str, str], str] = {}
_version: int = 0
_last_reload_mono: float = 0.0
PERIODIC_RELOAD_S = 300.0


def _norm(value: str | None) -> str:
    return str(value or "").strip()


def _key(subject_type: str, subject_id: str, resource_key: str, action: str) -> tuple[str, str, str, str]:
    return (
        _norm(subject_type).lower(),
        _norm(subject_id).lower(),
        _norm(resource_key),
        _norm(action).lower(),
    )


def cache_version() -> int:
    with _lock:
        return _version


def grant_count() -> int:
    with _lock:
        return len(_grants)


def clear() -> None:
    global _version, _last_reload_mono
    with _lock:
        _grants.clear()
        _version = 0
        _last_reload_mono = 0.0


def lookup(subject_type: str, subject_id: str | None, resource_key: str, action: str) -> str | None:
    if not subject_id:
        return None
    with _lock:
        return _grants.get(_key(subject_type, subject_id, resource_key, action))


def put_grant(
    subject_type: str,
    subject_id: str,
    resource_key: str,
    action: str,
    effect: str,
) -> None:
    effect_norm = _norm(effect).lower()
    cache_key = _key(subject_type, subject_id, resource_key, action)
    with _lock:
        if effect_norm in {"allow", "deny"}:
            _grants[cache_key] = effect_norm
        else:
            _grants.pop(cache_key, None)


def delete_grant(subject_type: str, subject_id: str, resource_key: str, action: str) -> None:
    with _lock:
        _grants.pop(_key(subject_type, subject_id, resource_key, action), None)


def snapshot() -> dict[tuple[str, str, str, str], str]:
    with _lock:
        return dict(_grants)


def load_from_rows(rows: Iterable[dict]) -> int:
    count = 0
    with _lock:
        _grants.clear()
        for row in rows:
            effect = _norm(row.get("effect")).lower()
            if effect not in {"allow", "deny"}:
                continue
            _grants[
                _key(
                    row.get("subject_type"),
                    row.get("subject_id"),
                    row.get("resource_key"),
                    row.get("action"),
                )
            ] = effect
            count += 1
    return count


def _rows_from_historian() -> list[dict] | None:
    try:
        from automation import PyAutomation

        if not bool(PyAutomation().is_db_connected()):
            return None
    except Exception:
        return None
    try:
        from ..dbmodels.authz import AuthzGrant

        return [row.serialize() for row in AuthzGrant.select().iterator()]
    except Exception:
        _LOGGER.debug("authz historian read skipped", exc_info=True)
        return None


def _rows_from_local() -> list[dict]:
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        return list(LocalCatalogProvider().read_all("authz_grants"))
    except Exception:
        _LOGGER.debug("authz local catalog read skipped", exc_info=True)
        return []


def _now_ms() -> int:
    return int(time.time() * 1000)


def reload_cache(*, reason: str = "manual", version: int | None = None) -> int:
    """Load grants from historian if reachable, else the local catalog mirror.

    Duplicate notifications with ``version <= cache_version`` are no-ops (stampede).
    Concurrent callers serialize on ``_lock`` so only one SELECT runs at a time.
    Empty cache remains fail-closed: evaluate() denies until rows exist.
    """
    global _version, _last_reload_mono
    incoming = int(version or 0)
    with _lock:
        if incoming and incoming <= _version:
            return len(_grants)
        rows = _rows_from_historian()
        source = "historian"
        if rows is None:
            rows = _rows_from_local()
            source = "catalog.db"
        n = 0
        _grants.clear()
        for row in rows or []:
            effect = _norm(row.get("effect")).lower()
            if effect not in {"allow", "deny"}:
                continue
            _grants[
                _key(
                    row.get("subject_type"),
                    row.get("subject_id"),
                    row.get("resource_key"),
                    row.get("action"),
                )
            ] = effect
            n += 1
        stamp = incoming or _now_ms()
        if stamp < _version:
            stamp = _version
        _version = stamp
        _last_reload_mono = time.monotonic()
        _LOGGER.info(
            "authz cache loaded grants=%s version=%s reason=%s source=%s",
            n,
            _version,
            reason,
            source,
        )
        return n


def maybe_periodic_reload(interval_s: float = PERIODIC_RELOAD_S) -> int:
    """Heartbeat: reload from source of truth if the interval elapsed (missed notify)."""
    interval = max(0.0, float(interval_s))
    with _lock:
        if _last_reload_mono and (time.monotonic() - _last_reload_mono) < interval:
            return 0
    return reload_cache(reason="periodic")
