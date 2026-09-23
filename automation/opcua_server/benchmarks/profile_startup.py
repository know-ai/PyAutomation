"""cProfile of a 5000-tag startup. Library time and package time are reported apart.

Writes startup_profile.prof for the package materialization and a text report
with the ten functions of highest cumulative time.
"""

from __future__ import annotations

import asyncio
import cProfile
import io
import os
import pstats
import socket
from pathlib import Path

from asyncua import Server

from ..address_space import AddressSpaceBuilder
from .bench_startup_real import bench


class SyntheticTag:
    """Float tag Supe.Linea1.FI_XXXX. No database."""

    def __init__(self, index: int) -> None:
        self.name = f"Supe.Linea1.FI_{index:04d}"
        self.area = "Linea1"
        self.manufacturer = "Supe"
        self.display_name = f"FI_{index:04d}"
        self.filter_enabled = False
        self.quality = 1.0
        self.stale = False

    def get_data_type(self) -> str:
        return "float"

    def get_variable(self) -> str:
        return "Flow"

    def get_unit(self) -> str:
        return "m3/h"

    def get_scan_time(self):
        return None

    def get_dead_band(self):
        return 0

    def get_value(self) -> float:
        return 1.0

    def get_timestamp(self):
        return None


def _port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


async def package_startup(n: int) -> None:
    """Build the canonical tree and materialize n analog tags on a live server."""
    from asyncua import ua

    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{_port()}/OPCUAServer/")
    index = await server.register_namespace("urn:pyautomationio:opcua:profile")
    builder = AddressSpaceBuilder(server.get_objects_node(), index)
    folder = await builder.ensure_branch_async("Supe", "Linea1", "Process")
    for i in range(n):
        tag = SyntheticTag(i)
        await builder.add_variable_async(folder, f"t:linea1:tag_{i}", tag.display_name, 0.0)
    await server.start()
    await server.stop()


def _bucket(filename: str) -> str:
    path = filename.replace("\\", "/")
    if "/asyncua/" in f"/{path}" or path.endswith("/asyncua"):
        return "asyncua"
    if "/opcua_server/" in f"/{path}":
        return "opcua_server"
    return "other"


def _report(stats: pstats.Stats, label: str) -> str:
    buffer = io.StringIO()
    stats.sort_stats("cumulative")
    stats.stream = buffer
    stats.print_stats(10)
    opcua_s = package_s = other_s = 0.0
    for (filename, _line, _name), (_cc, _nc, tottime, _ct, _callers) in stats.stats.items():
        bucket = _bucket(filename)
        if bucket == "opcua":
            opcua_s += tottime
        elif bucket == "opcua_server":
            package_s += tottime
        else:
            other_s += tottime
    header = (
        f"== {label} ==\n"
        f"tottime asyncua={opcua_s:.3f}s opcua_server={package_s:.3f}s other={other_s:.3f}s\n"
    )
    return header + buffer.getvalue()


def main() -> None:
    n = int(os.environ.get("OPCUA_BENCH_N", "5000"))
    out = Path(os.environ.get("OPCUA_PROFILE_DIR", "."))
    out.mkdir(parents=True, exist_ok=True)
    package_prof = out / "startup_profile.prof"
    bench_prof = out / "startup_bench_profile.prof"
    package_profiler = cProfile.Profile()
    package_profiler.enable()
    asyncio.run(package_startup(n))
    package_profiler.disable()
    package_profiler.dump_stats(str(package_prof))
    bench_profiler = cProfile.Profile()
    bench_profiler.enable()
    bench(n)
    bench_profiler.disable()
    bench_profiler.dump_stats(str(bench_prof))
    text = _report(pstats.Stats(package_profiler), f"package n={n}")
    text += "\n" + _report(pstats.Stats(bench_profiler), f"bench_startup_real n={n}")
    report = out / "startup_profile.txt"
    report.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {package_prof}")
    print(f"wrote {bench_prof}")


if __name__ == "__main__":
    main()
