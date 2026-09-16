# -*- coding: utf-8 -*-
"""PartitionManager. Context: BG. Complexity: O(1) DDL. 13 rolling months."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .constants import _PARTITION_DROP_YEARS, _PARTITION_FUTURE_MONTHS, _PARTITION_PAST_MONTHS


def _month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


class PartitionManager:
    """Context: BG. Complexity: O(1) por DDL. Sidecar rolling; no corta la tabla live sin backup."""

    def __init__(self, executor: Callable[[str], None] | None = None):
        self._executor = executor
        self.partitions: dict[str, tuple[int, int]] = {}
        self.dropped: list[str] = []
        self.last_ensure = 0

    def _name(self, year: int, month: int) -> str:
        return f"alarmsummary_p_{year:04d}_{month:02d}"

    def ensure(self, now: datetime | None = None) -> int:
        """Context: BG. Complexity: O(1) amortizado (13 nombres). T-177."""
        now = now or datetime.now(timezone.utc)
        created = 0
        start = -_PARTITION_PAST_MONTHS
        end = _PARTITION_FUTURE_MONTHS
        for delta in range(start, end + 1):
            y, m = _month_add(now.year, now.month, delta)
            name = self._name(y, m)
            if name in self.partitions:
                continue
            sql = (
                f"CREATE TABLE IF NOT EXISTS {name} "
                f"(LIKE alarmsummary INCLUDING DEFAULTS)"
            )
            if self._executor:
                try:
                    self._executor(sql)
                except Exception:
                    pass
            self.partitions[name] = (y, m)
            created += 1
        self.last_ensure = created
        return created

    def drop_old(self, now: datetime | None = None) -> int:
        """Context: BG. Complexity: O(P) P acotado. T-178 > 7 años."""
        now = now or datetime.now(timezone.utc)
        cutoff_y, cutoff_m = _month_add(now.year, now.month, -(_PARTITION_DROP_YEARS * 12))
        removed = 0
        for name, (y, m) in list(self.partitions.items()):
            if (y, m) < (cutoff_y, cutoff_m):
                if self._executor:
                    try:
                        self._executor(f"DROP TABLE IF EXISTS {name}")
                    except Exception:
                        pass
                self.partitions.pop(name, None)
                self.dropped.append(name)
                removed += 1
        return removed

    def rolling_count(self) -> int:
        return len(self.partitions)
