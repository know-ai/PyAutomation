"""Local asyncua server used by the field-client benches."""

from __future__ import annotations

import asyncio
import json
import socket
import sys

from asyncua import Server, ua
from automation.opcua_server.async_core.primitives import Event, Thread


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


class LocalServer:
    def __init__(self, count: int) -> None:
        self.count = count
        self.url = f"opc.tcp://127.0.0.1:{free_port()}/bench/"
        self.node_ids: list[str] = []
        self._ready = Event()
        self._stop = Event()
        self._thread = Thread(target=self._main, name="opcua-bench-server", daemon=True)
        self.error = None

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise TimeoutError(self.error or "bench server did not start")
        if self.error:
            raise self.error

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self.error = exc
            self._ready.set()

    async def _serve(self) -> None:
        server = Server()
        await server.init()
        server.set_endpoint(self.url)
        index = await server.register_namespace("urn:pyautomationio:opcua:client-bench")
        folder = await server.get_objects_node().add_folder(
            ua.NodeId(Identifier="Bench", NamespaceIndex=index),
            "Bench",
        )
        for item in range(self.count):
            node = await folder.add_variable(
                ua.NodeId(Identifier=f"T{item}", NamespaceIndex=index),
                f"T{item}",
                float(item),
            )
            self.node_ids.append(node.nodeid.to_string())
        await server.start()
        self._ready.set()
        while not self._stop.is_set():
            await asyncio.sleep(0.05)
        await server.stop()


def serve_until_stdin(port: int, count: int) -> None:
    """Process entry for the gevent bench. One JSON line, then serve until stdin closes."""
    url = f"opc.tcp://127.0.0.1:{port}/bench/"
    ready = Event()
    stop = Event()
    node_ids: list[str] = []

    def main() -> None:
        asyncio.run(_serve_fixed(url, count, node_ids, ready, stop))

    thread = Thread(target=main, name="opcua-bench-server", daemon=True)
    thread.start()
    if not ready.wait(timeout=15):
        raise SystemExit("bench server did not start")
    print(json.dumps({"url": url, "node_ids": node_ids}), flush=True)
    sys.stdin.read()
    stop.set()
    thread.join(timeout=5)


async def _serve_fixed(url: str, count: int, node_ids: list[str], ready: Event, stop: Event) -> None:
    server = Server()
    await server.init()
    server.set_endpoint(url)
    index = await server.register_namespace("urn:pyautomationio:opcua:client-bench")
    folder = await server.get_objects_node().add_folder(
        ua.NodeId(Identifier="Bench", NamespaceIndex=index),
        "Bench",
    )
    for item in range(count):
        node = await folder.add_variable(
            ua.NodeId(Identifier=f"T{item}", NamespaceIndex=index),
            f"T{item}",
            float(item),
        )
        node_ids.append(node.nodeid.to_string())
    await server.start()
    ready.set()
    while not stop.is_set():
        await asyncio.sleep(0.05)
    await server.stop()


if __name__ == "__main__":
    serve_until_stdin(int(sys.argv[1]), int(sys.argv[2]))
