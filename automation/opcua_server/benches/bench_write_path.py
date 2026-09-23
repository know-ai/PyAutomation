"""Local p95 of a CVT write and a loopback field write. Not a 24 h soak."""

from __future__ import annotations

import statistics
import time
from types import SimpleNamespace


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]


def main() -> None:
    from automation.opcua_server.propagation import FieldPropagationRouter, new_transaction

    class _Value:
        def __init__(self) -> None:
            self.value = 0

        def set_value_fast(self, value, timestamp, **kwargs):
            self.value = value

    tag = SimpleNamespace(id="bench", opcua_address="opc.tcp://127.0.0.1:4840", node_namespace="ns=2;s=bench")
    value = _Value()

    def write_cvt():
        started = time.perf_counter()
        value.set_value_fast(1, None, source="external")
        return (time.perf_counter() - started) * 1000

    class _Writer:
        def write(self, url, node_id, payload) -> str:
            return "ok"

    router = FieldPropagationRouter(_Writer())

    def write_plc():
        started = time.perf_counter()
        router.route(tag, 1, new_transaction())
        return (time.perf_counter() - started) * 1000

    cvt = [write_cvt() for _ in range(200)]
    plc = [write_plc() for _ in range(200)]
    print(f"cvt_p50_ms {statistics.median(cvt):.4f} cvt_p95_ms {_p95(cvt):.4f}")
    print(f"plc_p50_ms {statistics.median(plc):.4f} plc_p95_ms {_p95(plc):.4f}")


if __name__ == "__main__":
    main()
