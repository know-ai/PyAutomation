# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Mapping

from .journal import JournalWriter
from .replicator import RemoteReplicator


class SafHealthProbe:
    """Segregated observability contract (IHealthProbe)."""

    def __init__(self, journal: JournalWriter, replicator: RemoteReplicator | None = None):
        self.journal = journal
        self.replicator = replicator

    def snapshot(self) -> Mapping[str, Any]:
        pending = self.journal.pending_count()
        lag = self.journal.oldest_pending_age_s()
        dropped = self.journal.dropped_full
        disk = self.journal.disk_bytes()
        circuit = getattr(self.replicator, "circuit", None)
        healthy = pending == 0 or (dropped == 0 and not self.journal.backpressure)
        status = "ok"
        if dropped or self.journal.backpressure:
            status = "critical"
            healthy = False
        elif pending > 0:
            status = "degraded"
        return {
            "status": status,
            "healthy": healthy,
            "SAF_QUEUE_DEPTH": pending,
            "SAF_REPLICATION_LAG": round(lag, 3),
            "SAF_DROPPED_FULL": dropped,
            "SAF_DISK_BYTES": disk,
            "SAF_BACKPRESSURE": self.journal.backpressure,
            "SAF_CIRCUIT": getattr(circuit, "state", "unknown"),
            "SAF_LAST_ERROR": getattr(self.replicator, "last_error", "") or self.journal.last_error,
            "SAF_MAX_DISK_BYTES": self.journal.config.max_disk_bytes,
        }
