import asyncio
import threading
import unittest

from automation.opcua_server.async_core.command_queue import CommandQueue
from automation.opcua_server.async_core.primitives import Event, Thread
from automation.opcua_server.async_core.runner import AsyncioRunner


class _Probe:
    def __init__(self, done: Event, idents: list) -> None:
        self._done = done
        self._idents = idents

    async def apply(self, _ctx) -> None:
        self._idents.append(threading.get_ident())
        self._done.set()


class TestCommandQueue(unittest.TestCase):
    def test_maxsize_and_hundred_commands_without_network(self):
        queue = CommandQueue()
        self.assertEqual(queue.maxsize, 10_000)
        self.assertIsNone(queue.get_nowait())
        for index in range(100):
            queue.put(index)
        self.assertEqual(queue.size(), 100)
        self.assertEqual(queue.get_nowait(), 0)
        self.assertEqual(queue.size(), 99)

    def test_submit_runs_on_another_thread(self):
        runner = AsyncioRunner(app=object())
        done = Event()
        idents = []
        caller = threading.get_ident()
        runner.start()
        try:
            for _ in range(99):
                runner.submit(_Probe(Event(), idents))
            runner.submit(_Probe(done, idents))
            self.assertTrue(done.wait(2))
            self.assertEqual(len(idents), 100)
            self.assertNotIn(caller, idents)
        finally:
            runner.stop()


class TestPerThreadRunningLoop(unittest.TestCase):
    def test_wait_for_on_two_threads(self):
        async def probe():
            await asyncio.wait_for(asyncio.sleep(0), timeout=1)
            return True

        results: list[bool] = []

        def run() -> None:
            results.append(asyncio.run(probe()))

        threads = [Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results, [True, True])
