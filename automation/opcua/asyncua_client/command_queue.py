"""Thread-safe command queue from gevent to the field-client loop."""

from __future__ import annotations

from automation.opcua_server.async_core.primitives import Empty, Queue


class ClientCommandQueue:
    """Complexity: put O(1), try_put O(1), get O(1)."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self.maxsize = maxsize
        self._queue = Queue(maxsize=maxsize)

    def put(self, command) -> None:
        """Enqueue. Blocks if full. Complexity: O(1)."""
        self._queue.put(command)

    def try_put(self, command) -> bool:
        """Enqueue without blocking. Complexity: O(1)."""
        try:
            self._queue.put_nowait(command)
            return True
        except Exception:
            return False

    def get_nowait(self):
        """Dequeue without blocking. Complexity: O(1)."""
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def size(self) -> int:
        return self._queue.qsize()
