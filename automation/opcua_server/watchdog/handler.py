"""Watchdog handler contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IWatchdogHandler(ABC):
    """Complexity: on_tick O(K), on_transition O(1), on_reconcile O(N+M+E)."""

    @abstractmethod
    def on_tick(self, supervisor) -> None:
        """Called on the constant-mode tick."""

    @abstractmethod
    def on_transition(self, name: str, old_state: str, new_state: str) -> None:
        """Called when a state machine enters a state."""

    @abstractmethod
    def on_reconcile(self, supervisor) -> None:
        """Called on the full reconciliation pass."""
