# -*- coding: utf-8 -*-
"""Soak / tracemalloc helpers for Operación Engranaje Perfecto.

CI runs a short loop (PERF_SOAK_SECONDS, default 2). Plant soak is 24h / 7d:

    PERF_SOAK_SECONDS=86400 python -m unittest automation.tests.test_performance_soak

Acceptance (CA-1..CA-3, CA-6): RSS, OPC_MONITORED_COUNT and SAF_QUEUE_DEPTH
must stay flat; p99 set_value must not drift > 2× baseline. Collect samples
from GET /api/health/system during the run.
"""
from __future__ import annotations

import os
import time
import tracemalloc
import unittest
from datetime import datetime, timezone

from ..buffer import Buffer
from ..tags.cvt import CVT
from ..tags.tag import Tag


def _soak_seconds() -> float:
    try:
        return max(0.2, float(os.environ.get("PERF_SOAK_SECONDS", "2")))
    except ValueError:
        return 2.0


class TestPerformanceSoak(unittest.TestCase):
    def test_cvt_set_value_rss_proxy_stays_bounded(self):
        cvt = CVT()
        tags = []
        for i in range(32):
            tag = Tag(
                name=f"SOAK_{i}",
                unit="Pa",
                variable="Pressure",
                data_type="float",
                id=f"soak{i:04d}",
            )
            cvt._tags[tag.id] = tag
            cvt._index_tag(tag)
            tags.append(tag)

        buf = Buffer(size=64, roll="forward")
        tracemalloc.start()
        snapshot_start = tracemalloc.take_snapshot()
        deadline = time.monotonic() + _soak_seconds()
        writes = 0
        while time.monotonic() < deadline:
            now = datetime.now(timezone.utc)
            for tag in tags:
                cvt.set_value(id=tag.id, value=float(writes % 100), timestamp=now)
                buf(writes)
                writes += 1

        snapshot_end = tracemalloc.take_snapshot()
        stats = snapshot_end.compare_to(snapshot_start, "lineno")
        tag_growth = sum(
            item.size_diff
            for item in stats
            if "tags/tag.py" in (item.traceback[0].filename if item.traceback else "")
        )
        self.assertGreater(writes, 0)
        self.assertLess(tag_growth, 8 * 1024 * 1024)
        tracemalloc.stop()


if __name__ == "__main__":
    unittest.main()
