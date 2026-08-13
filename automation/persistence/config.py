# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SafConfig:
    """Operational contracts for the local outbox (Phoenix Directive)."""

    journal_path: str = os.path.join(".", "db", "saf", "journal.db")
    max_disk_bytes: int = 10 * 1024 * 1024 * 1024
    ring_maxsize: int = 50_000
    tag_batch_size: int = 256
    tag_flush_interval_s: float = 0.010
    replicate_batch_size: int = 1_000
    replicate_rate_per_s: int = 10_000
    circuit_fail_threshold: int = 5
    circuit_open_s: float = 5.0
    gc_sent_after_s: float = 3600.0
    gc_batch: int = 5_000
    backup_size_bytes: int = 1 * 1024 * 1024 * 1024
    wal_autocheckpoint: int = 1000

    @classmethod
    def from_app_config(cls, raw: dict | None) -> "SafConfig":
        data = dict(raw or {})
        defaults = cls()
        return cls(
            journal_path=str(data.get("saf_journal_path", defaults.journal_path)),
            max_disk_bytes=int(data.get("saf_max_disk_bytes", defaults.max_disk_bytes)),
            ring_maxsize=int(data.get("saf_ring_maxsize", defaults.ring_maxsize)),
            tag_batch_size=int(data.get("saf_tag_batch_size", defaults.tag_batch_size)),
            tag_flush_interval_s=float(data.get("saf_tag_flush_interval_s", defaults.tag_flush_interval_s)),
            replicate_batch_size=int(data.get("saf_replicate_batch_size", defaults.replicate_batch_size)),
            replicate_rate_per_s=int(data.get("saf_replicate_rate_per_s", defaults.replicate_rate_per_s)),
            circuit_fail_threshold=int(data.get("saf_circuit_fail_threshold", defaults.circuit_fail_threshold)),
            circuit_open_s=float(data.get("saf_circuit_open_s", defaults.circuit_open_s)),
            gc_sent_after_s=float(data.get("saf_gc_sent_after_s", defaults.gc_sent_after_s)),
            gc_batch=int(data.get("saf_gc_batch", defaults.gc_batch)),
            backup_size_bytes=int(data.get("saf_backup_size_bytes", defaults.backup_size_bytes)),
            wal_autocheckpoint=int(data.get("saf_wal_autocheckpoint", defaults.wal_autocheckpoint)),
        )
