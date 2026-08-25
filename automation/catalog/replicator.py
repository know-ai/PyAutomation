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
import time
from datetime import datetime, timezone

from ..utils.system_event_audit import clip, persist_system_event
from ..utils.audit_metrics import cooldown_allows
from ..workers.worker import BaseWorker
from .alarms import set_conflict, set_local_only, set_sync_failed
from .conflict import VersionStamp, resolve
from .content_hash import contents_equal
from .identity import (
    identity_key,
    index_by_identity,
    prepare_pull_row,
    prepare_push_row,
)
from .local_provider import LocalCatalogProvider
from .metrics import update as update_metrics
from .provider import refresh_catalog_source
from .remote_provider import RemoteCatalogProvider
from .replica_db import (
    close_replica_thread_connection,
    ensure_replica_database,
    reset_replica_database,
)
from .schema import REPLICATED_TABLES
from .versions import (
    edge_node_id,
    get_local,
    get_remote,
    now_ms,
    pending_count,
    touch_local,
    touch_remote,
)

_LOGGER = logging.getLogger("pyautomation")
_BATCH = 200
_FAIL_THRESHOLD = 3
_LOCAL_ONLY_S = 3600.0
_ONLINE_INTERVAL_S = 300.0
# User rows also invalidate via PG NOTIFY / Redis Pub/Sub (user_cache).
# This worker is disaster-recovery catch-up, not the <2s login path.
_CATCHUP_INTERVAL_S = 30.0
_EVENT_DELTA_THRESHOLD = 50
_EXCEPTION_EVENT_COOLDOWN_S = 300.0
_BACKOFF_INTERVALS_S = (30.0, 60.0, 120.0, 300.0)
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
        self._remote_outage_since: float | None = None

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

    def _wait_interval(self) -> float:
        if self._remote_available is False:
            return _BACKOFF_INTERVALS_S[self._backoff_step]
        if self._catch_up or pending_count() > 0:
            return self._catchup_interval
        return self.sync_interval

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.cycle()
            except Exception:
                _LOGGER.exception("catalog replicator cycle failed")
                self._failures += 1
                self._latch_sync_failed(self._failures >= _FAIL_THRESHOLD)
                update_metrics(consecutive_failures=self._failures)
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

        remote_available = self._is_remote_available()
        was_available = self._remote_available
        self._remote_available = remote_available
        self._transient_remote_errors = 0

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
            self._catch_up = True
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

        # One full scan per side per cycle (no per-table re-read).
        local_rows_by_table = {table: self._local.read_all(table) for table in REPLICATED_TABLES}
        remote_rows_by_table = {table: self._remote.read_all(table) for table in REPLICATED_TABLES}
        local_index = {
            table: index_by_identity(table, local_rows_by_table[table]) for table in REPLICATED_TABLES
        }
        remote_index = {
            table: index_by_identity(table, remote_rows_by_table[table]) for table in REPLICATED_TABLES
        }

        pushed = pulled = auto_resolved = row_errors = 0
        for table in REPLICATED_TABLES:
            try:
                p, u, c, e = self._sync_table(
                    table,
                    local_rows=local_rows_by_table[table],
                    remote_rows=remote_rows_by_table[table],
                    local_index=local_index,
                    remote_index=remote_index,
                )
                pushed += p
                pulled += u
                auto_resolved += c
                row_errors += e
            except Exception as exc:
                row_errors += 1
                if _is_transient_connection_error(exc):
                    self._transient_remote_errors += 1
                    _LOGGER.warning("catalog sync table skipped (remote connection) table=%s", table)
                else:
                    _LOGGER.exception("catalog sync table failed table=%s", table)

        self._unresolved = 0
        if self._transient_remote_errors:
            reset_replica_database()
            from .provider import set_catalog_source

            set_catalog_source("local")
            self._remote_available = False
            if self._remote_outage_since is None:
                self._remote_outage_since = time.monotonic()
            self._failures = 0
            self._latch_sync_failed(False)
            self._increment_backoff()
            self._catch_up = True
            _LOGGER.warning(
                "Catalog sync aborted after %s remote connection error(s); will retry with backoff",
                self._transient_remote_errors,
            )
            close_replica_thread_connection()
            return {
                "skipped": True,
                "reason": "remote-connection-lost",
                "errors": self._transient_remote_errors,
            }
        if row_errors:
            self._failures += 1
            latch = self._failures >= _FAIL_THRESHOLD
            self._latch_sync_failed(latch)
            update_metrics(consecutive_failures=self._failures)
            self._catch_up = True
        else:
            self._failures = 0
            self._latch_sync_failed(False)
            update_metrics(consecutive_failures=0)
            if pending_count() == 0 and pushed + pulled < _EVENT_DELTA_THRESHOLD:
                self._catch_up = False
        # Auto-merge always picks a side today — sticky Conflict alarm is for
        # future manual-merge paths only (kept cleared on successful cycles).
        set_conflict(False)
        self._sync_cycles += 1
        summary = f"{pushed} pushed, {pulled} pulled, {auto_resolved} auto-merged, {row_errors} errors"
        update_metrics(
            source="remote",
            last_success_utc=datetime.now(timezone.utc).isoformat(),
            pending_rows=pending_count(),
            conflict_count=auto_resolved,
            sync_cycles=self._sync_cycles,
            last_cycle_summary=summary,
            last_auto_merged=auto_resolved,
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
            "errors": row_errors,
        }

    def _latch_sync_failed(self, active: bool) -> None:
        """ISA alarm + edge-triggered operator Event on rising edge only."""
        if active and self._remote_outage_since is not None:
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

    def _sync_table(
        self,
        table: str,
        *,
        local_rows: list,
        remote_rows: list,
        local_index: dict,
        remote_index: dict,
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
        for row in local_rows:
            key = identity_key(table, row)
            if key:
                keys.add(key)
        for row in remote_rows:
            key = identity_key(table, row)
            if key:
                keys.add(key)

        for key in keys:
            if processed >= _BATCH:
                break
            local_row = local_by_id.get(key)
            remote_row = remote_by_id.get(key)
            local_pk = str((local_row or {}).get("_pk") or (local_row or {}).get("id") or "")
            remote_pk = str((remote_row or {}).get("_pk") or (remote_row or {}).get("id") or "")
            local_ver = get_local(table, local_pk) if local_pk else None
            remote_ver = get_remote(table, remote_pk) if remote_pk else None
            local_stamp = (
                VersionStamp(int(local_ver.version), local_ver.node_id) if local_ver is not None else None
            )
            remote_stamp = (
                VersionStamp(int(remote_ver.version), remote_ver.node_id) if remote_ver is not None else None
            )
            try:
                if local_row is None and remote_row is not None:
                    payload = prepare_pull_row(
                        table,
                        remote_row,
                        local_index=local_index,
                        remote_index=remote_index,
                    )
                    new_pk = self._local.upsert(
                        table,
                        payload,
                        node_id=getattr(remote_ver, "node_id", None) or "central",
                        version=getattr(remote_ver, "version", None) or now_ms(),
                    )
                    touch_remote(
                        table,
                        str(remote_pk or new_pk),
                        version=getattr(remote_ver, "version", None) or now_ms(),
                        node_id=getattr(remote_ver, "node_id", None) or "central",
                        resolved=True,
                    )
                    payload["_pk"] = str(new_pk)
                    local_by_id[key] = payload
                    local_index[table] = local_by_id
                    pulled += 1
                    processed += 1
                    continue
                if remote_row is None and local_row is not None:
                    if local_ver is None or local_ver.node_id == edge:
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
                        pushed += 1
                        processed += 1
                    continue

                # Both sides present: business content decides — not updated_at / version skew.
                if contents_equal(
                    table,
                    local_row,
                    remote_row,
                    left_index=local_index,
                    right_index=remote_index,
                ):
                    aligned = max(
                        int(local_stamp.version) if local_stamp else 0,
                        int(remote_stamp.version) if remote_stamp else 0,
                        1,
                    )
                    if local_pk:
                        touch_local(
                            table,
                            local_pk,
                            version=aligned,
                            node_id=(local_stamp.node_id if local_stamp else None)
                            or (remote_stamp.node_id if remote_stamp else None)
                            or edge,
                            resolved=True,
                        )
                    if remote_pk:
                        touch_remote(
                            table,
                            remote_pk,
                            version=aligned,
                            node_id=(remote_stamp.node_id if remote_stamp else None)
                            or (local_stamp.node_id if local_stamp else None)
                            or "central",
                            resolved=True,
                        )
                    processed += 1
                    continue

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
                    pushed += 1
                    conflicts += 1
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
                else:
                    if remote_row is not None:
                        ver = int(remote_stamp.version) if remote_stamp else now_ms()
                        node = remote_stamp.node_id if remote_stamp else "central"
                        payload = prepare_pull_row(
                            table,
                            remote_row,
                            local_index=local_index,
                            remote_index=remote_index,
                        )
                        new_pk = self._local.upsert(table, payload, node_id=node, version=ver)
                        touch_remote(table, remote_pk or str(new_pk), version=ver, node_id=node, resolved=True)
                        touch_local(table, str(new_pk), version=ver, node_id=node, resolved=True)
                        payload["_pk"] = str(new_pk)
                        local_by_id[key] = payload
                        local_index[table] = local_by_id
                        pulled += 1
                        conflicts += 1
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
                processed += 1
            except Exception as exc:
                errors += 1
                if _is_transient_connection_error(exc):
                    self._transient_remote_errors += 1
                    _LOGGER.warning(
                        "catalog sync row skipped (remote connection) table=%s key=%s",
                        table,
                        key,
                    )
                else:
                    _LOGGER.exception("catalog sync row failed table=%s key=%s", table, key)
                processed += 1
        return pushed, pulled, conflicts, errors


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
        _worker.stop()
        _worker = None
    reset_replica_database()
