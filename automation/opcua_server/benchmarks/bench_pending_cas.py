"""Pending performance measurements: tick allocations, reset and growth ratio.

Writes bench_pending_cas.json. The numbers are the evidence; a missed target stays in the file.
"""

from __future__ import annotations

import json
import os
import time
import tracemalloc
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from ..lifecycle import reset_structures
from ..metrics import OpcUaServerMetrics
from ..runtime import process_one_tick
from ..tests.test_growth_benchmarks import _p95_ms


class _Writeback:
    def clear(self) -> None:
        return None


def _tick_server(k: int):
    dirty = {f"tag_{i}" for i in range(k)}
    server = SimpleNamespace(
        _opcua_ready=True,
        _expose_queue=deque(maxlen=10_000),
        _expose_seen=set(),
        _dirty_tags=dirty,
        _dirty_alarms=set(),
        _dirty_engines=set(),
        _tick_counter=1,
        _watch_order=[],
        _watch_index=0,
        _last_touch={},
        _recent_ticks=deque(maxlen=5),
        metrics=OpcUaServerMetrics(),
        cvt=SimpleNamespace(get_tag_by_name=lambda name: None),
        publisher=None,
    )
    from ..dirty.per_tag import PerTagDirtyTracker

    server.tag_tracker = PerTagDirtyTracker({}, dirty)
    server.alarm_tracker = PerTagDirtyTracker({}, server._dirty_alarms)
    server.engine_tracker = PerTagDirtyTracker({}, server._dirty_engines)
    return server


def _tracemalloc_deltas(k: int = 20) -> tuple[int, int]:
    server = _tick_server(k)
    process_one_tick(server)
    server._dirty_tags.update(f"tag_{i}" for i in range(k))
    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    process_one_tick(server)
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    total = 0
    package = 0
    for stat in after.compare_to(before, "lineno"):
        if stat.size_diff <= 0:
            continue
        total += stat.size_diff
        filename = stat.traceback[0].filename.replace("\\", "/")
        if "/opcua_server/" in filename:
            package += stat.size_diff
    return package, total


def _reset_server(n: int):
    nodes = {f"t:_:tag_{i}": i for i in range(n)}
    return SimpleNamespace(
        server=None,
        publisher=None,
        cvt=SimpleNamespace(get_tag_by_name=lambda name: None),
        writeback=_Writeback(),
        metrics=OpcUaServerMetrics(),
        objects=None,
        builder=None,
        _cvt_exposer=None,
        _alarm_exposer=None,
        _engine_exposer=None,
        _tag_observers={},
        _ua_nodes=dict(nodes),
        _by_namespace=dict(nodes),
        _expose_queue=deque(maxlen=10_000),
        _expose_seen=set(),
        _dirty_tags=set(nodes),
        _dirty_alarms=set(),
        _dirty_engines=set(),
        _node_id_cache=dict(nodes),
        _access_cache={},
        _last_value={},
        _dead_bands={},
        _last_touch={},
        _watch_order=[],
        _name_to_canonical={},
        _watch_index=0,
        _tick_counter=0,
        _opcua_ready=False,
        _opcua_endpoint_up=False,
        _opcua_space_loaded=False,
        _namespace_idx=2,
    )


def _reset_ms(n: int) -> float:
    _reset_server(1)
    reset_structures(_reset_server(1))
    server = _reset_server(n)
    started = time.perf_counter()
    reset_structures(server)
    return (time.perf_counter() - started) * 1000.0


def main() -> None:
    package_bytes, total_bytes = _tracemalloc_deltas(20)
    reset_100 = _reset_ms(100)
    reset_10000 = _reset_ms(10000)
    tick_100 = _p95_ms(100)
    tick_10000 = _p95_ms(10000)
    ratio = tick_10000 / max(tick_100, 0.001)
    payload = {
        "CA-PERF-02_runtime_bytes": package_bytes,
        "CA-PERF-02_limit_bytes": 2048,
        "CA-PERF-03_total_bytes": total_bytes,
        "CA-PERF-03_limit_bytes": 10240,
        "CA-PERF-06_reset_ms_n100": reset_100,
        "CA-PERF-06_reset_ms_n10000": reset_10000,
        "CA-PERF-07_tick_p95_ms_n100": tick_100,
        "CA-PERF-07_tick_p95_ms_n10000": tick_10000,
        "CA-PERF-07_ratio": ratio,
        "CA-PERF-07_limit_ratio": 2.0,
    }
    out = Path(os.environ.get("OPCUA_PROFILE_DIR", ".")) / "bench_pending_cas.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
