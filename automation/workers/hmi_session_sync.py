# -*- coding: utf-8 -*-
"""Background snapshot of local HMI sessions into PostgreSQL.

Never runs on the Socket.IO hot path. Reads Redis sidecar / RAM and writes a
batch UPSERT every 5 s.
"""
from __future__ import annotations

import logging

from .worker import BaseWorker
from ..utils.hmi_session_store import cleanup_stale_sessions, node_identity, sync_sessions_to_pg

_LOGGER = logging.getLogger("pyautomation.hmi_sessions")

_SYNC_INTERVAL_S = 5.0
_STALE_SECONDS = 120
_CLEANUP_EVERY_N = 12  # ~60 s at 5 s ticks


class HmiSessionSyncWorker(BaseWorker):
    """Daemon thread; batch-syncs this edge's live sids to PostgreSQL."""

    def __init__(self, interval_s: float = _SYNC_INTERVAL_S):
        super().__init__()
        self.name = "HmiSessionSyncWorker"
        self.daemon = True
        self._interval_s = max(1.0, float(interval_s))
        self._ticks = 0

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                with self.historian_cycle():
                    node_id, _ = node_identity()
                    synced = sync_sessions_to_pg(node_id)
                    if synced:
                        _LOGGER.debug(
                            "HMI session PG snapshot wrote %s rows node=%s", synced, node_id
                        )
                    self._ticks += 1
                    if self._ticks % _CLEANUP_EVERY_N == 0:
                        removed = cleanup_stale_sessions(stale_seconds=_STALE_SECONDS)
                        if removed:
                            _LOGGER.debug("HMI session cleanup removed %s stale sids", removed)
            except Exception:
                _LOGGER.exception("Sync session to PG failed")
            self.stop_event.wait(self._interval_s)
        self.release_historian_socket()
