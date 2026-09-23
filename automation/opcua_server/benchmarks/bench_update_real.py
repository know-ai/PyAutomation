"""Update latency on a live asyncua server. Gate: 20 changes, p95 < 5 ms."""

from __future__ import annotations

import asyncio
import os
import time

from asyncua import Server, ua

from ..data_value import to_data_value
from .runner import dump, summarize


class _Tag:
    def __init__(self, value: float) -> None:
        self.value = value
        self.quality = 1.0
        self.stale = False

    def get_value(self):
        return self.value

    def get_timestamp(self):
        return None


async def _sample(n_changes: int) -> list[float]:
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/OPCUAServer/")
    idx = await server.register_namespace("urn:pyautomationio:opcua:bench")
    folder = await server.get_objects_node().add_folder(
        ua.NodeId(Identifier="PyAutomationIO", NamespaceIndex=idx),
        "PyAutomationIO",
    )
    nodes = []
    for i in range(n_changes):
        nodes.append(
            await folder.add_variable(
                ua.NodeId(Identifier=f"t:area:u_{i}", NamespaceIndex=idx),
                f"u_{i}",
                0.0,
            )
        )
    await server.start()
    samples = []
    try:
        for i, node in enumerate(nodes):
            started = time.perf_counter()
            await node.write_value(to_data_value(_Tag(float(i))))
            samples.append(time.perf_counter() - started)
    finally:
        await server.stop()
    return samples


def bench(n_changes: int = 20) -> dict:
    samples = asyncio.run(_sample(n_changes))
    return summarize("update_real", n_changes, samples, rss_mb=0.0, nodes_total=n_changes)


def main() -> None:
    result = bench(int(os.environ.get("OPCUA_BENCH_UPDATES", "20")))
    dump("bench_update.json", [result])
    print(result)


if __name__ == "__main__":
    main()
