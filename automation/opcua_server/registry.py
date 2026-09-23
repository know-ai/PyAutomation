"""O(1) registries for exposers, publishers and lint rules."""

from __future__ import annotations

import threading
from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Generic registry. register/get are O(1). all is O(N)."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._items: dict[str, T] = {}
        self._lock = threading.Lock()
        self._frozen = False

    def freeze(self) -> None:
        """Reject later registrations. Complexity: O(1)."""
        with self._lock:
            self._frozen = True

    def register(self, key: str, item: T) -> None:
        """Register ``item``. Same object twice is a no-op. A different object raises ValueError.

        After ``freeze``, every register raises RuntimeError. Complexity: O(1).
        """
        with self._lock:
            if self._frozen:
                raise RuntimeError(f"{self._name} is frozen")
            existing = self._items.get(key)
            if existing is item:
                return
            if existing is not None:
                raise ValueError(f"{key} already registered in {self._name}")
            self._items[key] = item

    def get(self, key: str) -> T:
        """Complexity: O(1)."""
        return self._items[key]

    def all(self) -> tuple[T, ...]:
        """Complexity: O(N)."""
        with self._lock:
            return tuple(self._items.values())


exposer_registry: Registry[type] = Registry("exposers")
lint_registry: Registry[object] = Registry("lint_rules")
publisher_registry: Registry[type] = Registry("publishers")


def register_exposer(cls):
    """Register a NodeExposer class by its ``entity_kind`` attribute. O(1)."""
    key = getattr(cls, "entity_kind", None) or cls.__name__
    exposer_registry.register(key, cls)
    return cls


def register_publisher(key: str):
    """Register an IPublisher class. O(1)."""

    def decorate(cls):
        publisher_registry.register(key, cls)
        return cls

    return decorate


def register_lint_rule(cls):
    """Register a LintRule instance by ``rule_id``. O(1)."""
    rule = cls()
    lint_registry.register(rule.rule_id, rule)
    return cls
