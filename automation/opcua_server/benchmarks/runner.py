"""Percentiles for the OPC UA benches. O(samples log samples) once per run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class BenchResult:
    name: str
    n: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    rss_mb: float
    nodes_total: int


def percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = int(round((len(ordered) - 1) * pct))
    return ordered[index]


def summarize(name: str, n: int, samples_s: list[float], rss_mb: float, nodes_total: int) -> BenchResult:
    millis = [item * 1000.0 for item in samples_s]
    return BenchResult(
        name=name,
        n=n,
        p50_ms=percentile(millis, 0.50),
        p95_ms=percentile(millis, 0.95),
        p99_ms=percentile(millis, 0.99),
        rss_mb=rss_mb,
        nodes_total=nodes_total,
    )


def dump(path: str, results: list[BenchResult]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([asdict(item) for item in results], handle, indent=2)
