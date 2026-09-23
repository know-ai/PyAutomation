"""Results from the field-client loop back to gevent. Drops the oldest when full."""

from __future__ import annotations

from automation.opcua_server.async_core.primitives import Empty, Queue


def _queue_full():
    try:
        from gevent.monkey import get_original

        return get_original("queue", "Full")
    except Exception:
        import queue

        return queue.Full


class ClientResultQueue:
    """Complexity: put O(1), drain O(K)."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self.maxsize = maxsize
        self._queue = Queue(maxsize=maxsize)
        self.discarded = 0
        self._full = _queue_full()

    def put(self, item) -> None:
        """Non-blocking. Discards the oldest item when full. Complexity: O(1)."""
        try:
            self._queue.put_nowait(item)
            return
        except self._full:
            pass
        except Exception:
            return
        try:
            self._queue.get_nowait()
        except Empty:
            self.discarded += 1
            return
        self.discarded += 1
        try:
            self._queue.put_nowait(item)
        except Exception:
            self.discarded += 1

    def drain(self) -> list:
        """Take every pending result. Complexity: O(K)."""
        items = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except Empty:
                return items

    def size(self) -> int:
        return self._queue.qsize()
