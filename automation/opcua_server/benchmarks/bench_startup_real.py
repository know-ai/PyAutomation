"""Startup of a real asyncua.Server. One variable per tag.

The timer starts after the standard address space is loaded, and covers
the N variables plus server.start(). One sample on 2026-09-23, N=5000,
measured p95 = 9566 ms. That is above the 5000 ms objective and above the
previous 8000 ms gate. The constant stays at 8000. The objective stays open.
"""

from __future__ import annotations

import asyncio
import os
import time

from asyncua import Server, ua

from .runner import dump, summarize

STARTUP_GATE_MS = 8000


def _port() -> int:
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


async def _sample(n: int) -> float:
    server = Server()
    await server.init()
    port = _port()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/OPCUAServer/")
    idx = await server.register_namespace("urn:pyautomationio:opcua:bench")
    folder = await server.get_objects_node().add_folder(
        ua.NodeId(Identifier="PyAutomationIO", NamespaceIndex=idx),
        "PyAutomationIO",
    )
    started = time.perf_counter()
    for i in range(n):
        await folder.add_variable(
            ua.NodeId(Identifier=f"t:area:tag_{i}", NamespaceIndex=idx),
            f"tag_{i}",
            0.0,
        )
    await server.start()
    elapsed = time.perf_counter() - started
    await server.stop()
    return elapsed


def bench(n: int, repeats: int = 1) -> dict:
    samples = [asyncio.run(_sample(n)) for _ in range(repeats)]
    return summarize("startup_real", n, samples, rss_mb=0.0, nodes_total=n)


def main() -> None:
    n = int(os.environ.get("OPCUA_BENCH_N", "5000"))
    result = bench(n)
    dump("bench.json", [result])
    print(result)


if __name__ == "__main__":
    main()
