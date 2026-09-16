# -*- coding: utf-8 -*-
"""KPICollector + KPIComputer. Context: COLD record / API compute. O(1) / O(1000)."""
from __future__ import annotations

from collections import defaultdict, deque

from .clock import SystemClock
from .constants import _MAX_KPI_ACK_LATENCIES, _MAX_KPI_RATE_WINDOW, _PRIORITY_DEFAULT


class KPICollector:
    """Observer COLD. INV-104 record_* O(1). Compat T-76 record_transition."""

    def __init__(self, clock=None):
        self._clock = clock or SystemClock()
        self._activation_ts: deque = deque(maxlen=_MAX_KPI_RATE_WINDOW)
        self._standing_count = 0
        self._chattering_count = 0
        self._stale_count = 0
        self._priority_dist: dict[int, int] = defaultdict(int)
        self._ack_latencies_ms: deque = deque(maxlen=_MAX_KPI_ACK_LATENCIES)
        self.transitions_total = 0
        self.by_to_state: dict[str, int] = defaultdict(int)
        self.chatter_detected_total = 0

    def record_transition(self, to_state: str | None = None) -> None:
        """Context: COLD. Complexity: O(1). Compat P1."""
        self.transitions_total += 1
        if to_state:
            self.by_to_state[to_state] += 1

    def record_event(self, to_state: str | None = None) -> None:
        """Context: COLD. Complexity: O(1). INV-104."""
        self.record_transition(to_state)

    def record_activation(self, alarm=None) -> None:
        """Context: COLD. Complexity: O(1)."""
        self._activation_ts.append(self._clock.monotonic())
        prio = int(getattr(alarm, "priority", _PRIORITY_DEFAULT) or _PRIORITY_DEFAULT)
        self._priority_dist[prio] += 1

    def record_ack(self, alarm=None, latency_ms: float = 0.0) -> None:
        """Context: COLD. Complexity: O(1)."""
        self._ack_latencies_ms.append(float(latency_ms))
        prio = int(getattr(alarm, "priority", _PRIORITY_DEFAULT) or _PRIORITY_DEFAULT)
        if self._priority_dist[prio] > 0:
            self._priority_dist[prio] -= 1

    def record_standing_change(self, delta: int) -> None:
        self._standing_count = max(0, self._standing_count + int(delta))

    def record_chatter(self, delta: int) -> None:
        self._chattering_count = max(0, self._chattering_count + int(delta))
        if int(delta) > 0:
            self.chatter_detected_total += int(delta)

    def record_stale(self, delta: int) -> None:
        self._stale_count = max(0, self._stale_count + int(delta))


class KPIComputer:
    """Context: API. Complexity: O(1000) sort acotado. INV-115."""

    def compute(self, collector: KPICollector, window_s: int = 3600) -> dict:
        now = collector._clock.monotonic()
        cutoff = now - window_s
        n_recent = 0
        for ts in collector._activation_ts:
            if ts >= cutoff:
                n_recent += 1
        hours = max(window_s / 3600.0, 1e-9)
        rate = n_recent / hours
        latencies = sorted(collector._ack_latencies_ms)
        n = len(latencies)
        p50 = latencies[n // 2] if n else 0.0
        p95 = latencies[min(n - 1, int(n * 0.95))] if n else 0.0
        return {
            "alarm_rate": {"value": rate, "unit": "alarms/hour"},
            "standing_alarms": {"value": collector._standing_count},
            "chattering_alarms": {"value": collector._chattering_count},
            "stale_alarms": {"value": collector._stale_count},
            "priority_distribution": dict(collector._priority_dist),
            "operator_response_time": {"p50": p50, "p95": p95, "unit": "ms"},
        }


class KPIHistoryRepository:
    """Context: BG/API. Complejidad insert O(1). Cota 90 días en memoria de test."""

    def __init__(self, max_rows: int = 90 * 24):
        self._rows: deque = deque(maxlen=max_rows)

    def save(self, snapshot: dict, ts=None) -> None:
        self._rows.append({"ts": ts, "snapshot": snapshot})

    def get_history(self, limit: int = 1000) -> list:
        cap = min(int(limit), 1000)
        rows = list(self._rows)
        return rows[-cap:]
