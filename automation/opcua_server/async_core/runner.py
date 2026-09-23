"""Dedicated operating-system thread and its asyncio loop."""

from __future__ import annotations

import asyncio
import threading

from .command_queue import CommandQueue
from .commands import StopServer
from .handlers import BATCH_LIMIT, LoopContext, handle
from .primitives import Event, Thread


class AsyncioRunner:
    """Complexity: start O(1), stop O(1), submit O(1)."""

    def __init__(self, app) -> None:
        self._app = app
        self.queue = CommandQueue()
        self._thread = None
        self._ready = Event()
        self._stopped = Event()
        self._started = False
        self.error = None
        self._loop_ident = None

    def start(self) -> None:
        """Start the dedicated thread and event loop. Complexity: O(1)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._ready = Event()
        self._stopped = Event()
        self.error = None
        self._thread = Thread(target=self._thread_main, name="opcua-asyncua", daemon=True)
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        """Stop the event loop and join the thread. Idempotent. Complexity: O(1)."""
        if self._thread is None:
            return
        if self._thread.is_alive():
            self.submit(StopServer())
            self._stopped.wait(timeout=5)
            self._thread.join(timeout=5)
        self._thread = None
        self._started = False

    def submit(self, command) -> None:
        """Enqueue a command for the event loop. Complexity: O(1)."""
        self.queue.put(command)

    def wait_ready(self, timeout: float = 30) -> bool:
        """Complexity: O(1) wait."""
        return bool(self._ready.wait(timeout))

    @property
    def loop_ident(self):
        return self._loop_ident

    def _thread_main(self) -> None:
        self._loop_ident = threading.get_ident()
        asyncio.run(self._run())

    async def _run(self) -> None:
        ctx = LoopContext(self._app)
        try:
            while True:
                batch = []
                for _ in range(BATCH_LIMIT):
                    command = self.queue.get_nowait()
                    if command is None:
                        break
                    batch.append(command)
                    await asyncio.sleep(0)
                stop = False
                writes = []
                for command in batch:
                    if isinstance(command, StopServer):
                        await handle(ctx, command)
                        stop = True
                        break
                    if type(command).__name__ == "WriteValues":
                        writes.extend(command.items)
                        continue
                    try:
                        await handle(ctx, command)
                    except Exception as exc:
                        self.error = exc
                    if type(command).__name__ == "StartEndpoint":
                        self._ready.set()
                if writes:
                    from .commands import WriteValues

                    await handle(ctx, WriteValues(tuple(writes)))
                if stop:
                    break
                if not batch:
                    await asyncio.sleep(0.05)
        finally:
            self._ready.set()
            self._stopped.set()
