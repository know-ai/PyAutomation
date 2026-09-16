# -*- coding: utf-8 -*-
"""T-64 synthetic 1M-key index. SPEC-ISA18-2-CLOSURE-v3 P1-4. No real Alarm objects."""
from __future__ import annotations

import time
import tracemalloc
import unittest
from types import SimpleNamespace


def build_synthetic_index(n_keys: int) -> dict:
    idx = {}
    for i in range(n_keys):
        idx[f"TAG_{i:08d}"] = ()
    return idx


def _make_minimal_alarm():
    def _evaluate_condition(value):
        return SimpleNamespace(transition_needed=False, from_state="Normal", to_state="Normal")

    return SimpleNamespace(_evaluate_condition=_evaluate_condition)


class TestT64SyntheticScale(unittest.TestCase):
    def test_t64_on_tag_value_1m_keys(self):
        n_small = 1_000
        n_large = 1_000_000
        test_tag = "TAG_00000042"

        small = build_synthetic_index(n_small)
        small[test_tag] = (_make_minimal_alarm(),)
        small_stats = self._bench(small, test_tag)

        tracemalloc.start()
        large = build_synthetic_index(n_large)
        large[test_tag] = (_make_minimal_alarm(),)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        mem_mb = peak / (1024 * 1024)
        large_stats = self._bench(large, test_tag)

        self.assertLessEqual(large_stats["p99"], 50.0, f"p99={large_stats['p99']:.1f}µs")
        self.assertLessEqual(mem_mb, 100.0, f"dict memory {mem_mb:.1f} MB")
        if small_stats["p99"] > 0:
            growth = (large_stats["p99"] - small_stats["p99"]) / small_stats["p99"]
            self.assertLessEqual(growth, 0.10, f"p99 grew {growth:.1%} from 1k to 1M")
        print(
            f"T-64 N={n_large}: p50={large_stats['p50']:.1f}µs p99={large_stats['p99']:.1f}µs mem={mem_mb:.1f}MB"
        )

    def _bench(self, idx: dict, tag: str, rounds: int = 10_000) -> dict[str, float]:
        samples = []
        for _ in range(rounds):
            t0 = time.perf_counter_ns()
            alarms = idx.get(tag, ())
            for alarm in alarms:
                alarm._evaluate_condition(42.0)
            t1 = time.perf_counter_ns()
            samples.append((t1 - t0) / 1000.0)
        samples.sort()
        return {
            "p50": samples[len(samples) // 2],
            "p99": samples[int(len(samples) * 0.99)],
        }
