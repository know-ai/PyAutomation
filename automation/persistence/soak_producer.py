# -*- coding: utf-8 -*-
"""T-01 soak producer — runs in a child process until SIGKILL."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from .config import SafConfig
from .journal import JournalWriter
from .records import PersistableRecord


def produce(journal_path: str, count_path: str, duration_s: float, n_tags: int, hz: float) -> int:
    config = SafConfig(
        journal_path=journal_path,
        ring_maxsize=2_000_000,
        tag_batch_size=1000,
        tag_flush_interval_s=0.005,
        max_disk_bytes=20 * 1024 * 1024 * 1024,
    )
    journal = JournalWriter(config)
    journal.start()
    tags = [f"soak_{index:04d}" for index in range(n_tags)]
    period = 1.0 / max(1.0, hz)
    generated = 0
    deadline = time.monotonic() + float(duration_s)
    with open(count_path, "w", encoding="utf-8") as counter:
        while time.monotonic() < deadline:
            tick_start = time.monotonic()
            stamp = datetime.now(timezone.utc)
            batch = [
                PersistableRecord.tag_sample(name, generated + offset, stamp)
                for offset, name in enumerate(tags)
            ]
            journal.append_many(batch)
            generated += len(batch)
            counter.seek(0)
            counter.write(str(generated))
            counter.truncate()
            counter.flush()
            os.fsync(counter.fileno())
            elapsed = time.monotonic() - tick_start
            remaining = period - elapsed
            if remaining > 0:
                time.sleep(remaining)
    journal.flush_sync()
    journal.stop()
    return generated


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    journal_path, count_path = args[0], args[1]
    duration_s = float(args[2])
    n_tags = int(args[3])
    hz = float(args[4])
    produce(journal_path, count_path, duration_s, n_tags, hz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
