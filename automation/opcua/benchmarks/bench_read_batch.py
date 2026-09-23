"""Bench B: one Read of N nodes on one URL. Prints the measured p95."""

from __future__ import annotations

import time

from automation.opcua.asyncua_client import sync_adapter
from automation.opcua.benchmarks.support import LocalServer, percentile
from automation.opcua.models import Client


def main() -> None:
    count = 200
    repeats = 20
    server = LocalServer(count)
    server.start()
    client = Client(server.url, client_name="BENCH-READ")
    samples = []
    try:
        sync_adapter.open_session(server.url, client.name, 10)
        for _ in range(3):
            client.read_data_values_bounded(server.node_ids, timeout_s=5)
        for _ in range(repeats):
            started = time.perf_counter()
            payload = client.read_data_values_bounded(server.node_ids, timeout_s=5)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if not isinstance(payload, dict) or payload.get(server.node_ids[0]) is None:
                raise RuntimeError("empty batch")
            samples.append(elapsed_ms)
    finally:
        try:
            sync_adapter.close_session(client.name)
        finally:
            server.stop()
            sync_adapter.reset_runner_for_tests()
    print(
        f"read_batch n={count} repeats={repeats} "
        f"p50_ms={percentile(samples, 0.50):.3f} p95_ms={percentile(samples, 0.95):.3f}"
    )


if __name__ == "__main__":
    main()
