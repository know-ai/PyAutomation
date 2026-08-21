# -*- coding: utf-8 -*-
"""Bidirectional catalog replicator — OS thread, never on the acquisition hot path."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from ..utils.system_event_audit import clip, persist_system_event
from ..workers.worker import BaseWorker
from .alarms import set_conflict, set_local_only, set_sync_failed
from .conflict import VersionStamp, resolve
from .identity import (
    build_table_indexes,
    identity_key,
    index_by_identity,
    prepare_pull_row,
    prepare_push_row,
)
from .local_provider import LocalCatalogProvider
from .metrics import update as update_metrics
from .provider import catalog_source, refresh_catalog_source
from .remote_provider import RemoteCatalogProvider
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


class CatalogReplicatorWorker(BaseWorker):
    def __init__(self, sync_interval: float = 30.0, startup_grace_s: float = 15.0):
        super().__init__()
        self.name = "CatalogReplicatorWorker"
        self.daemon = True
        self.sync_interval = max(5.0, float(sync_interval))
        self._startup_grace_s = max(0.0, float(startup_grace_s))
        self._startup_mono = time.monotonic()
        self._local = LocalCatalogProvider()
        self._remote = RemoteCatalogProvider()
        self._failures = 0
        self._local_only_since: float | None = None
        self._unresolved = 0

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.cycle()
            except Exception:
                _LOGGER.exception("catalog replicator cycle failed")
                self._failures += 1
                set_sync_failed(self._failures >= _FAIL_THRESHOLD)
                update_metrics(consecutive_failures=self._failures)
            self.stop_event.wait(self.sync_interval)

    def cycle(self, *, force: bool = False) -> dict:
        if (
            not force
            and self._startup_grace_s > 0
            and (time.monotonic() - self._startup_mono) < self._startup_grace_s
        ):
            return {"skipped": True, "reason": "startup-grace"}
        source = refresh_catalog_source()
        update_metrics(source=source, pending_rows=pending_count(), conflict_count=self._unresolved)
        if source != "remote":
            now = time.monotonic()
            if self._local_only_since is None:
                self._local_only_since = now
            elapsed = now - self._local_only_since
            set_local_only(elapsed >= _LOCAL_ONLY_S)
            update_metrics(local_only_since_utc=datetime.now(timezone.utc).isoformat())
            return {"skipped": True, "reason": "remote-down"}
        self._local_only_since = None
        set_local_only(False)
        # Parent tables must be indexed before children so FK remap works mid-cycle.
        local_index = build_table_indexes(self._local.read_all, REPLICATED_TABLES)
        remote_index = build_table_indexes(self._remote.read_all, REPLICATED_TABLES)
        pushed = pulled = auto_resolved = row_errors = 0
        # Auto-resolved version divergences (newest wins) are audited as events,
        # not sticky ALM.CATALOG.Conflict. That alarm is reserved for unresolved
        # cases — today resolve() always picks a side, so the sticky alarm only
        # stays meaningful if we later add a manual-merge path. Count auto-merges
        # separately for metrics/events without latching the operator alarm.
        for table in REPLICATED_TABLES:
            try:
                p, u, c, e = self._sync_table(
                    table,
                    local_index=local_index,
                    remote_index=remote_index,
                )
                pushed += p
                pulled += u
                auto_resolved += c
                row_errors += e
                # Refresh indexes after each table so child FK remap sees new parents.
                local_index[table] = index_by_identity(table, self._local.read_all(table))
                remote_index[table] = index_by_identity(table, self._remote.read_all(table))
            except Exception:
                row_errors += 1
                _LOGGER.exception("catalog sync table failed table=%s", table)
        # No unresolved conflicts with current newest-wins policy.
        self._unresolved = 0
        if row_errors:
            self._failures += 1
            set_sync_failed(self._failures >= _FAIL_THRESHOLD)
            update_metrics(consecutive_failures=self._failures)
        else:
            self._failures = 0
            set_sync_failed(False)
            update_metrics(consecutive_failures=0)
        set_conflict(False)
        update_metrics(
            source="remote",
            last_success_utc=datetime.now(timezone.utc).isoformat(),
            pending_rows=pending_count(),
            conflict_count=auto_resolved,
        )
        try:
            persist_system_event(
                message="Catalog sync completed",
                description=clip(
                    f"{pushed} pushed, {pulled} pulled, {auto_resolved} auto-merged, {row_errors} errors",
                    256,
                ),
                classification="System",
                priority=2,
                criticity=2 if row_errors == 0 else 4,
            )
        except Exception:
            _LOGGER.debug("catalog sync event skipped", exc_info=True)
        return {
            "pushed": pushed,
            "pulled": pulled,
            "conflicts": auto_resolved,
            "errors": row_errors,
        }

    def _sync_table(
        self,
        table: str,
        *,
        local_index: dict,
        remote_index: dict,
    ) -> tuple[int, int, int, int]:
        remote_rows = self._remote.read_all(table)
        local_rows = self._local.read_all(table)
        remote_by_id = index_by_identity(table, remote_rows)
        local_by_id = index_by_identity(table, local_rows)
        pushed = pulled = conflicts = errors = 0
        edge = edge_node_id()
        processed = 0

        # Union of natural keys (ignore raw pk-only aliases for matching).
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
                    pulled += 1
                    processed += 1
                    continue
                if remote_row is None and local_row is not None:
                    # Push edge-authored rows even if version sidecar is missing.
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
                    pushed += 1
                    if local_stamp and remote_stamp and local_stamp.version != remote_stamp.version:
                        conflicts += 1
                        self._emit_conflict(table, key, local_stamp, remote_stamp, "local")
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
                        pulled += 1
                        if local_stamp and remote_stamp and local_stamp.version != remote_stamp.version:
                            conflicts += 1
                            self._emit_conflict(table, key, local_stamp, remote_stamp, "remote")
                processed += 1
            except Exception:
                errors += 1
                _LOGGER.exception("catalog sync row failed table=%s key=%s", table, key)
                processed += 1
        return pushed, pulled, conflicts, errors

    def _emit_conflict(self, table: str, pk: str, local: VersionStamp, remote: VersionStamp, winner: str) -> None:
        """Audit an auto-merged version divergence (informational, not sticky)."""
        try:
            persist_system_event(
                message="Catalog divergence auto-merged",
                description=clip(
                    f"table={table} row={pk} local={local.version} remote={remote.version} winner={winner}",
                    256,
                ),
                classification="System",
                priority=2,
                criticity=2,
            )
        except Exception:
            _LOGGER.debug("catalog conflict event skipped", exc_info=True)


_worker: CatalogReplicatorWorker | None = None


def get_catalog_replicator() -> CatalogReplicatorWorker | None:
    return _worker


def start_catalog_replicator(sync_interval: float = 30.0) -> CatalogReplicatorWorker:
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
