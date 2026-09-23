"""Dirty-set contract. Runtime depends on this interface, not on an implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IDirtyTracker(ABC):
    """Track entities changed since the last tick.

    Complexity:
      - mark: O(1)
      - drain: O(K)
      - attach: O(1)
      - detach: O(1)
    """

    @abstractmethod
    def mark(self, name: str, value: Any) -> None:
        """Mark an entity dirty when it passes the deadband."""

    @abstractmethod
    def drain(self, limit: int = 1000) -> list[str]:
        """Return and clear up to ``limit`` dirty names. O(K)."""

    @abstractmethod
    def attach(self, name: str, initial_value: Any) -> None:
        """Start tracking an entity."""

    @abstractmethod
    def detach(self, name: str) -> None:
        """Stop tracking an entity and release its observer."""
