# -*- coding: utf-8 -*-
"""Writer/reader facade over JournalWriter.

The writer connection and its lock own every COMMIT. Readers use the
query_only connection opened by JournalWriter. The RAM ring has its own lock
and never fsyncs on the producer thread.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .config import SafConfig
from .contracts import IPersistable
from .journal import JournalWriter


class JournalAccess:
    """Two-connection view. JournalWriter remains the single SQLite writer."""

    def __init__(self, path: Path | str, config: SafConfig | None = None):
        base = config or SafConfig()
        self._writer = JournalWriter(
            SafConfig(
                journal_path=str(path),
                max_disk_bytes=base.max_disk_bytes,
                max_pending_rows=base.max_pending_rows,
                ring_maxsize=base.ring_maxsize,
                tag_batch_size=base.tag_batch_size,
                tag_flush_interval_s=base.tag_flush_interval_s,
                replicate_batch_size=base.replicate_batch_size,
                replicate_rate_per_s=base.replicate_rate_per_s,
                circuit_fail_threshold=base.circuit_fail_threshold,
                circuit_open_s=base.circuit_open_s,
                gc_sent_after_s=base.gc_sent_after_s,
                gc_batch=base.gc_batch,
                wal_autocheckpoint=base.wal_autocheckpoint,
                dead_letter_attempts=base.dead_letter_attempts,
                dead_letter_max_rows=base.dead_letter_max_rows,
                dead_letter_ttl_s=base.dead_letter_ttl_s,
                shed_high=base.shed_high,
                shed_low=base.shed_low,
                catchup_depth=base.catchup_depth,
                catchup_budget_s=base.catchup_budget_s,
                compact_min_freelist_bytes=base.compact_min_freelist_bytes,
                compact_min_interval_s=base.compact_min_interval_s,
                compact_max_pending=base.compact_max_pending,
                host_disk_critical_percent=base.host_disk_critical_percent,
            )
        )
        self._writer.start()

    def enqueue(self, record: IPersistable) -> int:
        return self._writer.append(record)

    def flush_ring(self) -> None:
        self._writer.flush_sync()

    def mark_replicating(self, ids: Sequence[int]) -> None:
        self._writer.mark_replicating(ids)

    def mark_sent(self, ids: Sequence[int]) -> None:
        self._writer.mark_sent(ids)

    def mark_pending(self, ids: Sequence[int], *, increment_attempts: bool = False) -> None:
        self._writer.mark_pending(ids, increment_attempts=increment_attempts)

    def fetch_pending(self, limit: int) -> list[dict]:
        return self._writer.fetch_pending(limit)

    def pending_count(self) -> int:
        return self._writer.pending_count()

    def oldest_pending_age_s(self) -> float:
        return self._writer.oldest_pending_age_s()

    def close(self) -> None:
        self._writer.stop()
