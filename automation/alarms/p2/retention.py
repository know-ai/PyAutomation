# -*- coding: utf-8 -*-
"""RetentionArchiver. Context: BG. Complexity: O(chunk) chunk≤10_000. INV-111/112/117."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .constants import _ARCHIVE_CHUNK, _RETENTION_DAYS


class RetentionArchiver:
    """Context: BG. Never DAS / TransitionWorker. Chunks acotados e idempotentes."""

    _CHUNK_SIZE = _ARCHIVE_CHUNK
    _RETENTION_DAYS = _RETENTION_DAYS

    def __init__(self, store: dict | None = None):
        self._live: list = []
        self._archive: dict[object, dict] = {}
        if store is not None:
            self._live = store.setdefault("live", [])
            self._archive = store.setdefault("archive", {})
        self.last_archived = 0
        self.runs = 0

    def seed_live(self, rows: list) -> None:
        self._live = list(rows)

    def run(self, cutoff=None, now=None) -> int:
        """Context: BG. Complexity: O(K_chunk) per iteration. Idempotent ON CONFLICT uuid."""
        now = now or datetime.now(timezone.utc)
        cutoff = cutoff or (now - timedelta(days=self._RETENTION_DAYS))
        total = 0
        while True:
            batch = []
            remain = []
            for row in self._live:
                event_time = row.get("event_time")
                if event_time is not None and event_time < cutoff and len(batch) < self._CHUNK_SIZE:
                    uuid = row.get("sample_uuid") or row.get("id")
                    if uuid not in self._archive:
                        batch.append(row)
                        self._archive[uuid] = row
                    # already archived → skip live (idempotent)
                else:
                    remain.append(row)
            self._live = remain
            n = len(batch)
            total += n
            if n < self._CHUNK_SIZE:
                break
        self.last_archived = total
        self.runs += 1
        return total

    def metrics(self) -> dict:
        """Context: API. Complexity: O(1)."""
        return {
            "last_archived": self.last_archived,
            "runs": self.runs,
            "archive_size": len(self._archive),
            "chunk_size": self._CHUNK_SIZE,
        }
