"""Shared write subscription plus the SCADA sink that only enqueues."""

from __future__ import annotations

from .sink import ScadaWriteSink, install_write_gate

__all__ = ["ScadaWriteSink", "WriteBackHandler", "install_write_gate"]


class WriteBackHandler:
    """Legacy subscription counter used by the sync fallback. Complexity: O(1) per subscribe."""

    def __init__(self) -> None:
        self._subscription = None
        self._handler = None
        self._items: dict[str, object] = {}

    @property
    def active(self) -> int:
        """Complexity: O(1)."""
        return len(self._items)

    def _ensure_write_subscription(self, server):
        if self._subscription is None:
            from ...opcua.subscription import SubHandlerServer

            self._handler = SubHandlerServer()
            self._subscription = server.create_subscription(100, self._handler)
        return self._subscription

    def subscribe(self, server, node) -> None:
        """One shared subscription. Complexity: O(1)."""
        namespace = node.nodeid.to_string()
        if namespace in self._items:
            return
        subscription = self._ensure_write_subscription(server)
        handle = subscription.subscribe_data_change(node)
        self._items[namespace] = handle
        if self._handler is not None:
            self._handler.subscriptions[namespace] = subscription

    def unsubscribe(self, namespace: str) -> None:
        """Complexity: O(1)."""
        handle = self._items.pop(namespace, None)
        if handle is None or self._subscription is None:
            return
        try:
            self._subscription.unsubscribe(handle)
        except Exception:
            self._items.pop(namespace, None)
        if self._handler is not None:
            self._handler.subscriptions.pop(namespace, None)

    def clear(self) -> None:
        """Complexity: O(1)."""
        if self._subscription is not None:
            try:
                self._subscription.delete()
            except Exception:
                self._subscription = None
        self._subscription = None
        self._handler = None
        self._items.clear()
