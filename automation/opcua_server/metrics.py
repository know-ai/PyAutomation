"""Bounded metrics for the embedded OPC UA server."""

from __future__ import annotations

from collections import deque


class OpcUaServerMetrics:
    """Tick percentiles over a fixed window. No unbounded growth."""

    def __init__(self, window: int = 256) -> None:
        self._ticks: deque[float] = deque(maxlen=window)
        self.expose_failures = 0
        self.reconcile_passes = 0
        self.tick_budget_exceeded = 0
        self.last_expose_ms = 0.0
        self.last_reconcile_ms = 0.0
        self.dirty_tags_last_tick = 0
        self.expose_queue_high_water = 0
        self.dirty_tags_high_water = 0
        self.nodes_tags = 0
        self.nodes_alarms = 0
        self.nodes_engines = 0
        self.write_subscriptions = 0
        self.analog_item_fallbacks = 0
        self.engine_watchdog_recoveries = 0
        self.tag_watchdog_recoveries = 0
        self.lint_violations = 0
        self.external_writes = 0
        self.external_writes_rejected = 0
        self.external_writes_failed = 0
        self.multihop_writes = 0
        self.multihop_writes_failed = 0
        self.multihop_loops = 0
        self.propagation_depth_max = 0
        self.rate_limit_hits = 0
        self.oscillation_detected = 0
        self.rollbacks = 0
        self.access_level_changes = 0

    def observe_tick(self, elapsed_ms: float) -> None:
        self._ticks.append(float(elapsed_ms))

    def _percentile(self, pct: float) -> float:
        if not self._ticks:
            return 0.0
        ordered = sorted(self._ticks)
        index = int(round((len(ordered) - 1) * pct))
        return ordered[index]

    def note_queue(self, depth: int) -> None:
        if depth > self.expose_queue_high_water:
            self.expose_queue_high_water = depth

    def note_dirty(self, size: int) -> None:
        self.dirty_tags_last_tick = size
        if size > self.dirty_tags_high_water:
            self.dirty_tags_high_water = size

    def record_engine_recovery(self) -> None:
        """Increment the engine watchdog recovery counter. Complexity: O(1)."""
        self.engine_watchdog_recoveries += 1

    def record_tag_recovery(self) -> None:
        """Increment the tag watchdog recovery counter. Complexity: O(1)."""
        self.tag_watchdog_recoveries += 1

    def as_dict(
        self,
        *,
        ready: bool,
        namespace_idx: int,
        structures: dict,
        host: str = "0.0.0.0",
        port: int = 0,
        site: str = "Default",
        area: str = "Global",
    ) -> dict:
        """Public gauges, including the eleven access and multi-hop counters. Complexity: O(W log W) only for the percentile window."""
        from .identity import IdentityCounters

        nodes_total = (
            self.nodes_tags + self.nodes_alarms + self.nodes_engines
        )
        return {
            "OPCUA_SERVER_READY": bool(ready),
            "OPCUA_SERVER_HOST": str(host),
            "OPCUA_SERVER_PORT": int(port),
            "OPCUA_NAMESPACE_IDX": int(namespace_idx),
            "OPCUA_NODES_TOTAL": nodes_total,
            "OPCUA_NODES_TAGS": self.nodes_tags,
            "OPCUA_NODES_ALARMS": self.nodes_alarms,
            "OPCUA_NODES_ENGINES": self.nodes_engines,
            "OPCUA_EXPOSE_QUEUE_DEPTH": int(structures.get("expose_queue", 0)),
            "OPCUA_EXPOSE_FAILURES": self.expose_failures,
            "OPCUA_WRITE_SUBSCRIPTIONS_ACTIVE": self.write_subscriptions,
            "OPCUA_LAST_EXPOSE_MS": self.last_expose_ms,
            "OPCUA_DIRTY_TAGS_LAST_TICK": self.dirty_tags_last_tick,
            "OPCUA_RECONCILE_PASSES": self.reconcile_passes,
            "OPCUA_TICK_P50_MS": self._percentile(0.50),
            "OPCUA_TICK_P95_MS": self._percentile(0.95),
            "OPCUA_TICK_P99_MS": self._percentile(0.99),
            "OPCUA_TICK_BUDGET_EXCEEDED_TOTAL": self.tick_budget_exceeded,
            "OPCUA_RECONCILE_PASS_DURATION_MS": self.last_reconcile_ms,
            "OPCUA_EXPOSE_QUEUE_HIGH_WATER": self.expose_queue_high_water,
            "OPCUA_DIRTY_TAGS_CURRENT": int(structures.get("dirty_tags", 0)),
            "OPCUA_DIRTY_TAGS_HIGH_WATER": self.dirty_tags_high_water,
            "OPCUA_MEMORY_STRUCTURES": dict(structures),
            "OPCUA_ANALOG_ITEM_FALLBACKS_TOTAL": self.analog_item_fallbacks,
            "OPCUA_ENGINE_WATCHDOG_RECOVERIES_TOTAL": self.engine_watchdog_recoveries,
            "OPCUA_TAG_WATCHDOG_RECOVERIES_TOTAL": self.tag_watchdog_recoveries,
            "OPCUA_NODEID_COLLISIONS_TOTAL": IdentityCounters.collisions,
            "OPCUA_NODEID_RESERVED_PREFIX_REJECTED_TOTAL": IdentityCounters.reserved_rejected,
            "OPCUA_NODEID_LENGTH_TRUNCATED_TOTAL": IdentityCounters.length_truncated,
            "OPCUA_SITE_FOLDER": str(site),
            "OPCUA_AREA_FOLDER": str(area),
            "OPCUA_EXTERNAL_WRITES_TOTAL": self.external_writes,
            "OPCUA_EXTERNAL_WRITES_REJECTED_TOTAL": self.external_writes_rejected,
            "OPCUA_EXTERNAL_WRITES_FAILED_TOTAL": self.external_writes_failed,
            "OPCUA_MULTIHOP_WRITES_TOTAL": self.multihop_writes,
            "OPCUA_MULTIHOP_WRITES_FAILED_TOTAL": self.multihop_writes_failed,
            "OPCUA_MULTIHOP_WRITES_LOOP_DETECTED_TOTAL": self.multihop_loops,
            "OPCUA_PROPAGATION_DEPTH_MAX": self.propagation_depth_max,
            "OPCUA_RATE_LIMIT_HITS_TOTAL": self.rate_limit_hits,
            "OPCUA_OSCILLATION_DETECTED_TOTAL": self.oscillation_detected,
            "OPCUA_ROLLBACK_TOTAL": self.rollbacks,
            "OPCUA_ACCESS_LEVEL_CHANGES_TOTAL": self.access_level_changes,
        }
