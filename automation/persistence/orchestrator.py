# -*- coding: utf-8 -*-
"""PersistenceOrchestrator — IPersistenceGateway implementation.

Acquisition (CVT, alarms, events) depends on this abstraction, never on
sqlite3 or psycopg2.
"""
from __future__ import annotations

import threading
import logging
from typing import Sequence

from .config import SafConfig
from .contracts import IPersistable, IRemoteDB
from .cycle_dedupe import CycleSampleCache
from .health import SafHealthProbe
from .idempotent_insert import IdempotentBatchInserter
from .journal import JournalWriter
from .remote import PeeweeRemoteDB
from .replicator import RemoteReplicator

_lock = threading.Lock()
_gateway: PersistenceOrchestrator | None = None


def _scope_owns_persistable(persistable: IPersistable) -> bool:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False):
        return False
    payload = persistable.payload()
    try:
        owner_node = payload.get("owner_node")
        area = payload.get("area")
        owns_area = getattr(scope, "owns_area", None)
        if callable(owns_area):
            area_owned = bool(owns_area(area))
        elif area is None or str(area).strip() in ("", "System"):
            area_owned = True
        else:
            area_owned = area == getattr(scope, "area", None)
        return bool(area_owned and scope.owns_node(owner_node))
    except Exception:
        return False


class PersistenceOrchestrator:
    def __init__(
        self,
        config: SafConfig | None = None,
        remote: IRemoteDB | None = None,
        tag_inserter: IdempotentBatchInserter | None = None,
    ):
        self.config = config or SafConfig()
        self.journal = JournalWriter(self.config)
        inserter = tag_inserter or IdempotentBatchInserter()
        self.remote = remote if remote is not None else PeeweeRemoteDB(tag_inserter=inserter)
        self.replicator = RemoteReplicator(self.journal, self.remote, self.config)
        self.health = SafHealthProbe(self.journal, self.replicator)
        self.cycle_cache = CycleSampleCache()
        self._kick_running = False
        self.journal.set_force_flush_hook(self._kick_replicate)
        self.journal.start()

    def _kick_replicate(self) -> None:
        """Non-blocking remote drain after the SAF ring spills to SQLite."""
        if self._kick_running:
            return
        self._kick_running = True

        def _run() -> None:
            try:
                self.replicate_once()
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "SAF force flush replicate failed", exc_info=True
                )
            finally:
                self._kick_running = False

        threading.Thread(target=_run, name="SafForceFlush", daemon=True).start()

    def enqueue(self, persistable: IPersistable) -> int:
        if not _scope_owns_persistable(persistable):
            logging.getLogger("pyautomation").error(
                "SAF rejected foreign record domain=%s entity=%s area=%s owner_node=%s",
                persistable.domain(),
                persistable.entity_id(),
                persistable.payload().get("area"),
                persistable.payload().get("owner_node"),
            )
            return 0
        if self.cycle_cache.should_drop(persistable):
            return 0
        return self.journal.append(persistable)

    def enqueue_many(self, persistables: Sequence[IPersistable]) -> list[int]:
        owned: list[IPersistable] = []
        for persistable in persistables:
            if not _scope_owns_persistable(persistable):
                logging.getLogger("pyautomation").error(
                    "SAF rejected foreign record domain=%s entity=%s area=%s owner_node=%s",
                    persistable.domain(),
                    persistable.entity_id(),
                    persistable.payload().get("area"),
                    persistable.payload().get("owner_node"),
                )
                continue
            if self.cycle_cache.should_drop(persistable):
                continue
            owned.append(persistable)
        if not owned:
            return []
        return self.journal.append_committed_many(owned)

    def mark_sent(self, journal_ids: Sequence[int]) -> None:
        self.journal.mark_sent(journal_ids)

    def mark_replicating(self, journal_ids: Sequence[int]) -> None:
        self.journal.mark_replicating(journal_ids)

    def mark_pending(self, journal_ids: Sequence[int], error: str = "") -> None:
        self.journal.mark_pending(journal_ids, error=error)

    def pending_count(self) -> int:
        return self.journal.pending_count()

    def flush_sync(self) -> None:
        self.journal.flush_sync()

    def replicate_once(self) -> int:
        return self.replicator.flush()

    def drop_unsent(self, *, confirm: bool) -> int:
        return self.journal.drop_unsent(confirm=confirm)

    def snapshot(self) -> dict:
        snap = dict(self.health.snapshot())
        snap["SAF_CYCLE_DUPES_DROPPED"] = self.cycle_cache.dropped
        return snap

    def close(self) -> None:
        self.journal.stop()


def get_persistence_gateway(config: SafConfig | None = None) -> PersistenceOrchestrator:
    global _gateway
    if _gateway is not None:
        return _gateway
    with _lock:
        if _gateway is None:
            _gateway = PersistenceOrchestrator(config=config)
        return _gateway


def reset_persistence_gateway() -> None:
    global _gateway
    with _lock:
        if _gateway is not None:
            _gateway.close()
            _gateway = None
