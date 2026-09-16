# -*- coding: utf-8 -*-
"""GATE-36: Redis session isolation + in-process dual drain (no Redis alarm queue)."""
from __future__ import annotations

import inspect
import subprocess
import threading
import unittest

from automation.alarms import runtime as runtime_mod
from automation.alarms.runtime import KIND_EMIT, reset_alarm_runtime_for_tests


class TestMultiworkerPgRedis(unittest.TestCase):
    def test_runtime_does_not_import_redis(self):
        source = inspect.getsource(runtime_mod)
        self.assertNotIn("import redis", source)
        self.assertNotIn("from redis", source)

    def test_redis_db15_isolated(self):
        proc = subprocess.run(
            ["docker", "exec", "compose-redis-session-1", "redis-cli", "-n", "15", "PING"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.stdout.strip(), "PONG")
        subprocess.run(
            ["docker", "exec", "compose-redis-session-1", "redis-cli", "-n", "15", "SET", "isa18:test", "1"],
            check=True,
            capture_output=True,
        )
        got = subprocess.run(
            ["docker", "exec", "compose-redis-session-1", "redis-cli", "-n", "15", "GET", "isa18:test"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(got.stdout.strip(), "1")
        subprocess.run(
            ["docker", "exec", "compose-redis-session-1", "redis-cli", "-n", "15", "FLUSHDB"],
            check=True,
            capture_output=True,
        )

    def test_two_drainers_process_each_event_once(self):
        runtime = reset_alarm_runtime_for_tests()
        class Dummy:
            identifier = "d"
            name = "d"
            last_transition_to = None
            state = None
        dummy = Dummy()
        n = 100
        for _ in range(n):
            runtime.enqueue(dummy, KIND_EMIT)
        seen = []
        lock = threading.Lock()

        def worker():
            while True:
                batch = runtime.dequeue_batch(100)
                if not batch:
                    return
                with lock:
                    seen.extend(batch)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        runtime.stop_worker()
        self.assertEqual(len(seen), n)
        self.assertEqual(runtime.queue_depth(), 0)
