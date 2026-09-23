"""Bench A: two URLs read in the same window. Prints the measured p95 of each pair."""

from __future__ import annotations

import time

from automation.opcua.asyncua_client import sync_adapter
from automation.opcua.benchmarks.support import LocalServer, percentile
from automation.opcua.models import Client
from automation.opcua_server.async_core.primitives import Thread


def main() -> None:
    count = 100
    repeats = 15
    left = LocalServer(count)
    right = LocalServer(count)
    left.start()
    right.start()
    client_a = Client(left.url, client_name="BENCH-A")
    client_b = Client(right.url, client_name="BENCH-B")
    samples = []
    try:
        sync_adapter.open_session(left.url, client_a.name, 10)
        sync_adapter.open_session(right.url, client_b.name, 10)
        for _ in range(2):
            client_a.read_data_values_bounded(left.node_ids, timeout_s=5)
            client_b.read_data_values_bounded(right.node_ids, timeout_s=5)

        def read(client, node_ids, slot):
            started = time.perf_counter()
            payload = client.read_data_values_bounded(node_ids, timeout_s=5)
            slot.append(((time.perf_counter() - started) * 1000, payload))

        for _ in range(repeats):
            slot_a, slot_b = [], []
            thread_a = Thread(target=read, args=(client_a, left.node_ids, slot_a), name="bench-a")
            thread_b = Thread(target=read, args=(client_b, right.node_ids, slot_b), name="bench-b")
            started = time.perf_counter()
            thread_a.start()
            thread_b.start()
            thread_a.join()
            thread_b.join()
            wall_ms = (time.perf_counter() - started) * 1000
            if not slot_a or not slot_b or slot_a[0][1] is None or slot_b[0][1] is None:
                raise RuntimeError("parallel read missed")
            samples.append(wall_ms)
    finally:
        for client in (client_a, client_b):
            try:
                sync_adapter.close_session(client.name)
            except Exception:
                pass
        left.stop()
        right.stop()
        sync_adapter.reset_runner_for_tests()
    print(
        f"parallel_plc urls=2 n={count} repeats={repeats} "
        f"p50_ms={percentile(samples, 0.50):.3f} p95_ms={percentile(samples, 0.95):.3f}"
    )


if __name__ == "__main__":
    main()
