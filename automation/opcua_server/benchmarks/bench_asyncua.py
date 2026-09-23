"""Startup of 5000 tags on asyncua. Prints the measured p95. Does not invent a gate."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .bench_startup_real import bench


def main() -> None:
    n = int(os.environ.get("OPCUA_BENCH_N", "5000"))
    result = bench(n)
    out = Path(os.environ.get("OPCUA_BENCH_JSON", "bench_asyncua.json"))
    out.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
