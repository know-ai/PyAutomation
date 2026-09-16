# -*- coding: utf-8 -*-
"""AlarmSubsystem facade. Context: API. Complexity: O(1) dispatch."""
from __future__ import annotations

from .chatter import ChatterDetector
from .clock import SystemClock
from .events import MemoryEventLogger
from .kpi import KPICollector, KPIComputer, KPIHistoryRepository
from .latching import LatchingPolicyRegistry
from .partition import PartitionManager
from .priority import PriorityManager
from .repository import MemoryAlarmRepository
from .retention import RetentionArchiver
from .suppression import SuppressionManager
from .suppression_cache import SuppressionCache


class AlarmSubsystem:
    """Facade: un punto de entrada P2. Context: API/COLD/BG. DIP en constructor."""

    def __init__(
        self,
        repo=None,
        events=None,
        clock=None,
        metrics_sink=None,
    ):
        self.clock = clock or SystemClock()
        self.repo = repo or MemoryAlarmRepository()
        self.events = events or MemoryEventLogger(self.clock)
        self.metrics_sink = metrics_sink
        self.priority = PriorityManager(self.repo, self.events, self.clock)
        self.chatter = ChatterDetector(self.clock, self.repo)
        cache = SuppressionCache(self.clock)
        self.suppression = SuppressionManager(cache, self.clock, self.events)
        self.kpi = KPICollector(self.clock)
        self.kpi_computer = KPIComputer()
        self.kpi_history = KPIHistoryRepository()
        self.archiver = RetentionArchiver()
        self.partitions = PartitionManager()
        self.latching = LatchingPolicyRegistry

    def compute_kpis(self, window_s: int = 3600) -> dict:
        """Context: API. Complexity: O(1000)."""
        snap = self.kpi_computer.compute(self.kpi, window_s=window_s)
        self.kpi_history.save(snap, ts=self.clock.now())
        return snap
