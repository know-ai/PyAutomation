"""Thread-safe command queue from the gevent thread to the asyncio thread."""

from __future__ import annotations

from .primitives import Empty, Queue


class CommandQueue:
    """Complexity: put O(1), get O(1), size O(1)."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self.maxsize = maxsize
        self._queue = Queue(maxsize=maxsize)

    def put(self, command) -> None:
        """Enqueue a command. Blocks if full. Complexity: O(1)."""
        self._queue.put(command)

    def get_nowait(self):
        """Dequeue a command without blocking. Complexity: O(1)."""
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def size(self) -> int:
        """Complexity: O(1)."""
        return self._queue.qsize()
