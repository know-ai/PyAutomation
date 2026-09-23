"""RSS after N live asyncua variables. Gate: N=10000 stays under 300 MB."""

from __future__ import annotations

import asyncio
import os

from asyncua import Server, ua

from .runner import dump, summarize


def _rss_mb() -> float:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return 0.0


async def _build(n: int) -> None:
    server = Server()
    await server.init()
    idx = await server.register_namespace("urn:pyautomationio:opcua:bench")
    folder = await server.get_objects_node().add_folder(
        ua.NodeId(Identifier="PyAutomationIO", NamespaceIndex=idx),
        "PyAutomationIO",
    )
    for i in range(n):
        await folder.add_variable(
            ua.NodeId(Identifier=f"t:area:m_{i}", NamespaceIndex=idx),
            f"m_{i}",
            0.0,
        )


def bench(n: int):
    asyncio.run(_build(n))
    return summarize("memory_real", n, [0.0], rss_mb=_rss_mb(), nodes_total=n)


def main() -> None:
    n = int(os.environ.get("OPCUA_BENCH_N", "10000"))
    result = bench(n)
    dump("bench_memory.json", [result])
    print(result)


if __name__ == "__main__":
    main()
