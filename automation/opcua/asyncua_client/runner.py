"""Dedicated operating-system thread and asyncio loop for field OPC UA sessions."""

from __future__ import annotations

import asyncio
import threading

from automation.opcua_server.async_core.primitives import Event, Thread

from . import handlers
from .command_queue import ClientCommandQueue
from .commands import StopClientLoop
from .result_queue import ClientResultQueue


class ClientRunner:
    """One loop per process, separate from the embedded server. Complexity: start O(1), submit O(1)."""

    def __init__(self) -> None:
        self.queue = ClientCommandQueue(maxsize=10_000)
        self.results = ClientResultQueue(maxsize=10_000)
        self._states: dict[str, bool] = {}
        self._state_lock = threading.Lock()
        self._thread = None
        self._ready = Event()
        self._stopped = Event()
        self.error = None
        self._loop_ident = None

    def set_connected(self, name: str, connected: bool) -> None:
        with self._state_lock:
            self._states[name] = bool(connected)

    def is_connected(self, name: str) -> bool:
        with self._state_lock:
            return bool(self._states.get(name, False))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._ready = Event()
        self._stopped = Event()
        self.error = None
        self._thread = Thread(target=self._thread_main, name="opcua-asyncua-client", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread.is_alive():
            self.queue.put(StopClientLoop())
            self._stopped.wait(timeout=5)
            self._thread.join(timeout=5)
        self._thread = None

    def submit(self, command) -> None:
        self.queue.put(command)

    @property
    def loop_ident(self):
        return self._loop_ident

    def _thread_main(self) -> None:
        self._loop_ident = threading.get_ident()
        asyncio.run(self._run())

    async def _run(self) -> None:
        ctx = handlers.LoopContext(self.results, self.set_connected)
        tasks: set = set()
        self._ready.set()
        try:
            while True:
                command = self.queue.get_nowait()
                if isinstance(command, StopClientLoop):
                    break
                if command is not None:
                    tasks.add(asyncio.create_task(handlers.handle(ctx, command)))
                if tasks:
                    done, tasks = await asyncio.wait(tasks, timeout=0.01)
                    for task in done:
                        exc = task.exception() if not task.cancelled() else None
                        if exc is not None:
                            self.error = exc
                else:
                    await asyncio.sleep(0.01)
        finally:
            for task in tasks:
                task.cancel()
            await ctx.close()
            self._stopped.set()
