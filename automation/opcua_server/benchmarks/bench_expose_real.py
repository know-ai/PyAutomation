"""Expose latency for one tag on a live asyncua server. Gate: p95 < 100 ms."""

from __future__ import annotations

import asyncio
import time

from asyncua import Server, ua

from .runner import dump, summarize


async def _sample() -> float:
    server = Server()
    await server.init()
    idx = await server.register_namespace("urn:pyautomationio:opcua:bench")
    folder = await server.get_objects_node().add_folder(
        ua.NodeId(Identifier="Process", NamespaceIndex=idx),
        "Process",
    )
    started = time.perf_counter()
    await folder.add_variable(
        ua.NodeId(Identifier="t:area:one", NamespaceIndex=idx),
        "one",
        0.0,
    )
    elapsed = time.perf_counter() - started
    await server.stop()
    return elapsed


def bench() -> dict:
    samples = [asyncio.run(_sample()) for _ in range(5)]
    return summarize("expose_real", 1, samples, rss_mb=0.0, nodes_total=1)


def main() -> None:
    result = bench()
    dump("bench_expose.json", [result])
    print(result)


if __name__ == "__main__":
    main()
