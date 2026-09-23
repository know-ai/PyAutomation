"""Per-tag dirty tracking. A future global observer can replace this class."""

from __future__ import annotations

from typing import Any

from .observer import TagDirtyObserver
from .tracker import IDirtyTracker


class PerTagDirtyTracker(IDirtyTracker):
    """Deadband and a private observer per tag. drain reuses one scratch list."""

    def __init__(self, deadbands: dict, dirty: set, server=None, scratch_size: int = 1000) -> None:
        self._deadbands = deadbands
        self._dirty = dirty
        self._server = server
        self._last_values: dict[str, Any] = {}
        self._scratch: list[Any] = [None] * scratch_size

    def mark(self, name: str, value: Any) -> None:
        """Complexity: O(1)."""
        if hasattr(value, "value") and not isinstance(value, (int, float, str, bool)):
            value = value.value
        previous = self._last_values.get(name)
        deadband = self._deadbands.get(name, 0.0) or 0.0
        if self._within(previous, value, deadband):
            return
        self._last_values[name] = value
        self._dirty.add(name)

    def drain(self, limit: int = 1000) -> list[str]:
        """Complexity: O(K) for the drained names."""
        cap = min(limit, len(self._scratch), len(self._dirty))
        index = 0
        while self._dirty and index < cap:
            self._scratch[index] = self._dirty.pop()
            index += 1
        taken = self._scratch[:index]
        for slot in range(index):
            self._scratch[slot] = None
        return taken

    def attach(self, name: str, initial_value: Any) -> None:
        """Complexity: O(1)."""
        self._last_values[name] = initial_value
        server = self._server
        if server is None or name in server._tag_observers:
            return
        tag = server.cvt.get_tag_by_name(name=name) if name else None
        if tag is None:
            return
        observer = TagDirtyObserver(server)
        try:
            tag.attach(observer)
        except Exception:
            return
        server._tag_observers[name] = observer

    def detach(self, name: str) -> None:
        """Complexity: O(1)."""
        self._dirty.discard(name)
        self._last_values.pop(name, None)
        server = self._server
        if server is None:
            return
        observer = server._tag_observers.pop(name, None)
        if observer is None:
            return
        tag = server.cvt.get_tag_by_name(name=name) if name else None
        if tag is None:
            return
        try:
            tag.detach(observer)
        except Exception:
            return

    @staticmethod
    def _within(previous, value, deadband) -> bool:
        if previous is None or deadband <= 0:
            return False
        if isinstance(value, bool) or isinstance(previous, bool):
            return False
        if not isinstance(value, (int, float)) or not isinstance(previous, (int, float)):
            return False
        return abs(float(value) - float(previous)) < float(deadband)
