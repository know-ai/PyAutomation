# -*- coding: utf-8 -*-
"""Dedicated SAF drain worker. Journal compact runs only when the queue is quiet."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from .worker import BaseWorker

_LOGGER = logging.getLogger("pyautomation")


class ReplicationWorker(BaseWorker):
    """OS thread: catch-up replicate_once until the journal is quiet, then reclaim."""

    def __init__(self):
        super().__init__()
        self.name = "ReplicationWorker"
        self.daemon = True
        self.last_cycle_utc = None
        self.last_replicated = 0
        self._wake = threading.Event()

    def request_cycle(self) -> None:
        self._wake.set()

    def run(self):
        while not self.stop_event.is_set():
            self._wake.clear()
            idle_s = 1.0
            try:
                from ..persistence import get_persistence_gateway

                gateway = get_persistence_gateway()
                pending = int(gateway.pending_count() or 0)
                catchup_depth = int(getattr(gateway.config, "catchup_depth", 5000) or 5000)
                if pending > 0:
                    written = gateway.replicate_catchup()
                    self.last_replicated = int(written or 0)
                    self.last_cycle_utc = datetime.now(timezone.utc).isoformat()
                    idle_s = 0.01 if pending > catchup_depth else 0.2
                    if pending <= catchup_depth:
                        gateway.reclaim_idle()
                else:
                    gateway.reclaim_idle()
                    self.last_cycle_utc = datetime.now(timezone.utc).isoformat()
                    idle_s = 5.0
                    # Nothing to drain: an empty journal can stay empty for
                    # hours, so give the socket back instead of parking it.
                    self.release_historian_socket()
            except Exception:
                _LOGGER.error("SAF replication worker cycle failed; journal preserved", exc_info=True)
                idle_s = 1.0
            self._wake.wait(timeout=idle_s)
        self.release_historian_socket()
        _LOGGER.info("ReplicationWorker shutdown")
