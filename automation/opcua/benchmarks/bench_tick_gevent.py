"""Bench of the gevent tick while a field Read is in flight.

Patch happens before the application import. The OPC server is another process,
so this process has a single asyncio loop on the client thread.

The hub sleeps 10 ms. The printed p95 is the extra delay over that sleep.
"""

from __future__ import annotations

from gevent import monkey

monkey.patch_all()

import json
import subprocess
import sys
import time

import gevent

from automation.opcua.asyncua_client import sync_adapter
from automation.opcua.benchmarks.support import free_port, percentile
from automation.opcua.models import Client


def main() -> None:
    port = free_port()
    count = 100
    process = subprocess.Popen(
        [sys.executable, "-m", "automation.opcua.benchmarks.support", str(port), str(count)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    line = process.stdout.readline()
    info = json.loads(line)
    client = Client(info["url"], client_name="BENCH-TICK")
    gaps = []
    try:
        sync_adapter.open_session(info["url"], client.name, 10)

        def ticker() -> None:
            previous = time.perf_counter()
            deadline = previous + 0.6
            while time.perf_counter() < deadline:
                gevent.sleep(0.01)
                now = time.perf_counter()
                gaps.append((now - previous - 0.01) * 1000)
                previous = now

        def reader() -> None:
            gevent.sleep(0.05)
            client.read_data_values_bounded(info["node_ids"], timeout_s=2)

        gevent.joinall(
            [gevent.spawn(ticker), gevent.spawn(reader)],
            timeout=3,
        )
    finally:
        try:
            sync_adapter.close_session(client.name)
        except Exception:
            pass
        sync_adapter.reset_runner_for_tests()
        if process.stdin:
            process.stdin.close()
        process.wait(timeout=5)
    if len(gaps) < 10:
        raise RuntimeError(f"tick samples={len(gaps)}")
    print(
        f"gevent_tick during_read samples={len(gaps)} "
        f"extra_p50_ms={percentile(gaps, 0.50):.3f} extra_p95_ms={percentile(gaps, 0.95):.3f}"
    )


if __name__ == "__main__":
    main()
