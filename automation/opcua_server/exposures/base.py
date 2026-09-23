"""NodeExposer contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class NodeExposer(ABC):
    @property
    @abstractmethod
    def entity_type(self) -> str:
        """'t' | 'a' | 'e'."""

    @abstractmethod
    def ensure_folder(self, builder, entity: Any):
        """O(1) amortized folder lookup."""

    @abstractmethod
    def upsert(self, key: str, entity: Any):
        """O(P) with P <= 6. Complexity: O(P)."""

    @abstractmethod
    def update_value(self, key: str, entity: Any) -> None:
        """O(1) set_data_value."""

    @abstractmethod
    def remove(self, key: str) -> None:
        """O(1) dict pop."""

    @abstractmethod
    def owns(self, entity: Any) -> bool:
        """O(1) scope check."""
