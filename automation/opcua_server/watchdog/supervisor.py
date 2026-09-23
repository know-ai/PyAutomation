"""Orchestrates watchdog handlers. The facade depends on this type."""

from __future__ import annotations

from .handlers.periodic import PeriodicWatchdogHandler
from .handlers.reconcile import ReconcileWatchdogHandler
from .handlers.transition import TransitionWatchdogHandler

_supervisor = None


class WatchdogSupervisor:
    """Fan-out to handlers. notify_transition is O(1)."""

    def __init__(self, server) -> None:
        self.server = server
        self.transition = TransitionWatchdogHandler(server)
        self._handlers = (
            self.transition,
            ReconcileWatchdogHandler(),
            PeriodicWatchdogHandler(),
        )

    def notify_transition(self, name: str, old_state: str, new_state: str) -> None:
        """Complexity: O(1)."""
        for handler in self._handlers:
            handler.on_transition(name, old_state, new_state)

    def on_tick(self) -> None:
        """Complexity: O(slice) in the periodic handler."""
        for handler in self._handlers:
            handler.on_tick(self)

    def on_reconcile(self) -> None:
        """Complexity: O(E) in the reconcile handler."""
        for handler in self._handlers:
            handler.on_reconcile(self)


def bind_watchdog(supervisor: WatchdogSupervisor) -> None:
    global _supervisor
    _supervisor = supervisor


def unbind_watchdog(supervisor: WatchdogSupervisor) -> None:
    global _supervisor
    if _supervisor is supervisor:
        _supervisor = None


def notify_transition(name: str, old_state: str, new_state: str) -> None:
    """O(1). No-op when the embedded server has not bound a supervisor."""
    supervisor = _supervisor
    if supervisor is None or not name:
        return
    supervisor.notify_transition(name, old_state, new_state)


def get_opcua_watchdog() -> WatchdogSupervisor | None:
    return _supervisor
