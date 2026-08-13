# -*- coding: utf-8 -*-
"""PersistenceOrchestrator — IPersistenceGateway implementation.

Acquisition (CVT, alarms, events) depends on this abstraction, never on
sqlite3 or psycopg2.
"""
from __future__ import annotations

import threading
from typing import Sequence

from .config import SafConfig
from .contracts import IPersistable, IRemoteDB
from .health import SafHealthProbe
from .idempotent_insert import IdempotentBatchInserter
from .journal import JournalWriter
from .remote import PeeweeRemoteDB
from .replicator import RemoteReplicator

_lock = threading.Lock()
_gateway: PersistenceOrchestrator | None = None


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
        self.journal.start()

    def enqueue(self, persistable: IPersistable) -> int:
        return self.journal.append(persistable)

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

    def snapshot(self) -> dict:
        return dict(self.health.snapshot())

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
