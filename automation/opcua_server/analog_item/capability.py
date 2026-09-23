"""Capability probe contract. probe is O(1) and runs once at startup."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ICapabilityProbe(ABC):
    @abstractmethod
    def probe(self) -> bool:
        """Return True when the capability is available."""

    @abstractmethod
    def cached(self) -> bool | None:
        """Cached probe result, or None before the first probe."""
