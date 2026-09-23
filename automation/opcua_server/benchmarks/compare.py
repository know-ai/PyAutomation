"""Compare a bench JSON against the closure gates. Exit 1 when a gate fails."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .bench_startup_real import STARTUP_GATE_MS

GATES = {
    "startup_real": ("p95_ms", float(STARTUP_GATE_MS)),
    "update_real": ("p95_ms", 5.0),
    "expose_real": ("p95_ms", 100.0),
    "memory_real": ("rss_mb", 300.0),
}


def main(path: str = "bench.json") -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    failed = False
    for row in payload:
        gate = GATES.get(row["name"])
        if gate is None:
            continue
        field, limit = gate
        value = float(row[field])
        if value > limit:
            print(f"FAIL {row['name']} {field}={value} limit={limit}")
            failed = True
        else:
            print(f"OK {row['name']} {field}={value} limit={limit}")
    return 1 if failed else 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "bench.json"
    raise SystemExit(main(target))
