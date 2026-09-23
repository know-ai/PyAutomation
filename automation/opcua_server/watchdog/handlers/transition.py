"""State entry marks the engine dirty. Does not require while_running."""

from __future__ import annotations

from ..handler import IWatchdogHandler


class TransitionWatchdogHandler(IWatchdogHandler):
    """O(1) mark. A second call while the engine is already dirty does not count again."""

    def __init__(self, server) -> None:
        self._server = server

    def on_tick(self, supervisor) -> None:
        return

    def on_transition(self, name: str, old_state: str, new_state: str) -> None:
        del old_state, new_state
        if not name or name == "OPCUAServer":
            return
        already = name in self._server._dirty_engines
        self._server.mark_engine(name)
        if not already:
            self._server.metrics.engine_watchdog_recoveries += 1

    def on_reconcile(self, supervisor) -> None:
        return
