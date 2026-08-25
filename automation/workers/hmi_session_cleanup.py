# -*- coding: utf-8 -*-
"""Prune stale HMI Socket.IO sessions from Redis sidecar / RAM.

PostgreSQL snapshots are owned by HmiSessionSyncWorker — this worker never
writes hmi_sessions.
"""
from __future__ import annotations

import logging

from .worker import BaseWorker
from ..utils.hmi_session_store import cleanup_stale_sessions

_LOGGER = logging.getLogger("pyautomation.hmi_sessions")

_CLEANUP_INTERVAL_S = 60.0
_STALE_SECONDS = 120


class HmiSessionCleanupWorker(BaseWorker):
    """Daemon thread; prunes Redis/RAM TTL. Never on the Socket.IO hot path."""

    def __init__(
        self,
        interval_s: float = _CLEANUP_INTERVAL_S,
        stale_seconds: int = _STALE_SECONDS,
    ):
        super().__init__()
        self.name = "HmiSessionCleanupWorker"
        self.daemon = True
        self._interval_s = max(10.0, float(interval_s))
        self._stale_seconds = max(60, int(stale_seconds))

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                removed = cleanup_stale_sessions(stale_seconds=self._stale_seconds)
                if removed:
                    _LOGGER.debug("HMI session cleanup removed %s stale sids", removed)
            except Exception:
                _LOGGER.debug("HMI session cleanup worker tick failed", exc_info=True)
            self.stop_event.wait(self._interval_s)
