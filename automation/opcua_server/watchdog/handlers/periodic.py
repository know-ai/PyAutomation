"""Rotating tag slice. A tag silent for 300 s joins the dirty set."""

from __future__ import annotations

import logging
import time

from ...runtime import WATCHDOG_S, WATCHDOG_SLICE
from ..handler import IWatchdogHandler

_LOG = logging.getLogger("pyautomation")


class PeriodicWatchdogHandler(IWatchdogHandler):
    """O(slice) per call. slice is 200 names."""

    def on_tick(self, supervisor) -> None:
        self._slice(supervisor.server)

    def on_transition(self, name: str, old_state: str, new_state: str) -> None:
        return

    def on_reconcile(self, supervisor) -> None:
        self._slice(supervisor.server)

    def _slice(self, server) -> None:
        order = server._watch_order
        if not order:
            return
        now = time.monotonic()
        count = min(WATCHDOG_SLICE, len(order))
        start = server._watch_index
        for step in range(count):
            name = order[(start + step) % len(order)]
            seen = server._last_touch.get(name)
            if seen is not None and (now - seen) < WATCHDOG_S:
                continue
            _LOG.warning("OPC UA watchdog refreshing stale tag %s", name)
            if name not in server._dirty_tags:
                server.metrics.tag_watchdog_recoveries += 1
                from ...audit import audit_failure

                audit_failure("OPC UA tag watchdog recovery", name, criticity=2)
            server._dirty_tags.add(name)
            server._last_touch[name] = now
        server._watch_index = (start + count) % len(order)
