# -*- coding: utf-8 -*-
"""Bidirectional catalog replicator — OS thread, never on the acquisition hot path.

Operational Silence Doctrine (operator Events table):
- Never emit "Catalog sync completed" or "Catalog divergence auto-merged" to Events.
  Those go to app.log (DEBUG / INFO) and CatalogMetrics only.
- Emit Events only for exceptions the operator must act on:
  sync failed, local-only mode, unresolved (manual) conflict.
- Online period 300 s; compare business content via SHA-256, not audit timestamps.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone

from ..utils.system_event_audit import clip, persist_system_event
from ..utils.audit_metrics import cooldown_allows
from ..workers.worker import BaseWorker
from .alarms import (
    set_conflict,
    set_local_only,
    set_orphan_rows,
    set_remote_inconsistency,
    set_sync_failed,
)
from .conflict import VersionStamp, resolve
from .content_hash import contents_equal
from .identity import (
    identity_key,
    index_by_identity,
    lookup_fk_parent,
    parent_fk_known,
    prepare_pull_row,
    prepare_push_row,
)
from .local_provider import LocalCatalogProvider
from .metrics import update as update_metrics
from .partition import areas_compatible
from .provider import refresh_catalog_source
from .remote_provider import RemoteCatalogProvider
from .replica_db import (
    close_replica_thread_connection,
    ensure_replica_database,
    replica_watermark_ms,
    reset_replica_database,
)
from .schema import (
    CHILD_TABLES,
    LOOKUP_TABLES,
    PARENT_TABLES,
    PARTITIONED_TABLES,
    PUSH_ONLY_TABLES,
    REPLICATED_TABLES,
)
from .versions import (
    edge_node_id,
    get_local,
    get_remote,
    list_local_pending,
    now_ms,
    pending_count,
    touch_local,
    touch_remote,
)

_LOGGER = logging.getLogger("pyautomation")
_BATCH = 200
_FAIL_THRESHOLD = 5
_ORPHAN_THRESHOLD = 5
_ORPHAN_TTL_S = 300.0  # drop unresolved child rows after 5 minutes
_MAX_RETRIES = 5  # drop unresolved child rows after 5 sync cycles
_LOCAL_ONLY_S = 3600.0
_ONLINE_INTERVAL_S = 300.0
# User rows also invalidate via PG NOTIFY / Redis Pub/Sub (user_cache).
# This worker is disaster-recovery catch-up, not the <2s login path.
_CATCHUP_INTERVAL_S = 30.0
_CYCLE_TIMEOUT_S = 10.0
_FULL_SCAN_INTERVAL_S = 300.0
_EVENT_DELTA_THRESHOLD = 50
_EXCEPTION_EVENT_COOLDOWN_S = 300.0
_BACKOFF_INTERVALS_S = (30.0, 60.0, 120.0, 300.0, 900.0)
_SYNC_FAIL_MIN_OUTAGE_S = 300.0  # do not latch sync-failed alarm during short outages
_MAX_CONFLICT_SAMPLES = 5


def _is_transient_connection_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in ("InterfaceError", "OperationalError", "ConnectionError", "ConnectionDoesNotExist"):
        return True
    mod = (type(exc).__module__ or "").lower()
    text = str(exc).lower()
    if "psycopg2" in mod or "peewee" in mod or "mysql" in mod:
        if "connection" in text or "closed" in text or "server closed" in text:
            return True
    return False


def _is_integrity_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in ("IntegrityError",):
        return True
    text = str(exc).lower()
    return (
        "not null constraint" in text
        or "constraint failed" in text
        or "foreign key constraint" in text
        or "unique constraint" in text
    )


class CatalogPullAborted(Exception):
    """Hard local-apply error: roll back this cycle's SQLite catalog writes."""


_REQUIRED_PULL_FKS: dict[str, tuple[tuple[str, str], ...]] = {
    "tags": (("unit", "unit_id"),),
    "alarms": (("tag", "tag_id"),),
    "tagsmachines": (("tag", "tag_id"), ("machine", "machine_id")),
}


@dataclass
class _PendingOrphan:
    """Child catalog row waiting for a parent tag/machine to appear locally."""

    table: str
    key: str
    remote_row: dict
    first_seen_mono: float
    retry_count: int = 0


def _fk_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (int, float)) and int(value) == 0:
        return True
    return False


def _pull_has_required_fks(table: str, payload: dict) -> bool:
    for field, column in _REQUIRED_PULL_FKS.get(table) or ():
        if not _fk_missing(payload.get(field)) or not _fk_missing(payload.get(column)):
            continue
        return False
    return True


class CatalogReplicatorWorker(BaseWorker):
    def __init__(
        self,
        sync_interval: float = _ONLINE_INTERVAL_S,
        startup_grace_s: float = 15.0,
        catchup_interval: float = _CATCHUP_INTERVAL_S,
    ):
        super().__init__()
        self.name = "CatalogReplicatorWorker"
        self.daemon = True
        self.sync_interval = max(60.0, float(sync_interval))
        self._catchup_interval = max(5.0, float(catchup_interval))
        self._startup_grace_s = max(0.0, float(startup_grace_s))
        self._startup_mono = time.monotonic()
        self._reconnect_grace_until = 0.0
        self._catch_up = False
        self._local = LocalCatalogProvider()
        self._remote = RemoteCatalogProvider(prefer_replica_reads=True)
        self._failures = 0
        self._local_only_since: float | None = None
        self._unresolved = 0
        self._cycle_conflicts: list[tuple[str, str, str]] = []
        self._cycle_conflict_counts: dict[str, int] = {}
        self._sync_failed_latched = False
        self._local_only_latched = False
        self._sync_cycles = 0
        self._remote_available: bool | None = None
        self._backoff_step = 0
        self._remote_down_logged = False
        self._transient_remote_errors = 0
        self._cycle_backup_skips = 0
        self._remote_outage_since: float | None = None
        self._hard_fail_since: float | None = None
        self._last_sync = None
        self._last_remote_version_ms: int | None = None
        self._last_full_scan_mono = 0.0
        self._cycle_lock = threading.Lock()
        self._executor = None
        self._cycle_integrity_errors = 0
        self._cycle_deferred_errors = 0
        self._cycle_deferred_by_table: dict[str, int] = {}
        self._cycle_deferred_samples: list[str] = []
        self._consecutive_integrity_cycles = 0
        self._consecutive_errors = 0
        self._orphan_latched = False
        self._inconsistency_latched = False
        self._cycle_cross_area_count = 0
        self._pending_orphans: dict[tuple[str, str], _PendingOrphan] = {}
        self._pending_loaded = False
        self._max_retries = _MAX_RETRIES
        self._full_sync_log_mono = 0.0
        self._tags_sync_pending = False
        self._parent_load_failed = False
        self._connection_backoff = False
        self._recycled_this_cycle = False

    def stop(self):
        super().stop()
        executor = self._executor
        self._executor = None
        if executor is None:
            return
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
        except Exception:
            _LOGGER.debug("catalog replicator executor shutdown skipped", exc_info=True)

    def _make_executor(self):
        """Native OS threads. gevent.monkey.patch_all() does not apply here."""
        try:
            from gevent.threadpool import ThreadPoolExecutor
        except ImportError:
            from concurrent.futures import ThreadPoolExecutor
        return ThreadPoolExecutor(max_workers=1)

    def _thread_pool_executor(self):
        if self._executor is None:
            self._executor = self._make_executor()
        return self._executor

    def _cycle_in_thread(self, force: bool = False):
        """Executed on an OS thread. Never touches the gevent hub event-loop."""
        if not self._cycle_lock.acquire(blocking=False):
            _LOGGER.warning("Catalog sync still running in OS thread; skip overlapping cycle")
            return {"skipped": True, "reason": "overlap"}
        try:
            from ..utils.db_connections import ephemeral_historian, historian_role_scope

            replica = ensure_replica_database()
            primary = None
            try:
                from automation import PyAutomation

                primary = getattr(PyAutomation(), "_db", None)
            except Exception:
                primary = None
            # The pool thread reports itself as ``Dummy-9``; name the subsystem
            # so pg_stat_activity attributes the socket to catalog sync.
            with historian_role_scope("CatalogReplicator"):
                with ephemeral_historian(replica):
                    with ephemeral_historian(primary):
                        return self.cycle(force=force)
        except Exception:
            _LOGGER.exception("Catalog sync in thread failed")
            raise
        finally:
            self._cycle_lock.release()

    def _is_remote_available(self) -> bool:
        """Historian reachable on the dedicated replica handle (never the hot API proxy)."""
        if refresh_catalog_source() != "remote":
            return False
        return self._historian_ready()

    def _increment_backoff(self) -> None:
        self._backoff_step = min(self._backoff_step + 1, len(_BACKOFF_INTERVALS_S) - 1)

    def _reset_backoff(self) -> None:
        self._backoff_step = 0

    def _handle_remote_unavailable(self, now: float) -> dict:
        """Offline mode: local catalog is source of truth; no remote I/O or sync-failed alarm."""
        from .provider import set_catalog_source

        if self._local_only_since is None:
            self._local_only_since = now
        elapsed = now - self._local_only_since
        local_only = elapsed >= _LOCAL_ONLY_S
        set_local_only(local_only)
        self._latch_local_only(local_only)
        set_sync_failed(False)
        self._sync_failed_latched = False
        self._failures = 0
        self._consecutive_errors = 0
        self._hard_fail_since = None
        self._transient_remote_errors = 0
        self._catch_up = True
        self._increment_backoff()
        set_catalog_source("local")
        reset_replica_database()
        update_metrics(
            source="local",
            pending_rows=pending_count(),
            conflict_count=self._unresolved,
            consecutive_failures=0,
            local_only_since_utc=datetime.now(timezone.utc).isoformat(),
        )
        if not self._remote_down_logged:
            _LOGGER.info(
                "Catalog sync skipped: remote historian unavailable (local catalog active)"
            )
            self._remote_down_logged = True
        close_replica_thread_connection()
        return {"skipped": True, "reason": "remote-down"}

    def arm_reconnect_grace(self, seconds: float = 5.0) -> None:
        """Hold sync briefly after reconnect so the Peewee socket can settle."""
        self._reconnect_grace_until = time.monotonic() + max(0.0, float(seconds))
        self._catch_up = True
        reset_replica_database()

    def request_full_sync(self, *, reason: str = "reconnect/version change") -> None:
        """Non-blocking: next cycle pulls the full remote catalog (no watermark)."""
        now = time.monotonic()
        if reason.startswith("reconnect") or (now - self._full_sync_log_mono) >= 30.0:
            _LOGGER.info("Performing full catalog sync (%s)", reason)
            self._full_sync_log_mono = now
        self._last_sync = None
        self._last_remote_version_ms = None
        self._last_full_scan_mono = 0.0
        self._catch_up = True

    def _sync_full(self) -> dict:
        """Full catalog pull, e.g. after historian reconnect. Safe outside cycle()."""
        self.request_full_sync(reason="reconnect/version change")
        result = self.cycle(force=True)
        if not result.get("skipped"):
            _LOGGER.info("Full catalog sync completed")
        return result

    def sync_status(self) -> dict:
        last = self._last_sync
        return {
            "CATALOG_PENDING_ROWS": len(self._pending_orphans),
            "CATALOG_LAST_SYNC": last.isoformat() if last else None,
            "CATALOG_SYNC_ERRORS": int(self._consecutive_errors),
            "CATALOG_ORPHAN_ALARM": bool(self._orphan_latched),
            "CATALOG_REMOTE_INCONSISTENCY": bool(self._inconsistency_latched),
        }

    def _recycle_replica_handle(self) -> None:
        """Drop a dead Peewee/libpq socket so the next I/O opens a fresh replica."""
        if self._recycled_this_cycle:
            return
        self._recycled_this_cycle = True
        try:
            reset_replica_database()
            close_replica_thread_connection()
        except Exception:
            _LOGGER.debug("catalog replica recycle skipped", exc_info=True)

    def _wait_interval(self) -> float:
        try:
            from ..persistence import get_persistence_gateway

            gateway = get_persistence_gateway()
            high = int(getattr(gateway.config, "shed_high", 50_000) or 50_000)
            if int(gateway.pending_count() or 0) > high:
                return self.sync_interval
        except Exception:
            pass
        if self._remote_available is False or self._connection_backoff:
            return _BACKOFF_INTERVALS_S[self._backoff_step]
        if self._catch_up or pending_count() > 0 or self._pending_orphans:
            return self._catchup_interval
        return self.sync_interval

    def run(self):
        while not self.stop_event.is_set():
            future = self._thread_pool_executor().submit(self._cycle_in_thread, False)
            try:
                future.result(timeout=_CYCLE_TIMEOUT_S)
            except FuturesTimeoutError:
                _LOGGER.warning(
                    "Catalog sync thread timeout, skipping cycle. (limit=%.1fs)",
                    _CYCLE_TIMEOUT_S,
                )
                cancel = getattr(future, "cancel", None)
                if callable(cancel):
                    cancel()
            except TimeoutError:
                _LOGGER.warning(
                    "Catalog sync thread timeout, skipping cycle. (limit=%.1fs)",
                    _CYCLE_TIMEOUT_S,
                )
                cancel = getattr(future, "cancel", None)
                if callable(cancel):
                    cancel()
            except BaseException as exc:
                if type(exc).__name__ in ("Timeout", "TimeoutError"):
                    _LOGGER.warning(
                        "Catalog sync thread timeout, skipping cycle. (limit=%.1fs)",
                        _CYCLE_TIMEOUT_S,
                    )
                    cancel = getattr(future, "cancel", None)
                    if callable(cancel):
                        cancel()
                elif isinstance(exc, Exception):
                    _LOGGER.exception("Catalog sync thread exception.")
                    self._failures += 1
                    self._latch_sync_failed(self._failures >= _FAIL_THRESHOLD)
                    update_metrics(consecutive_failures=self._failures)
                else:
                    raise
            self.stop_event.wait(self._wait_interval())

    def _historian_ready(self) -> bool:
        """Prefer dedicated replica handle; do not poke the API proxy."""
        try:
            db = ensure_replica_database()
            if db is None:
                return False
            if getattr(db, "is_closed", lambda: True)():
                db.connect(reuse_if_open=True)
            db.execute_sql("SELECT 1")
            return True
        except Exception:
            return False

    def _probe_replica_writable(self) -> bool:
        """True only if DML can land. ``SELECT 1`` is not enough on a half-open tunnel."""
        try:
            db = ensure_replica_database()
            if db is None:
                return False
            if getattr(db, "is_closed", lambda: True)():
                db.connect(reuse_if_open=True)
            db.execute_sql("SELECT 1")
            db.execute_sql("UPDATE catalog_versions SET version = version WHERE FALSE")
            return True
        except Exception as exc:
            text = str(exc).lower()
            name = type(exc).__name__.lower()
            if "catalog_versions" in text and (
                "does not exist" in text
                or "undefined" in text
                or "undefinedtable" in name
            ):
                return True
            return False

    def _idle_while_connection_backoff(self) -> dict | None:
        """No sqlite scan and no extra SELECT 1. One write probe, then drop the socket.

        The SSH/TCP tunnel can answer ``SELECT 1`` while DML still dies. Catalog
        stays on the local sqlite until this probe succeeds. SAF/DAQ keep their
        own historian path; this must not call ``mark_remote_db_dead``.
        """
        from .provider import set_catalog_source

        set_catalog_source("local")
        if self._probe_replica_writable():
            self._connection_backoff = False
            self._reset_backoff()
            _LOGGER.info("Catalog replica writable again; resuming full sync")
            self.request_full_sync(reason="replica writable after backoff")
            return None
        self._recycle_replica_handle()
        self._increment_backoff()
        self._consecutive_errors += 1
        if self._consecutive_errors >= _FAIL_THRESHOLD:
            self._latch_sync_failed(True)
        else:
            self._latch_sync_failed(False)
        _LOGGER.warning(
            "Catalog replica still not writable; skipping sync this cycle "
            "(backoff %.0fs, no tunnel traffic until then). Runtime catalog unchanged.",
            _BACKOFF_INTERVALS_S[self._backoff_step],
        )
        close_replica_thread_connection()
        return {
            "skipped": True,
            "reason": "connection-backoff",
            "connection_errors": 1,
        }

    def cycle(self, *, force: bool = False) -> dict:
        now = time.monotonic()
        if now < self._reconnect_grace_until:
            return {"skipped": True, "reason": "reconnect-grace"}
        if (
            not force
            and self._startup_grace_s > 0
            and (now - self._startup_mono) < self._startup_grace_s
        ):
            return {"skipped": True, "reason": "startup-grace"}

        # Write-dead replica: do not SELECT 1 / open the tunnel before the probe.
        if self._connection_backoff and not force:
            skipped = self._idle_while_connection_backoff()
            if skipped is not None:
                return skipped

        self._ensure_pending_loaded()

        remote_available = self._is_remote_available()
        was_available = self._remote_available
        self._remote_available = remote_available
        self._transient_remote_errors = 0
        self._recycled_this_cycle = False

        if not remote_available:
            if was_available is not False:
                self._remote_outage_since = now
                self._emit_exception_event(
                    message="Catalog offline mode",
                    description=clip(
                        "Remote historian unreachable; edge catalog operating locally until sync resumes",
                        256,
                    ),
                    criticity=3,
                    cooldown_key="catalog:offline-mode",
                )
            return self._handle_remote_unavailable(now)

        if was_available is False:
            self._reset_backoff()
            self._remote_down_logged = False
            self.request_full_sync(reason="reconnect/version change")
            reset_replica_database()
            outage_s = (
                (now - self._remote_outage_since) if self._remote_outage_since is not None else 0.0
            )
            _LOGGER.info(
                "Remote historian available; catalog sync resuming (outage %.0fs)",
                outage_s,
            )
            if outage_s >= 1.0:
                self._emit_exception_event(
                    message="Catalog online sync resumed",
                    description=clip(
                        f"Remote historian restored after {int(outage_s)}s; replicating pending catalog rows",
                        256,
                    ),
                    criticity=2,
                    cooldown_key="catalog:online-resumed",
                )
            self._remote_outage_since = None

        source = refresh_catalog_source()
        update_metrics(source=source, pending_rows=pending_count(), conflict_count=self._unresolved)
        if source != "remote":
            return self._handle_remote_unavailable(now)
        if not self._historian_ready():
            return {"skipped": True, "reason": "historian-not-ready"}
        self._local_only_since = None
        set_local_only(False)
        self._latch_local_only(False)
        self._cycle_conflicts = []
        self._cycle_conflict_counts = {}
        self._cycle_integrity_errors = 0
        self._cycle_deferred_errors = 0
        self._cycle_deferred_by_table = {}
        self._cycle_deferred_samples = []
        self._cycle_cross_area_count = 0
        self._cycle_backup_skips = 0
        self._parent_load_failed = False
        self._ensure_pending_loaded()

        full_scan = self._should_full_scan()
        try:
            pending = list_local_pending()
        except Exception:
            pending = []
        pending_pks: dict[str, set[str]] = {}
        for item in pending:
            pending_pks.setdefault(str(item.table_name), set()).add(str(item.row_id))

        since_ms = int(self._last_remote_version_ms or 0)
        local_rows_by_table = {table: self._local.read_all(table) for table in REPLICATED_TABLES}
        remote_rows_by_table: dict[str, list] = {}
        row_errors = 0
        tables = self._tables_this_cycle()
        replica = ensure_replica_database()
        load_txn = replica.atomic() if replica is not None else nullcontext()
        with load_txn:
            for table in tables:
                if self._transient_remote_errors:
                    remote_rows_by_table[table] = []
                    continue
                if table in CHILD_TABLES and self._parent_load_failed:
                    remote_rows_by_table[table] = []
                    _LOGGER.warning(
                        "Skipping pull of %s this cycle: tags/machines connection error; "
                        "retrying next cycle with tags prioritized",
                        table,
                    )
                    continue
                try:
                    if table in PUSH_ONLY_TABLES:
                        # Disaster backup lives on the historian; this edge never
                        # hydrates local catalog.db from remote address-space rows.
                        remote_rows_by_table[table] = []
                        continue
                    remote_rows_by_table[table] = self._load_remote_rows(
                        table, full_scan=full_scan, since_ms=since_ms
                    )
                except Exception as exc:
                    remote_rows_by_table[table] = []
                    if _is_transient_connection_error(exc):
                        self._transient_remote_errors += 1
                        if table in PARENT_TABLES:
                            self._parent_load_failed = True
                            self._tags_sync_pending = True
                        self._recycle_replica_handle()
                        _LOGGER.warning("catalog load skipped (remote connection) table=%s", table)
                    else:
                        row_errors += 1
                        _LOGGER.exception("catalog load failed table=%s", table)
        for table in REPLICATED_TABLES:
            remote_rows_by_table.setdefault(table, [])
        local_index = {
            table: index_by_identity(table, local_rows_by_table[table]) for table in REPLICATED_TABLES
        }
        remote_index = {
            table: index_by_identity(table, remote_rows_by_table[table]) for table in REPLICATED_TABLES
        }
        for child in CHILD_TABLES:
            remote_rows_by_table[child] = self._filter_child_rows(
                child,
                remote_rows_by_table.get(child) or [],
                local_index=local_index,
                remote_index=remote_index,
            )
            remote_index[child] = index_by_identity(child, remote_rows_by_table[child])
        if not self._parent_load_failed:
            if self._cycle_cross_area_count > 0:
                self._latch_remote_inconsistency(True)
            elif full_scan:
                self._latch_remote_inconsistency(False)

        pushed = pulled = auto_resolved = 0
        tags_connection_error = False
        for table in tables:
            if self._transient_remote_errors:
                break
            if table in CHILD_TABLES and self._parent_load_failed:
                continue
            try:
                table_pending = pending_pks.get(table) or set()
                if (
                    not full_scan
                    and not remote_rows_by_table[table]
                    and not table_pending
                ):
                    continue
                p, u, c, e = self._sync_table(
                    table,
                    local_rows=local_rows_by_table[table],
                    remote_rows=remote_rows_by_table[table],
                    local_index=local_index,
                    remote_index=remote_index,
                    partial_remote=not full_scan,
                    pending_pks=table_pending,
                )
                pushed += p
                pulled += u
                auto_resolved += c
                row_errors += e
            except Exception as exc:
                if _is_transient_connection_error(exc):
                    self._transient_remote_errors += 1
                    if table in PUSH_ONLY_TABLES:
                        self._cycle_backup_skips += 1
                    if table in PARENT_TABLES:
                        self._parent_load_failed = True
                        self._tags_sync_pending = True
                    if table == "tags":
                        tags_connection_error = True
                    self._recycle_replica_handle()
                    _LOGGER.warning(
                        "catalog sync table skipped (remote connection) table=%s", table
                    )
                else:
                    row_errors += 1
                    _LOGGER.warning(
                        "catalog sync table failed table=%s: %s", table, exc
                    )

        resolved_pending = 0
        socket_dead_early = bool(self._transient_remote_errors)
        if not self._parent_load_failed and not socket_dead_early:
            resolved_pending = self._resolve_pending_orphans(local_index, remote_index)
            pulled += resolved_pending

        if not socket_dead_early:
            self._bump_pending_retries()
            self._cleanup_pending_orphans(local_index)
            self._flush_pending_to_disk()

        self._unresolved = 0
        connection_errors = self._transient_remote_errors
        backup_skips = int(self._cycle_backup_skips or 0)
        hard_connection = max(0, connection_errors - backup_skips)
        deferred = self._cycle_deferred_errors + self._cycle_integrity_errors
        hard_fail = bool(hard_connection or row_errors)
        socket_dead = bool(hard_connection or (connection_errors and not backup_skips))
        if not self._parent_load_failed and not tags_connection_error:
            self._tags_sync_pending = False
        if backup_skips or socket_dead:
            self._recycle_replica_handle()
        if backup_skips and not hard_connection:
            _LOGGER.info(
                "Catalog backup skip %s row(s) (push-only / remote blip); runtime catalog unchanged",
                backup_skips,
            )
        if socket_dead:
            _LOGGER.warning(
                "Catalog sync had %s remote connection error(s); recycling replica handle and backing off",
                hard_connection or connection_errors,
            )
            self._connection_backoff = True
            self._increment_backoff()
        if hard_fail:
            self._consecutive_errors += 1
            if not socket_dead:
                self._catch_up = True
            update_metrics(consecutive_failures=self._consecutive_errors)
            if self._consecutive_errors >= _FAIL_THRESHOLD:
                self._latch_sync_failed(True)
            else:
                self._latch_sync_failed(False)
        else:
            self._consecutive_errors = 0
            self._failures = 0
            self._connection_backoff = False
            self._reset_backoff()
            self._latch_sync_failed(False)
            update_metrics(consecutive_failures=0)
            if (
                pending_count() == 0
                and pushed + pulled < _EVENT_DELTA_THRESHOLD
                and not self._cycle_integrity_errors
            ):
                self._catch_up = False
        if self._cycle_integrity_errors:
            self._catch_up = True
        if self._cycle_deferred_errors:
            self._log_deferred_summary()
        # Pending child remaps are sidecar retries, not a process fault.
        # Keep ALM.CATALOG.OrphanRows off the operator banner.
        self._consecutive_integrity_cycles = 0
        self._latch_orphan_rows(False)
        self._failures = self._consecutive_errors
        # Auto-merge always picks a side today — sticky Conflict alarm is for
        # future manual-merge paths only (kept cleared on successful cycles).
        set_conflict(False)
        self._sync_cycles += 1
        if not row_errors and not hard_connection:
            self._last_sync = datetime.now(timezone.utc)
            watermark = replica_watermark_ms()
            self._last_remote_version_ms = watermark or now_ms()
            if full_scan:
                self._last_full_scan_mono = time.monotonic()
        summary = f"{pushed} pushed, {pulled} pulled, {auto_resolved} auto-merged, {row_errors} errors"
        update_metrics(
            source="remote",
            last_success_utc=datetime.now(timezone.utc).isoformat(),
            pending_rows=pending_count(),
            conflict_count=auto_resolved,
            sync_cycles=self._sync_cycles,
            last_cycle_summary=summary,
            last_auto_merged=auto_resolved,
            orphan_pending_rows=len(self._pending_orphans),
            last_sync_utc=self._last_sync.isoformat() if self._last_sync else None,
            orphan_alarm=self._orphan_latched,
            consecutive_failures=self._consecutive_errors,
        )
        self._log_cycle_outcome(
            pushed=pushed,
            pulled=pulled,
            auto_resolved=auto_resolved,
            row_errors=row_errors,
            summary=summary,
        )
        close_replica_thread_connection()
        return {
            "pushed": pushed,
            "pulled": pulled,
            "conflicts": auto_resolved,
            "errors": row_errors + connection_errors,
            "connection_errors": connection_errors,
            "deferred": deferred,
            "incremental": not full_scan,
        }

    def _latch_sync_failed(self, active: bool) -> None:
        """ISA alarm + edge-triggered operator Event on rising edge only.

        Deferred FK remaps and push-only blips never reach here. Hard errors
        must persist for ``_SYNC_FAIL_MIN_OUTAGE_S`` so a healthy runtime with
        a noisy catalog sidecar does not flash the operator banner.
        """
        if self._consecutive_errors == 0:
            self._hard_fail_since = None
        elif self._hard_fail_since is None:
            self._hard_fail_since = time.monotonic()
        if active:
            started = self._hard_fail_since or time.monotonic()
            if (time.monotonic() - started) < _SYNC_FAIL_MIN_OUTAGE_S:
                active = False
            if self._remote_outage_since is not None:
                elapsed = time.monotonic() - self._remote_outage_since
                if elapsed < _SYNC_FAIL_MIN_OUTAGE_S:
                    active = False
        set_sync_failed(active)
        if active and not self._sync_failed_latched:
            self._emit_exception_event(
                message="Catalog sync failed",
                description=clip(
                    f"Catalog replicator failed {self._failures} consecutive cycles",
                    256,
                ),
                criticity=5,
                cooldown_key="catalog:sync-failed",
            )
        self._sync_failed_latched = bool(active)

    def _latch_orphan_rows(self, active: bool) -> None:
        set_orphan_rows(active)
        if active and not self._orphan_latched:
            self._emit_exception_event(
                message="Catalog orphan rows",
                description=clip(
                    f"Child catalog rows missing parent FKs for {self._consecutive_integrity_cycles} cycles",
                    256,
                ),
                criticity=3,
                cooldown_key="catalog:orphan-rows",
            )
        self._orphan_latched = bool(active)

    def _latch_remote_inconsistency(self, active: bool) -> None:
        set_remote_inconsistency(active)
        if active and not self._inconsistency_latched:
            _LOGGER.error(
                "Found %s inconsistent tagsmachines rows in remote. Manual correction required.",
                self._cycle_cross_area_count,
            )
            self._emit_exception_event(
                message="Remote catalog inconsistency detected",
                description=clip(
                    f"{self._cycle_cross_area_count} tagsmachines rows have cross-area binds. Correct remote data.",
                    256,
                ),
                criticity=4,
                cooldown_key="catalog:remote-inconsistency",
            )
        self._inconsistency_latched = bool(active)

    def _latch_local_only(self, active: bool) -> None:
        """ISA alarm + edge-triggered operator Event when local-only persists."""
        if active and not self._local_only_latched:
            self._emit_exception_event(
                message="Catalog local-only mode",
                description=clip(
                    "Remote historian unreachable; edge operating on local catalog only",
                    256,
                ),
                criticity=4,
                cooldown_key="catalog:local-only",
            )
        self._local_only_latched = bool(active)

    def _emit_exception_event(
        self,
        *,
        message: str,
        description: str,
        criticity: int,
        cooldown_key: str,
    ) -> None:
        if not cooldown_allows(cooldown_key, _EXCEPTION_EVENT_COOLDOWN_S):
            _LOGGER.debug("catalog exception event debounced key=%s", cooldown_key)
            return
        try:
            persist_system_event(
                message=message,
                description=description,
                classification="System",
                priority=2,
                criticity=criticity,
            )
        except Exception:
            _LOGGER.debug("catalog exception event skipped message=%s", message, exc_info=True)

    def _log_cycle_outcome(
        self,
        *,
        pushed: int,
        pulled: int,
        auto_resolved: int,
        row_errors: int,
        summary: str,
    ) -> None:
        """Operational silence: success / auto-merge never touch the Events table."""
        if row_errors:
            _LOGGER.warning("Catalog sync completed with errors (%s)", summary)
            return
        if auto_resolved > 0:
            by_table = dict(self._cycle_conflict_counts)
            table_bits = ",".join(
                f"{name}×{count}" for name, count in sorted(by_table.items())
            ) or "mixed"
            samples = "; ".join(
                f"{t}:{k}({d})" for t, k, d in self._cycle_conflicts[:_MAX_CONFLICT_SAMPLES]
            )
            detail = clip(
                f"{auto_resolved} rows auto-merged ({table_bits})"
                + (f"; e.g. {samples}" if samples else ""),
                256,
            )
            _LOGGER.info("Catalog divergence auto-merged (log-only): %s", detail)
        _LOGGER.debug("Catalog sync completed (%s)", summary)

    def _note_conflict(
        self,
        table: str,
        key: str,
        local: VersionStamp,
        remote: VersionStamp,
        winner: str,
    ) -> None:
        """Accumulate samples for INFO logs / metrics — never Events."""
        table_s = str(table)
        self._cycle_conflict_counts[table_s] = self._cycle_conflict_counts.get(table_s, 0) + 1
        if len(self._cycle_conflicts) >= _MAX_CONFLICT_SAMPLES:
            return
        self._cycle_conflicts.append(
            (
                table_s,
                str(key),
                f"L{int(local.version)}/R{int(remote.version)}→{winner}",
            )
        )

    def _tables_this_cycle(self) -> list[str]:
        """Lookups first, then tags when a previous tags pull failed."""
        tables = list(REPLICATED_TABLES)
        if not self._tags_sync_pending:
            return tables
        lookups = [name for name in tables if name in LOOKUP_TABLES]
        rest = [name for name in tables if name not in LOOKUP_TABLES and name != "tags"]
        _LOGGER.info("Prioritizing tags catalog sync after previous connection error")
        return lookups + ["tags"] + rest

    def _note_deferred_row(self, table: str, key: str, *, direction: str) -> None:
        """Count a child FK remap skip. Per-row detail is DEBUG; cycle emits one INFO."""
        self._cycle_deferred_errors += 1
        table_s = str(table)
        self._cycle_deferred_by_table[table_s] = self._cycle_deferred_by_table.get(table_s, 0) + 1
        if len(self._cycle_deferred_samples) < _MAX_CONFLICT_SAMPLES:
            self._cycle_deferred_samples.append(f"{direction} {table_s}:{key}")
        _LOGGER.debug(
            "catalog %s deferred table=%s key=%s parent FK remap missed",
            direction,
            table_s,
            key,
        )

    def _log_deferred_summary(self) -> None:
        by = ",".join(
            f"{name}×{count}"
            for name, count in sorted(self._cycle_deferred_by_table.items())
        ) or "mixed"
        sample = "; ".join(self._cycle_deferred_samples)
        extra = f"; e.g. {sample}" if sample else ""
        _LOGGER.info(
            "Catalog sync deferred %s row(s) (%s); parent not in historian yet, "
            "retry later; runtime catalog unchanged%s",
            self._cycle_deferred_errors,
            by,
            extra,
        )

    def _note_deferred_orphan(self, table: str, key: str, remote_row: dict | None) -> None:
        if table not in CHILD_TABLES or not key or remote_row is None:
            return
        pending_key = (table, str(key))
        existing = self._pending_orphans.get(pending_key)
        if existing is None:
            self._pending_orphans[pending_key] = _PendingOrphan(
                table=table,
                key=str(key),
                remote_row=dict(remote_row),
                first_seen_mono=time.monotonic(),
            )
            return
        existing.remote_row = dict(remote_row)

    def _forget_pending_orphan(self, table: str, key: str) -> None:
        self._pending_orphans.pop((table, str(key)), None)

    def _ensure_pending_loaded(self) -> None:
        if self._pending_loaded:
            return
        self._pending_loaded = True
        try:
            self._local.init_pending_table()
            now_wall = datetime.now(timezone.utc)
            now_mono = time.monotonic()
            for item in self._local.load_pending_rows():
                table = str(item.get("table_name") or "")
                key = str(item.get("row_id") or "")
                if not table or not key:
                    continue
                seen = item.get("first_seen")
                age = 0.0
                if isinstance(seen, datetime):
                    if seen.tzinfo is None:
                        seen = seen.replace(tzinfo=timezone.utc)
                    age = max(0.0, (now_wall - seen).total_seconds())
                self._pending_orphans[(table, key)] = _PendingOrphan(
                    table=table,
                    key=key,
                    remote_row=dict(item.get("row_data") or {}),
                    first_seen_mono=now_mono - age,
                    retry_count=int(item.get("retries") or 0),
                )
        except Exception:
            _LOGGER.debug("pending_rows load skipped", exc_info=True)

    def _flush_pending_to_disk(self) -> None:
        try:
            self._local.init_pending_table()
            live = {(pending.table, pending.key) for pending in self._pending_orphans.values()}
            for item in self._local.load_pending_rows():
                pair = (str(item.get("table_name") or ""), str(item.get("row_id") or ""))
                if pair not in live:
                    self._local.delete_pending_row(pair[0], pair[1])
            now_mono = time.monotonic()
            wall_now = time.time()
            for pending in self._pending_orphans.values():
                age = max(0.0, now_mono - pending.first_seen_mono)
                first_seen = datetime.fromtimestamp(wall_now - age, tz=timezone.utc)
                self._local.save_pending_row(
                    pending.table,
                    pending.key,
                    pending.remote_row,
                    retries=pending.retry_count,
                    first_seen=first_seen,
                )
        except Exception:
            _LOGGER.debug("pending_rows flush skipped", exc_info=True)

    def _resolve_pending_orphans(self, local_index: dict, remote_index: dict) -> int:
        """Upsert child rows whose parent FKs appeared in a later cycle."""
        resolved = 0
        for pending_key, pending in list(self._pending_orphans.items()):
            table, key = pending_key
            payload = prepare_pull_row(
                table,
                pending.remote_row,
                local_index=local_index,
                remote_index=remote_index,
            )
            if self._skip_pull_reason(
                table, pending.remote_row, payload, local_index, remote_index
            ):
                continue
            try:
                new_pk = self._local.upsert(
                    table, payload, node_id="central", version=now_ms()
                )
            except Exception as exc:
                if _is_integrity_error(exc):
                    _LOGGER.warning(
                        "IntegrityError syncing %s row %s: %s",
                        table,
                        key,
                        exc,
                    )
                    continue
                _LOGGER.warning(
                    "Pending %s row %s still unresolved: %s", table, key, exc
                )
                continue
            payload["_pk"] = str(new_pk)
            local_index.setdefault(table, {})[key] = payload
            self._pending_orphans.pop(pending_key, None)
            resolved += 1
            _LOGGER.info("Resolved pending %s row %s", table, key)
        return resolved

    def _bump_pending_retries(self) -> None:
        for pending in self._pending_orphans.values():
            pending.retry_count += 1

    def _cleanup_pending_orphans(self, local_index: dict) -> int:
        """Drop pull-retries that stayed unresolved.

        Do not delete local catalog rows or raise OrphanRows: the child is
        waiting on a parent in the historian, which is expected during
        multi-edge catch-up.
        """
        now = time.monotonic()
        expired = [
            item
            for item in self._pending_orphans.items()
            if item[1].retry_count >= self._max_retries
            or (now - item[1].first_seen_mono) >= _ORPHAN_TTL_S
        ]
        if not expired:
            return 0
        by_table: dict[str, int] = {}
        for pending_key, pending in expired:
            by_table[pending.table] = by_table.get(pending.table, 0) + 1
            _LOGGER.info(
                "Giving up catalog pull retry of %s row %s after %s cycles; "
                "local catalog unchanged",
                pending.table,
                pending.key,
                pending.retry_count,
            )
            self._pending_orphans.pop(pending_key, None)
        summary = ",".join(f"{name}×{count}" for name, count in sorted(by_table.items()))
        _LOGGER.info(
            "Catalog pull retries expired (%s); not an operator OrphanRows alarm",
            summary,
        )
        return len(expired)

    def drop_orphans_older_than(self, age_minutes: int) -> int:
        """Operator-triggered drop of pending orphan rows older than age_minutes."""
        self._ensure_pending_loaded()
        age_s = max(60.0, float(age_minutes) * 60.0)
        now = time.monotonic()
        expired = [
            item
            for item in self._pending_orphans.items()
            if (now - item[1].first_seen_mono) >= age_s
        ]
        if not expired:
            self._flush_pending_to_disk()
            return 0
        for pending_key, pending in expired:
            _LOGGER.warning(
                "Operator dropped pending %s row %s age>=%ss",
                pending.table,
                pending.key,
                int(age_s),
            )
            self._pending_orphans.pop(pending_key, None)
        self._flush_pending_to_disk()
        return len(expired)

    def _should_full_scan(self) -> bool:
        if self._last_remote_version_ms is None or self._last_full_scan_mono <= 0.0:
            return True
        return (time.monotonic() - self._last_full_scan_mono) >= _FULL_SCAN_INTERVAL_S

    def _scope_identity(self) -> tuple[str, str] | None:
        try:
            from ..node_scope import get_node_scope

            scope = get_node_scope()
        except Exception:
            return None
        if not getattr(scope, "enabled", False) or not getattr(scope, "is_valid", False):
            return None
        area = str(getattr(scope, "area", "") or "").strip()
        node_id = str(getattr(scope, "node_id", "") or "").strip()
        if not area or not node_id:
            return None
        return area, node_id

    def _row_in_node_scope(self, table: str, row: dict | None) -> bool:
        """True if this edge may pull/push the row. Lookup tables are always in scope."""
        if not row:
            return False
        if table not in PARTITIONED_TABLES:
            return True
        identity = self._scope_identity()
        if identity is None:
            return True
        area, node_id = identity
        row_area = str(row.get("area") or "").strip()
        row_owner = str(row.get("owner_node") or "").strip()
        row_name = str(row.get("name") or "").strip()
        if table == "opcua":
            return (not row_owner) or row_owner == node_id
        if table == "opcuaserver":
            # Address-space rows are named "{area}_…". Never treat another
            # line's nodes as this edge's catalog.
            prefix = f"{area}_"
            return row_name.startswith(prefix) or row_area == area
        if table == "tagsmachines":
            # No area column. Scope is decided from parent tag/machine in
            # _filter_child_rows / _tagsmachines_cross_area (never "always True").
            return True
        if table == "machines":
            return row_area == area
        if row_area == area or row_owner == node_id:
            return True
        if not row_area and not row_owner:
            return True
        return False

    def _build_area_filter(self, table: str) -> tuple[str, tuple] | None:
        """SQL WHERE for this edge. Lookup tables are unfiltered (shared)."""
        if table in LOOKUP_TABLES or table in ("nodes", "linearreferencinggeospatial"):
            return None
        identity = self._scope_identity()
        if identity is None:
            return None
        area, node_id = identity
        if table == "opcua":
            return ("(owner_node IS NULL OR owner_node = %s)", (node_id,))
        if table == "tags":
            return (
                "(area = %s OR owner_node = %s OR ((area IS NULL OR area = '') AND (owner_node IS NULL OR owner_node = '')))",
                (area, node_id),
            )
        if table == "machines":
            return ("area = %s", (area,))
        if table == "alarms":
            return ("(area IS NULL OR area = %s)", (area,))
        if table == "opcuaserver":
            return ("name LIKE %s", (f"{area}_%",))
        if table == "tagsmachines":
            return (
                "tag_id IN (SELECT id FROM tags WHERE area = %s OR owner_node = %s) "
                "OR machine_id IN (SELECT id FROM machines WHERE area = %s)",
                (area, node_id, area),
            )
        return None

    def _filter_scope_rows(self, table: str, rows: list[dict]) -> list[dict]:
        if table not in PARTITIONED_TABLES:
            return list(rows or [])
        return [row for row in (rows or []) if self._row_in_node_scope(table, row)]

    def _lookup_bind_parents(
        self,
        row: dict,
        *,
        local_index: dict,
        remote_index: dict,
    ) -> tuple[dict | None, dict | None]:
        tag = lookup_fk_parent(
            "tagsmachines",
            row,
            "tag",
            local_index=local_index,
            remote_index=remote_index,
        )
        machine = lookup_fk_parent(
            "tagsmachines",
            row,
            "machine",
            local_index=local_index,
            remote_index=remote_index,
        )
        return tag, machine

    def _tagsmachines_pull_decision(
        self,
        row: dict,
        local_index: dict,
        remote_index: dict,
    ) -> str:
        """keep | foreign | cross_area. Never 'deferred' for partition violations."""
        tag, machine = self._lookup_bind_parents(
            row, local_index=local_index, remote_index=remote_index
        )
        tag_ours = bool(tag) and self._row_in_node_scope("tags", tag)
        machine_ours = bool(machine) and self._row_in_node_scope("machines", machine)
        if tag and machine:
            if not areas_compatible(tag.get("area"), machine.get("area")):
                return "cross_area"
            if tag_ours and machine_ours:
                return "keep"
            return "foreign"
        if tag_ours or machine_ours:
            return "cross_area"
        return "foreign"

    def _filter_child_rows(
        self,
        table: str,
        rows: list[dict],
        *,
        local_index: dict,
        remote_index: dict,
    ) -> list[dict]:
        """Drop alarms/tagsmachines whose tag/machine is not this edge's catalog."""
        if table not in CHILD_TABLES:
            return list(rows or [])
        if table == "tagsmachines":
            return self._filter_tagsmachines_rows(
                rows, local_index=local_index, remote_index=remote_index
            )
        kept: list[dict] = []
        for row in rows or []:
            if parent_fk_known(table, row, local_index=local_index, remote_index=remote_index):
                kept.append(row)
            else:
                _LOGGER.debug(
                    "Omitting %s row %s: parent tag/machine not in this edge catalog",
                    table,
                    identity_key(table, row) or row.get("id"),
                )
        return kept

    def _filter_tagsmachines_rows(
        self,
        rows: list[dict],
        *,
        local_index: dict,
        remote_index: dict,
    ) -> list[dict]:
        kept: list[dict] = []
        invalid: list[dict] = []
        for row in rows or []:
            decision = self._tagsmachines_pull_decision(row, local_index, remote_index)
            if decision == "keep":
                kept.append(row)
            elif decision == "cross_area":
                invalid.append(row)
            else:
                _LOGGER.debug(
                    "Omitting tagsmachines row %s: parent tag/machine not in this edge catalog",
                    identity_key("tagsmachines", row) or row.get("id"),
                )
        if invalid:
            self._cycle_cross_area_count += len(invalid)
            _LOGGER.warning(
                "Ignoring %s cross-area tagsmachines rows. "
                "Manual correction required in remote.",
                len(invalid),
            )
        return kept

    def _load_remote_rows(self, table: str, *, full_scan: bool, since_ms: int) -> list[dict]:
        """Lookup + parent tables: full read. Partitioned: this area only."""
        where = None
        params = None
        scoped = self._build_area_filter(table)
        if scoped:
            where, params = scoped
        if table in LOOKUP_TABLES or table in PARENT_TABLES:
            rows = self._remote.read_all(table, where=where, params=params)
            # Lookups may be empty on a filtered replica; parents must never
            # fall back to an unscoped read_all (that leaked foreign machines).
            if not rows and where and table in LOOKUP_TABLES:
                rows = self._remote.read_all(table)
            return self._filter_scope_rows(table, rows)
        if full_scan:
            rows = self._remote.read_all(table, where=where, params=params)
            if not rows and where and table in LOOKUP_TABLES:
                rows = self._remote.read_all(table)
        else:
            rows = self._fetch_modified_rows(table, since_ms)
        return self._filter_scope_rows(table, rows)

    def _skip_pull_reason(
        self,
        table: str,
        remote_row: dict,
        payload: dict,
        local_index: dict,
        remote_index: dict,
    ) -> str | None:
        """None = upsert. 'foreign' = omit. 'deferred' = retry next cycle."""
        if table == "tagsmachines":
            decision = self._tagsmachines_pull_decision(
                remote_row, local_index, remote_index
            )
            if decision != "keep":
                return "foreign"
        if _pull_has_required_fks(table, payload):
            return None
        if table in CHILD_TABLES:
            if parent_fk_known(
                table, remote_row, local_index=local_index, remote_index=remote_index
            ):
                return "deferred"
            return "foreign"
        return "deferred"

    def _fetch_modified_rows(self, table_name: str, since: int) -> list[dict]:
        """Return only rows modified since the catalog_versions / updated_at watermark."""
        return self._remote.read_changed(table_name, int(since or 0))

    def _sync_table(
        self,
        table: str,
        *,
        local_rows: list,
        remote_rows: list,
        local_index: dict,
        remote_index: dict,
        partial_remote: bool = False,
        pending_pks: set | None = None,
    ) -> tuple[int, int, int, int]:
        remote_by_id = index_by_identity(table, remote_rows)
        local_by_id = index_by_identity(table, local_rows)
        # Keep shared indexes aligned for FK remap across tables in this cycle.
        local_index[table] = local_by_id
        remote_index[table] = remote_by_id
        pushed = pulled = conflicts = errors = 0
        edge = edge_node_id()
        processed = 0

        keys = set()
        if partial_remote:
            for row in remote_rows:
                key = identity_key(table, row)
                if key:
                    keys.add(key)
            pending = pending_pks or set()
            for row in local_rows:
                if not self._row_in_node_scope(table, row):
                    continue
                pk = str(row.get("_pk") or row.get("id") or "")
                if pk in pending:
                    key = identity_key(table, row)
                    if key:
                        keys.add(key)
        else:
            for row in local_rows:
                if not self._row_in_node_scope(table, row):
                    continue
                key = identity_key(table, row)
                if key:
                    keys.add(key)
            for row in remote_rows:
                key = identity_key(table, row)
                if key:
                    keys.add(key)

        # One SQLite transaction per row: an IntegrityError must not roll back
        # sibling rows of the same table (Bulkhead / CA-ISOLATION-02).
        for key in keys:
            if processed >= _BATCH:
                break
            local_row = local_by_id.get(key)
            remote_row = remote_by_id.get(key)
            if remote_row is not None and not self._row_in_node_scope(table, remote_row):
                processed += 1
                continue
            if table in PUSH_ONLY_TABLES and local_row is None and remote_row is not None:
                processed += 1
                continue
            local_pk = str((local_row or {}).get("_pk") or (local_row or {}).get("id") or "")
            remote_pk = str((remote_row or {}).get("_pk") or (remote_row or {}).get("id") or "")
            try:
                with self._local.atomic():
                    p, u, c = self._sync_one_key(
                        table,
                        key=key,
                        local_row=local_row,
                        remote_row=remote_row,
                        local_pk=local_pk,
                        remote_pk=remote_pk,
                        local_by_id=local_by_id,
                        remote_by_id=remote_by_id,
                        local_index=local_index,
                        remote_index=remote_index,
                        edge=edge,
                    )
                pushed += p
                pulled += u
                conflicts += c
                processed += 1
            except Exception as exc:
                processed += 1
                if _is_integrity_error(exc):
                    self._cycle_integrity_errors += 1
                    _LOGGER.warning(
                        "IntegrityError syncing %s row %s: %s",
                        table,
                        key,
                        exc,
                    )
                    continue
                if _is_transient_connection_error(exc):
                    self._transient_remote_errors += 1
                    if table in PUSH_ONLY_TABLES:
                        self._cycle_backup_skips += 1
                    self._recycle_replica_handle()
                    log = (
                        _LOGGER.warning
                        if self._transient_remote_errors <= 1
                        else _LOGGER.debug
                    )
                    log(
                        "catalog sync row skipped (remote connection) table=%s key=%s",
                        table,
                        key,
                    )
                    break
                errors += 1
                _LOGGER.exception("catalog sync row failed table=%s key=%s", table, key)
        return pushed, pulled, conflicts, errors

    def _sync_one_key(
        self,
        table: str,
        *,
        key: str,
        local_row,
        remote_row,
        local_pk: str,
        remote_pk: str,
        local_by_id: dict,
        remote_by_id: dict,
        local_index: dict,
        remote_index: dict,
        edge: str,
    ) -> tuple[int, int, int]:
        if table in PUSH_ONLY_TABLES:
            if local_row is None:
                return 0, 0, 0
            # Option 2: backup push only. Remote must never win LWW / hydrate.
            remote_row = None
            remote_pk = ""
        if local_row is None and remote_row is not None:
            payload = prepare_pull_row(
                table,
                remote_row,
                local_index=local_index,
                remote_index=remote_index,
            )
            reason = self._skip_pull_reason(
                table, remote_row, payload, local_index, remote_index
            )
            if reason == "foreign":
                return 0, 0, 0
            if reason == "deferred":
                self._note_deferred_row(table, key, direction="pull")
                self._note_deferred_orphan(table, key, remote_row)
                return 0, 0, 0
            new_pk = self._local.upsert(
                table,
                payload,
                node_id="central",
                version=now_ms(),
            )
            payload["_pk"] = str(new_pk)
            local_by_id[key] = payload
            local_index[table] = local_by_id
            self._forget_pending_orphan(table, key)
            return 0, 1, 0
        if remote_row is None and local_row is not None:
            if table == "tagsmachines":
                decision = self._tagsmachines_pull_decision(
                    local_row, local_index, remote_index
                )
                if decision != "keep":
                    return 0, 0, 0
            local_ver = get_local(table, local_pk) if local_pk else None
            if local_ver is None or local_ver.node_id == edge:
                payload = prepare_push_row(
                    table,
                    local_row,
                    local_index=local_index,
                    remote_index=remote_index,
                )
                if table in CHILD_TABLES and not _pull_has_required_fks(table, payload):
                    self._note_deferred_row(table, key, direction="push")
                    return 0, 0, 0
                new_pk = self._remote.upsert(
                    table,
                    payload,
                    node_id=edge,
                    version=int(local_ver.version) if local_ver else now_ms(),
                )
                touch_local(
                    table,
                    local_pk or str(new_pk),
                    version=int(local_ver.version) if local_ver else now_ms(),
                    node_id=edge,
                    resolved=True,
                )
                touch_remote(
                    table,
                    str(new_pk),
                    version=int(local_ver.version) if local_ver else now_ms(),
                    node_id=edge,
                    resolved=True,
                )
                payload["_pk"] = str(new_pk)
                remote_by_id[key] = payload
                remote_index[table] = remote_by_id
                return 1, 0, 0
            return 0, 0, 0

        if contents_equal(
            table,
            local_row,
            remote_row,
            left_index=local_index,
            right_index=remote_index,
        ):
            return 0, 0, 0

        local_ver = get_local(table, local_pk) if local_pk else None
        remote_ver = get_remote(table, remote_pk) if remote_pk else None
        local_stamp = (
            VersionStamp(int(local_ver.version), local_ver.node_id) if local_ver is not None else None
        )
        remote_stamp = (
            VersionStamp(int(remote_ver.version), remote_ver.node_id) if remote_ver is not None else None
        )
        winner = resolve(
            local_stamp,
            remote_stamp,
            local_dirty=bool(
                local_ver is not None
                and not bool(getattr(local_ver, "conflict_resolved", True))
                and str(getattr(local_ver, "node_id", "") or "") == edge
            ),
        )
        if winner == "local" and local_row is not None:
            payload = prepare_push_row(
                table,
                local_row,
                local_index=local_index,
                remote_index=remote_index,
            )
            new_pk = self._remote.upsert(
                table,
                payload,
                node_id=edge,
                version=int(local_stamp.version) if local_stamp else now_ms(),
            )
            touch_local(
                table,
                local_pk,
                version=int(local_stamp.version) if local_stamp else now_ms(),
                node_id=edge,
                resolved=True,
            )
            touch_remote(
                table,
                str(new_pk),
                version=int(local_stamp.version) if local_stamp else now_ms(),
                node_id=edge,
                resolved=True,
            )
            payload["_pk"] = str(new_pk)
            remote_by_id[key] = payload
            remote_index[table] = remote_by_id
            if local_stamp and remote_stamp:
                self._note_conflict(table, key, local_stamp, remote_stamp, "local")
            else:
                self._note_conflict(
                    table,
                    key,
                    local_stamp or VersionStamp(now_ms(), edge),
                    remote_stamp or VersionStamp(0, "central"),
                    "local",
                )
            return 1, 0, 1
        if remote_row is not None:
            ver = int(remote_stamp.version) if remote_stamp else now_ms()
            node = remote_stamp.node_id if remote_stamp else "central"
            payload = prepare_pull_row(
                table,
                remote_row,
                local_index=local_index,
                remote_index=remote_index,
            )
            reason = self._skip_pull_reason(
                table, remote_row, payload, local_index, remote_index
            )
            if reason == "foreign":
                return 0, 0, 0
            if reason == "deferred":
                self._note_deferred_row(table, key, direction="pull")
                self._note_deferred_orphan(table, key, remote_row)
                return 0, 0, 0
            new_pk = self._local.upsert(table, payload, node_id=node, version=ver)
            touch_local(table, str(new_pk), version=ver, node_id=node, resolved=True)
            payload["_pk"] = str(new_pk)
            local_by_id[key] = payload
            local_index[table] = local_by_id
            self._forget_pending_orphan(table, key)
            if local_stamp and remote_stamp:
                self._note_conflict(table, key, local_stamp, remote_stamp, "remote")
            else:
                self._note_conflict(
                    table,
                    key,
                    local_stamp or VersionStamp(0, edge),
                    remote_stamp or VersionStamp(ver, node),
                    "remote",
                )
            return 0, 1, 1
        return 0, 0, 0


_worker: CatalogReplicatorWorker | None = None


def get_catalog_replicator() -> CatalogReplicatorWorker | None:
    return _worker


def start_catalog_replicator(sync_interval: float = _ONLINE_INTERVAL_S) -> CatalogReplicatorWorker:
    global _worker
    if _worker is not None and _worker.is_alive():
        return _worker
    _worker = CatalogReplicatorWorker(sync_interval=sync_interval)
    _worker.start()
    return _worker


def stop_catalog_replicator() -> None:
    global _worker
    if _worker is not None:
        old = _worker
        old.stop()
        try:
            old.join(timeout=5.0)
        except Exception:
            pass
        _worker = None
    reset_replica_database()
