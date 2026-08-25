# -*- coding: utf-8 -*-
"""Hot operational controls for /performance (observability + action).

HTTP handlers stay thin: validation, roles, and Events live here. Workers are
restarted cooperatively (stop_event) so the acquisition hub is not blocked.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from .system_event_audit import clip, persist_system_event

_LOGGER = logging.getLogger("pyautomation")
_RESTART_LOCK = threading.Lock()
_RESTARTING: dict[str, bool] = {
    "LoggerWorker": False,
    "CatalogReplicator": False,
    "MetricsSampler": False,
}

WORKER_ALIASES = {
    "loggerworker": "LoggerWorker",
    "logger": "LoggerWorker",
    "catalogreplicator": "CatalogReplicator",
    "catalogreplicatorworker": "CatalogReplicator",
    "catalog": "CatalogReplicator",
    "metricssampler": "MetricsSampler",
    "metricssamplerworker": "MetricsSampler",
    "metrics": "MetricsSampler",
}

CONTROL_ROLES = frozenset({"admin", "supervisor", "sudo"})
DESTRUCTIVE_ROLES = frozenset({"admin", "sudo"})
AGE_CHOICES = (5, 10, 30, 60)


class OpsControlError(ValueError):
    """Operator input that should map to HTTP 400."""


def normalize_worker_name(name: str | None) -> str:
    key = "".join(ch for ch in str(name or "") if ch.isalnum()).lower()
    resolved = WORKER_ALIASES.get(key)
    if not resolved:
        raise OpsControlError(
            "Unknown worker. Use LoggerWorker, CatalogReplicator or MetricsSampler."
        )
    return resolved


def _username(user) -> str:
    return str(getattr(user, "username", None) or getattr(user, "name", None) or "unknown")


def _role_name(user) -> str:
    role = getattr(user, "role", None)
    return str(getattr(role, "name", None) or "").strip().lower()


def require_control_role(user) -> None:
    if _role_name(user) not in CONTROL_ROLES:
        raise PermissionError("admin or supervisor role required")


def require_destructive_role(user) -> None:
    if _role_name(user) not in DESTRUCTIVE_ROLES:
        raise PermissionError("admin role required")


def _audit(message: str, description: str, *, user=None, criticity: int = 3) -> None:
    persist_system_event(
        message=clip(message, 256),
        description=clip(description, 256),
        classification="System",
        priority=min(5, max(1, int(criticity))),
        criticity=int(criticity),
        user=user,
    )


def _iso(value) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _state(thread, key: str) -> str:
    if _RESTARTING.get(key):
        return "restarting"
    if thread is None:
        return "inactive"
    alive = bool(getattr(thread, "is_alive", lambda: False)())
    return "alive" if alive else "error"


def worker_snapshot() -> dict[str, dict[str, Any]]:
    from .. import PyAutomation
    from ..catalog.replicator import get_catalog_replicator

    app = PyAutomation()
    logger = getattr(app, "db_worker", None)
    catalog = get_catalog_replicator()
    metrics = getattr(app, "metrics_worker", None)
    catalog_last = None
    if catalog is not None:
        last = getattr(catalog, "_last_sync", None)
        catalog_last = _iso(last)
    return {
        "LoggerWorker": {
            "name": "LoggerWorker",
            "state": _state(logger, "LoggerWorker"),
            "last_cycle_utc": getattr(logger, "last_cycle_utc", None),
        },
        "CatalogReplicator": {
            "name": "CatalogReplicator",
            "state": _state(catalog, "CatalogReplicator"),
            "last_cycle_utc": catalog_last,
        },
        "MetricsSampler": {
            "name": "MetricsSampler",
            "state": _state(metrics, "MetricsSampler"),
            "last_cycle_utc": getattr(metrics, "last_cycle_utc", None),
        },
    }


def _refresh_metrics() -> None:
    try:
        from .. import PyAutomation

        worker = getattr(PyAutomation(), "metrics_worker", None)
        request = getattr(worker, "request_sample", None)
        if callable(request):
            request()
    except Exception:
        _LOGGER.debug("ops metrics refresh skipped", exc_info=True)


def restart_worker(name: str, *, user=None, reason: str | None = None) -> dict[str, Any]:
    resolved = normalize_worker_name(name)
    with _RESTART_LOCK:
        if _RESTARTING.get(resolved):
            raise OpsControlError(f"{resolved} is already restarting")
        _RESTARTING[resolved] = True
    who = _username(user)
    why = reason or "operator action from /performance"

    def _run() -> None:
        try:
            if resolved == "LoggerWorker":
                _restart_logger()
            elif resolved == "CatalogReplicator":
                _restart_catalog()
            else:
                _restart_metrics()
            _audit(
                f"Worker restarted: {resolved}",
                f"User {who} restarted {resolved} due to {why}",
                user=user,
                criticity=3,
            )
        except Exception as exc:
            _LOGGER.exception("worker restart failed name=%s", resolved)
            _audit(
                f"Worker restart failed: {resolved}",
                f"User {who} failed to restart {resolved}: {exc}",
                user=user,
                criticity=4,
            )
        finally:
            with _RESTART_LOCK:
                _RESTARTING[resolved] = False
            _refresh_metrics()

    threading.Thread(target=_run, name=f"Restart{resolved}", daemon=True).start()
    return {
        "ok": True,
        "accepted": True,
        "worker": resolved,
        "state": "restarting",
        "WORKERS": worker_snapshot(),
    }


def _restart_logger() -> dict[str, Any]:
    from .. import PyAutomation
    from ..workers.logger import LoggerWorker

    app = PyAutomation()
    old = getattr(app, "db_worker", None)
    period = float(getattr(old, "_period", 10.0) or 10.0)
    manager = getattr(old, "_manager", None) or getattr(app, "db_manager", None)
    if manager is None:
        raise OpsControlError("LoggerWorker manager is not available")
    if old is not None:
        old.stop()
        old.join(timeout=8.0)
    new = LoggerWorker(manager, period=period)
    app.db_worker = new
    new.start()
    return {"state": "alive"}


def _restart_catalog() -> dict[str, Any]:
    from ..catalog.replicator import start_catalog_replicator, stop_catalog_replicator

    stop_catalog_replicator()
    start_catalog_replicator()
    return {"state": "alive"}


def _restart_metrics() -> dict[str, Any]:
    from .. import PyAutomation
    from ..workers.metrics_sampler import MetricsSamplerWorker

    app = PyAutomation()
    old = getattr(app, "metrics_worker", None)
    interval = getattr(old, "_interval_s", None)
    if old is not None:
        old.stop()
        old.join(timeout=8.0)
    new = MetricsSamplerWorker(interval_seconds=interval)
    app.metrics_worker = new
    new.start()
    return {"state": "alive"}


def saf_retry(*, user=None, reason: str | None = None) -> dict[str, Any]:
    from .. import PyAutomation
    from ..persistence import get_persistence_gateway

    replicated = 0
    worker = getattr(PyAutomation(), "db_worker", None)
    request = getattr(worker, "request_cycle", None)
    if callable(request):
        request()
    try:
        replicated = int(get_persistence_gateway().replicate_once() or 0)
    except Exception:
        _LOGGER.warning("SAF retry replicate_once failed; LoggerWorker will retry", exc_info=True)
    who = _username(user)
    _audit(
        "SAF retry requested",
        f"User {who} forced SAF replication ({reason or 'queue depth'}); written={replicated}",
        user=user,
        criticity=2,
    )
    _refresh_metrics()
    return {"ok": True, "replicated": replicated}


def saf_reset(*, confirm: bool, user=None, reason: str | None = None) -> dict[str, Any]:
    if not confirm:
        raise OpsControlError("confirm=true is required to empty the SAF queue")
    from ..persistence import get_persistence_gateway

    dropped = get_persistence_gateway().drop_unsent(confirm=True)
    who = _username(user)
    _audit(
        "SAF queue emptied",
        f"User {who} dropped {dropped} pending SAF samples ({reason or 'confirmed reset'})",
        user=user,
        criticity=5,
    )
    _refresh_metrics()
    return {"ok": True, "dropped": dropped}


def catalog_sync(*, user=None, reason: str | None = None) -> dict[str, Any]:
    from ..catalog.replicator import get_catalog_replicator

    worker = get_catalog_replicator()
    if worker is None:
        raise OpsControlError("Catalog replicator is not running")
    worker.request_full_sync(reason=reason or "operator /performance")

    def _run() -> None:
        try:
            worker.cycle(force=True)
        except Exception:
            _LOGGER.warning("catalog force sync failed", exc_info=True)

    threading.Thread(target=_run, name="CatalogForceSync", daemon=True).start()
    who = _username(user)
    _audit(
        "Catalog sync requested",
        f"User {who} forced catalog sync ({reason or 'operator'})",
        user=user,
        criticity=2,
    )
    _refresh_metrics()
    return {"ok": True, "accepted": True}


def catalog_clean_orphans(
    *,
    age_minutes: int = 10,
    user=None,
    reason: str | None = None,
) -> dict[str, Any]:
    if int(age_minutes) not in AGE_CHOICES:
        raise OpsControlError("age_minutes must be one of 5, 10, 30, 60")
    from ..catalog.replicator import get_catalog_replicator

    worker = get_catalog_replicator()
    if worker is None:
        raise OpsControlError("Catalog replicator is not running")
    dropped = int(worker.drop_orphans_older_than(int(age_minutes)))
    who = _username(user)
    _audit(
        "Catalog orphans cleaned",
        f"User {who} dropped {dropped} pending orphans older than {age_minutes} min",
        user=user,
        criticity=3,
    )
    _refresh_metrics()
    return {"ok": True, "dropped": dropped, "age_minutes": int(age_minutes)}


def rebuild_derived_tags(*, user=None, reason: str | None = None) -> dict[str, Any]:
    from .. import PyAutomation
    from ..signal_conditioning.filtered_tags import (
        ensure_filtered_tag,
        is_filtered_derivative_name,
        source_tag_name,
        tag_filter_enabled,
    )

    app = PyAutomation()
    rows = list(app.cvt.get_tags() or [])
    names = {str(row.get("name") or "") for row in rows if row}
    created = 0
    removed = 0
    for row in rows:
        name = str((row or {}).get("name") or "")
        if not name:
            continue
        if is_filtered_derivative_name(name):
            source = source_tag_name(name)
            if source and source not in names:
                try:
                    app.delete_tag_by_name(name)
                    removed += 1
                except Exception:
                    _LOGGER.debug("orphan derived tag delete skipped name=%s", name, exc_info=True)
            continue
        tag = app.get_tag_by_name(name)
        if tag is None or not tag_filter_enabled(tag):
            continue
        if ensure_filtered_tag(tag) is not None:
            created += 1
    who = _username(user)
    _audit(
        "Derived tags rebuilt",
        f"User {who} rebuilt .f tags created={created} removed={removed} ({reason or 'operator'})",
        user=user,
        criticity=3,
    )
    _refresh_metrics()
    return {"ok": True, "ensured": created, "removed": removed}


def update_runtime_settings(payload: dict[str, Any], *, user=None) -> dict[str, Any]:
    from .. import PyAutomation
    from ..persistence import get_persistence_gateway
    from ..persistence.config import SafConfig
    from ..persistence.remote import set_missing_tag_drop_after
    from ..catalog.replicator import get_catalog_replicator

    data = dict(payload or {})
    applied: dict[str, Any] = {}
    app = PyAutomation()
    ring = data.get("SAF_RING_MAXSIZE", data.get("saf_ring_maxsize"))
    if ring is not None:
        value = max(1000, min(1_000_000, int(ring)))
        gw = get_persistence_gateway()
        current = gw.config
        new_cfg = SafConfig(
            journal_path=current.journal_path,
            max_disk_bytes=current.max_disk_bytes,
            max_pending_rows=current.max_pending_rows,
            ring_maxsize=value,
            tag_batch_size=current.tag_batch_size,
            tag_flush_interval_s=current.tag_flush_interval_s,
            replicate_batch_size=current.replicate_batch_size,
            replicate_rate_per_s=current.replicate_rate_per_s,
            circuit_fail_threshold=current.circuit_fail_threshold,
            circuit_open_s=current.circuit_open_s,
            gc_sent_after_s=current.gc_sent_after_s,
            gc_batch=current.gc_batch,
            backup_size_bytes=current.backup_size_bytes,
            wal_autocheckpoint=current.wal_autocheckpoint,
        )
        gw.config = new_cfg
        gw.journal.config = new_cfg
        gw.replicator.config = new_cfg
        app.set_app_config(saf_ring_maxsize=value)
        applied["SAF_RING_MAXSIZE"] = value
    retries = data.get("REPLICATE_RETRY_LIMIT", data.get("replicate_retry_limit"))
    if retries is not None:
        value = set_missing_tag_drop_after(int(retries))
        catalog = get_catalog_replicator()
        if catalog is not None:
            catalog._max_retries = max(1, min(20, int(retries)))
        app.set_app_config(replicate_retry_limit=value)
        applied["REPLICATE_RETRY_LIMIT"] = value
    if not applied:
        raise OpsControlError("No supported settings in payload")
    who = _username(user)
    _audit(
        "Runtime settings updated",
        f"User {who} updated {applied}",
        user=user,
        criticity=3,
    )
    return {"ok": True, "applied": applied}
