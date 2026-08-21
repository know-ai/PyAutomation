# -*- coding: utf-8 -*-
"""Bidirectional catalog replicator — OS thread, never on the acquisition hot path.

Design constraints (HMI performance):
- Default period 120 s while the historian is healthy (30 s only while catching up).
- Full-table remote reads use a dedicated DB handle (``replica_db``), not the API proxy.
- Each cycle reads each table once; indexes are updated in-memory after upserts.
- Success is logged at DEBUG; Events rows only for failures / real conflicts / large deltas.
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
_ONLINE_INTERVAL_S = 120.0
_CATCHUP_INTERVAL_S = 30.0
_EVENT_DELTA_THRESHOLD = 50
_SUCCESS_EVENT_EVERY = 10  # emit summary Event at most every N successful quiet cycles
_CATALOG_EVENT_COOLDOWN_S = 120.0  # identical catalog audit fingerprints share one Events row
_MAX_CONFLICT_SAMPLES = 5


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
        self.sync_interval = max(30.0, float(sync_interval))
        self._catchup_interval = max(5.0, float(catchup_interval))
        self._startup_grace_s = max(0.0, float(startup_grace_s))
        self._startup_mono = time.monotonic()
        self._reconnect_grace_until = 0.0
        self._catch_up = False
        self._quiet_successes = 0
        self._local = LocalCatalogProvider()
        self._remote = RemoteCatalogProvider(prefer_replica_reads=True)
        self._failures = 0
        self._local_only_since: float | None = None
        self._unresolved = 0
        self._cycle_conflicts: list[tuple[str, str, str]] = []
        self._cycle_conflict_counts: dict[str, int] = {}

    def arm_reconnect_grace(self, seconds: float = 5.0) -> None:
        """Hold sync briefly after reconnect so the Peewee socket can settle."""
        self._reconnect_grace_until = time.monotonic() + max(0.0, float(seconds))
        self._catch_up = True
        reset_replica_database()

    def _wait_interval(self) -> float:
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
                set_sync_failed(self._failures >= _FAIL_THRESHOLD)
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
        source = refresh_catalog_source()
        update_metrics(source=source, pending_rows=pending_count(), conflict_count=self._unresolved)
        if source != "remote":
            if self._local_only_since is None:
                self._local_only_since = now
            elapsed = now - self._local_only_since
            set_local_only(elapsed >= _LOCAL_ONLY_S)
            update_metrics(local_only_since_utc=datetime.now(timezone.utc).isoformat())
            self._catch_up = True
            return {"skipped": True, "reason": "remote-down"}
        if not self._historian_ready():
            return {"skipped": True, "reason": "historian-not-ready"}
        self._local_only_since = None
        set_local_only(False)
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
            except Exception:
                row_errors += 1
                _LOGGER.exception("catalog sync table failed table=%s", table)

        self._unresolved = 0
        if row_errors:
            self._failures += 1
            set_sync_failed(self._failures >= _FAIL_THRESHOLD)
            update_metrics(consecutive_failures=self._failures)
            self._catch_up = True
        else:
            self._failures = 0
            set_sync_failed(False)
            update_metrics(consecutive_failures=0)
            if pending_count() == 0 and pushed + pulled < _EVENT_DELTA_THRESHOLD:
                self._catch_up = False
        set_conflict(False)
        update_metrics(
            source="remote",
            last_success_utc=datetime.now(timezone.utc).isoformat(),
            pending_rows=pending_count(),
            conflict_count=auto_resolved,
        )
        self._emit_divergence_summary(auto_resolved=auto_resolved)
        self._emit_cycle_summary(
            pushed=pushed,
            pulled=pulled,
            auto_resolved=auto_resolved,
            row_errors=row_errors,
            force=force,
        )
        close_replica_thread_connection()
        return {
            "pushed": pushed,
            "pulled": pulled,
            "conflicts": auto_resolved,
            "errors": row_errors,
        }

    def _emit_cycle_summary(
        self,
        *,
        pushed: int,
        pulled: int,
        auto_resolved: int,
        row_errors: int,
        force: bool,
    ) -> None:
        delta = pushed + pulled
        noisy = row_errors > 0 or auto_resolved > 0 or delta >= _EVENT_DELTA_THRESHOLD or force
        summary = f"{pushed} pushed, {pulled} pulled, {auto_resolved} auto-merged, {row_errors} errors"
        if not noisy:
            self._quiet_successes += 1
            _LOGGER.debug("Catalog sync completed (%s)", summary)
            if self._quiet_successes % _SUCCESS_EVENT_EVERY != 0:
                return
        else:
            self._quiet_successes = 0
        # Idempotent across catch-up cycles that report the same outcome.
        if not force and not cooldown_allows(f"catalog:sync:{summary}", _CATALOG_EVENT_COOLDOWN_S):
            _LOGGER.debug("Catalog sync completed event debounced (%s)", summary)
            return
        try:
            persist_system_event(
                message="Catalog sync completed",
                description=clip(summary, 256),
                classification="System",
                priority=2,
                criticity=2 if row_errors == 0 else 4,
            )
        except Exception:
            _LOGGER.debug("catalog sync event skipped", exc_info=True)

    def _note_conflict(
        self,
        table: str,
        key: str,
        local: VersionStamp,
        remote: VersionStamp,
        winner: str,
    ) -> None:
        """Accumulate counts + a few samples; never write Events here."""
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

    def _emit_divergence_summary(self, *, auto_resolved: int) -> None:
        """At most one divergence Events row per cycle, debounced by fingerprint."""
        if auto_resolved <= 0:
            return
        by_table = dict(self._cycle_conflict_counts)
        table_bits = ",".join(f"{name}×{count}" for name, count in sorted(by_table.items())) or "mixed"
        samples = "; ".join(f"{t}:{k}({d})" for t, k, d in self._cycle_conflicts[:_MAX_CONFLICT_SAMPLES])
        fingerprint = f"catalog:divergence:{auto_resolved}:{table_bits}"
        if not cooldown_allows(fingerprint, _CATALOG_EVENT_COOLDOWN_S):
            _LOGGER.debug(
                "Catalog divergence event debounced count=%s tables=%s",
                auto_resolved,
                table_bits,
            )
            return
        description = clip(
            f"{auto_resolved} rows auto-merged ({table_bits})"
            + (f"; e.g. {samples}" if samples else ""),
            256,
        )
        try:
            persist_system_event(
                message="Catalog divergence auto-merged",
                description=description,
                classification="System",
                priority=2,
                criticity=2,
            )
        except Exception:
            _LOGGER.debug("catalog divergence summary skipped", exc_info=True)
        _LOGGER.info("Catalog divergence auto-merged: %s", description)

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
                    if local_stamp and remote_stamp and local_stamp.version != remote_stamp.version:
                        conflicts += 1
                        self._note_conflict(table, key, local_stamp, remote_stamp, "local")
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
                        if local_stamp and remote_stamp and local_stamp.version != remote_stamp.version:
                            conflicts += 1
                            self._note_conflict(table, key, local_stamp, remote_stamp, "remote")
                processed += 1
            except Exception:
                errors += 1
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
