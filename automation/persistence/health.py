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
        regime = _regime(self.journal, pending)
        rate = int(getattr(self.journal.config, "replicate_rate_per_s", 10000) or 10000)
        eta = (float(pending) / float(rate)) if pending and rate else 0.0
        try:
            from .latency import ack_p95_ms
            from ..state_machine_timing import snapshot_timing_metrics

            ack_p95 = ack_p95_ms()
            tick_p95 = float(snapshot_timing_metrics().get("SAF_TICK_P95_MS") or 0.0)
        except Exception:
            ack_p95 = 0.0
            tick_p95 = 0.0
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
            "SAF_MAX_PENDING_ROWS": getattr(self.journal.config, "max_pending_rows", 0),
            "SAF_PENDING_CAP_HITS": getattr(self.journal, "pending_cap_hits", 0),
            "SAF_DEADLETTER_COUNT": int(getattr(self.journal, "deadletter_count", 0) or 0),
            "SAF_TAG_INGEST_AGE_S": self._ingest_age_s(),
            "SAF_REGIME": regime,
            "SAF_RING_FULL_TOTAL": int(getattr(self.journal, "ring_full_total", 0) or 0),
            "SAF_RING_FULL_DROPPED": int(getattr(self.journal, "ring_full_dropped", 0) or 0),
            "SAF_CRITICAL_JOURNAL_FAILED_TOTAL": int(
                getattr(self.journal, "critical_journal_failed", 0) or 0
            ),
            "SAF_REPLICATING_REWOUND_TOTAL": int(
                getattr(self.journal, "replicating_rewound", 0) or 0
            ),
            "SAF_VACUUM_LAST_DURATION_MS": float(
                getattr(self.journal, "vacuum_last_duration_ms", 0.0) or 0.0
            ),
            "SAF_VACUUM_TOTAL": int(getattr(self.journal, "vacuum_total", 0) or 0),
            "SAF_DRAIN_ACTIVE": bool(getattr(self.journal, "drain_active", False)),
            "SAF_DRAIN_ETA_S": round(eta, 3),
            "SAF_PENDING_ROWS": pending,
            "SAF_ACK_P95_MS": round(ack_p95, 3),
            "SAF_TICK_P95_MS": round(tick_p95, 3),
        }

    def _ingest_age_s(self) -> float:
        mono = float(getattr(self.journal, "last_tag_ingest_mono", 0.0) or 0.0)
        if mono <= 0:
            return 0.0
        import time

        return max(0.0, time.monotonic() - mono)


def _regime(journal: JournalWriter, pending: int) -> str:
    connected = True
    try:
        from .. import PyAutomation

        connected = bool(PyAutomation().is_db_connected())
    except Exception:
        connected = True
    if not connected:
        return "outage"
    catchup = int(getattr(journal.config, "catchup_depth", 5000) or 5000)
    if getattr(journal, "drain_active", False) or pending > catchup:
        return "draining"
    import time

    last = float(getattr(journal, "last_drain_mono", 0.0) or 0.0)
    if last > 0.0 and (time.monotonic() - last) < 60.0:
        return "post_catchup"
    return "normal"
