# -*- coding: utf-8 -*-
"""O(1) alarm runtime: transition queue, counters, chatter, KPIs, latency.

SPEC-ISA18-2-CLOSURE-v3: DAS evaluates conditions and enqueues. Persistence,
SM.send, and on.alarm live on TransitionWorker. Queue has maxlen=100_000.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from threading import Event, Thread

from ..utils import Observer
from .p2.chatter import ChatterDetector
from .p2.kpi import KPICollector
from .p2.partition import PartitionManager
from .p2.priority import PriorityManager
from .p2.retention import RetentionArchiver
from .p2.suppression import SuppressionManager

_LOGGER = logging.getLogger("pyautomation")

KIND_ABNORMAL = "abnormal"
KIND_NORMAL = "normal"
KIND_EMIT = "emit"
KIND_UNSHELVE = "unshelve"

_MAX_QUEUE = 100_000
_LATENCY_WINDOW = 4096
_CHATTER_WINDOW_S = 60.0
_CHATTER_THRESHOLD = 10
_ACTIVE_CACHE_TTL_S = 1.0
_HOT_PATH_P99_BUDGET_US = 50.0
_WORKER_LAG_HIGH_MS = 5000.0
_LAG_SAMPLES = 1000


@dataclass(slots=True)
class TransitionEvent:
    alarm: Any
    kind: str
    enqueued_at: float


class LatencyWindow:
    """Ring buffer of microsecond samples. Percentiles are O(W log W) off hot path."""

    __slots__ = ("_samples", "_lock")

    def __init__(self):
        self._samples: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._lock = threading.Lock()

    def observe_us(self, value: float) -> None:
        with self._lock:
            self._samples.append(value)

    def percentiles(self) -> dict[str, float]:
        with self._lock:
            data = sorted(self._samples)
        if not data:
            return {"p50": 0.0, "p99": 0.0, "p999": 0.0}
        n = len(data)

        def _at(p: float) -> float:
            idx = min(n - 1, max(0, int(round((n - 1) * p))))
            return data[idx]

        return {"p50": _at(0.50), "p99": _at(0.99), "p999": _at(0.999)}


class AlarmTagObserver(Observer):
    """Tag observer that only runs Alarm.check_condition (no validate_types)."""

    def __init__(self, alarm):
        super().__init__()
        self.alarm = alarm

    def release(self):
        self.alarm = None

    def update(self):
        alarm = self.alarm
        tag = self._subject
        if alarm is None or tag is None:
            return
        timestamp = getattr(tag, "timestamp", None)
        if timestamp is None:
            return
        value = getattr(tag, "value", None)
        alarm.check_condition(
            getattr(value, "value", value) if value is not None else None,
            timestamp,
        )


class TransitionWorker(Thread):
    def __init__(self, runtime: "AlarmRuntime", interval_ms: int = 50):
        super().__init__(name="AlarmTransitionWorker", daemon=True)
        self.runtime = runtime
        self.interval_ms = interval_ms
        self.stop_event = Event()
        self._alive_flag = Event()
        self._last_heartbeat = time.monotonic()
        self._lag_samples: deque[float] = deque(maxlen=_LAG_SAMPLES)

    def stop(self):
        self.stop_event.set()

    def is_alive_recently(self, timeout_s: float = 5.0) -> bool:
        """INV-39: worker is live if the thread runs and heartbeat is fresh."""
        if self.stop_event.is_set():
            return False
        if not self.is_alive():
            return False
        return (time.monotonic() - self._last_heartbeat) < timeout_s

    def get_lag_stats(self) -> dict[str, float]:
        """INV-40: p50/p95/p99 of enqueue→process lag."""
        samples = list(self._lag_samples)
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}
        ordered = sorted(samples)
        n = len(ordered)
        return {
            "p50": ordered[min(n - 1, int(n * 0.50))],
            "p95": ordered[min(n - 1, int(n * 0.95))],
            "p99": ordered[min(n - 1, int(n * 0.99))],
            "count": n,
        }

    def run(self):
        self._alive_flag.set()
        self._last_heartbeat = time.monotonic()
        runtime = self.runtime
        while not self.stop_event.is_set():
            try:
                batch = runtime.dequeue_batch(max_size=100)
                if not batch:
                    self._last_heartbeat = time.monotonic()
                    self._alive_flag.set()
                    self.stop_event.wait(self.interval_ms / 1000.0)
                    continue
                for event in batch:
                    lag_ms = max(0.0, (time.monotonic() - event.enqueued_at) * 1000.0)
                    self._lag_samples.append(lag_ms)
                    runtime.process_event(event)
                self._last_heartbeat = time.monotonic()
                self._alive_flag.set()
            except Exception:
                _LOGGER.exception("ALARM.WORKER.CycleError")
                time.sleep(0.1)


class AlarmRuntime:
    """Process-wide O(1) structures for the alarm subsystem."""

    # INV-36: maxlen is not negotiable
    _PENDING_TRANSITIONS_MAXLEN = 100_000
    # INV-38: backlog warning threshold
    _PENDING_TRANSITIONS_WARN_THRESHOLD = 10_000

    def __init__(self):
        self._pending: deque[TransitionEvent] = deque(maxlen=self._PENDING_TRANSITIONS_MAXLEN)
        self._pending_lock = threading.Lock()  # cold path only — never taken in enqueue
        self._pending_max_seen = 0  # INV-50
        self._overflow_count = 0
        self._backlog_warned = False
        self._overflow_warned = False
        self._perf_flags: dict[str, dict[str, Any]] = {}
        self._not_empty = threading.Event()
        self.worker: TransitionWorker | None = None
        self.latency = LatencyWindow()
        self.record_latency = LatencyWindow()
        self.chatter = ChatterDetector()
        self.suppression = SuppressionManager()
        self.kpi = KPICollector()
        self.archiver = RetentionArchiver()
        self.priority = PriorityManager()
        self.partitions = PartitionManager()
        from .p2.kpi import KPIHistoryRepository

        self.kpi_history = KPIHistoryRepository()
        self.history_rows_total = 0
        self._count_active = 0
        self._count_by_state: dict[str, int] = defaultdict(int)
        self._annunciated: dict[str, Any] = {}
        self._active_cache: list = []
        self._active_cache_ts = 0.0
        self._last_lag_ms = 0.0
        self._last_worker_dead_log = 0.0

    @property
    def _pending_transitions(self) -> deque[TransitionEvent]:
        return self._pending

    @property
    def worker_alive(self) -> bool:
        return self.is_worker_alive_recently(timeout_s=5.0)

    def is_worker_alive_recently(self, timeout_s: float = 5.0) -> bool:
        worker = self.worker
        if worker is None:
            return False
        return worker.is_alive_recently(timeout_s=timeout_s)

    def start_worker(self) -> TransitionWorker:
        worker = self.worker
        if worker is not None and worker.is_alive() and not worker.stop_event.is_set():
            return worker
        if worker is not None:
            worker.stop()
            self._not_empty.set()
            worker.join(timeout=1.0)
        worker = TransitionWorker(self)
        self.worker = worker
        worker.start()
        return worker

    def stop_worker(self) -> None:
        worker = self.worker
        if worker is None:
            return
        worker.stop()
        self._not_empty.set()
        worker.join(timeout=2.0)
        self.worker = None

    def restart_worker(self) -> TransitionWorker:
        self.stop_worker()
        return self.start_worker()

    def enqueue(self, alarm, kind: str) -> bool:
        event = TransitionEvent(alarm=alarm, kind=kind, enqueued_at=time.monotonic())
        return self.enqueue_transition(event)

    def enqueue_transition(self, event: TransitionEvent) -> bool:
        """Hot path. O(1). Never blocks. Never takes a lock."""
        try:
            was_full = len(self._pending) == self._PENDING_TRANSITIONS_MAXLEN
            self._pending.append(event)
            n = len(self._pending)
            if n > self._pending_max_seen:
                self._pending_max_seen = n
            self._not_empty.set()
            if n < (self._PENDING_TRANSITIONS_WARN_THRESHOLD / 2):
                self._backlog_warned = False
            if n < self._PENDING_TRANSITIONS_MAXLEN:
                self._overflow_warned = False
            if n == self._PENDING_TRANSITIONS_MAXLEN:
                if was_full:
                    self._overflow_count += 1
                self._emit_overflow_alarm(n)
            elif n >= self._PENDING_TRANSITIONS_WARN_THRESHOLD:
                if not self._backlog_warned:
                    self._emit_backlog_warning(n)
                    self._backlog_warned = True
            return True
        except Exception:
            _LOGGER.exception("ALARM.QUEUE.EnqueueFailed")
            return False

    def _emit_overflow_alarm(self, depth: int) -> None:
        """INV-37: CRITICAL when maxlen is reached. Once until hysteresis."""
        if self._overflow_warned:
            return
        self._overflow_warned = True
        _LOGGER.critical(
            "ALARM.QUEUE.Overflow depth=%d max=%d total_overflows=%d",
            depth,
            self._PENDING_TRANSITIONS_MAXLEN,
            self._overflow_count,
        )
        self.raise_perf_alarm(
            name="ALM.PERF.ALARM_QUEUE_OVERFLOW",
            severity="CRITICAL",
            value=depth,
        )

    def _emit_backlog_warning(self, depth: int) -> None:
        """INV-38: WARNING above threshold, no drop."""
        _LOGGER.warning("ALARM.QUEUE.Backlog depth=%d", depth)
        self.raise_perf_alarm(
            name="ALM.PERF.ALARM_QUEUE_BACKLOG",
            severity="WARNING",
            value=depth,
        )

    def raise_perf_alarm(self, name: str, severity: str, value) -> None:
        """Flag only — never enqueue into the transition queue (would recurse)."""
        self._perf_flags[name] = {
            "severity": severity,
            "value": value,
            "ts": time.monotonic(),
        }

    def dequeue_batch(self, max_size: int = 100) -> list[TransitionEvent]:
        """Cold path. Lock is allowed here."""
        batch: list[TransitionEvent] = []
        with self._pending_lock:
            for _ in range(max(1, int(max_size))):
                try:
                    batch.append(self._pending.popleft())
                except IndexError:
                    break
        return batch

    def pop_event(self, timeout: float = 0.05) -> TransitionEvent | None:
        batch = self.dequeue_batch(max_size=1)
        if batch:
            return batch[0]
        self._not_empty.clear()
        self._not_empty.wait(timeout)
        batch = self.dequeue_batch(max_size=1)
        return batch[0] if batch else None

    def drain(self, limit: int = 10_000) -> int:
        processed = 0
        while processed < limit:
            batch = self.dequeue_batch(max_size=min(100, limit - processed))
            if not batch:
                break
            for event in batch:
                self.process_event(event)
                processed += 1
        return processed

    def drain_one_sync(self, event: TransitionEvent) -> None:
        self.process_event(event)

    def queue_depth(self) -> int:
        return len(self._pending)

    def count_active(self) -> int:
        return int(self._count_active)

    def count_by_state(self) -> dict[str, int]:
        return dict(self._count_by_state)

    def get_active_alarms(self, limit: int = 3, order_by: str | None = None) -> list:
        return self.active_alarms(limit=limit)

    def process_event(self, event: TransitionEvent) -> None:
        self._last_lag_ms = max(0.0, (time.monotonic() - event.enqueued_at) * 1000.0)
        alarm = event.alarm
        if alarm is None:
            return
        kind = event.kind
        started = time.perf_counter()
        try:
            if kind == KIND_ABNORMAL:
                alarm.abnormal_condition()
            elif kind == KIND_NORMAL:
                alarm.normal_condition()
            elif kind == KIND_EMIT:
                alarm._emit_runtime_state()
            elif kind == KIND_UNSHELVE:
                current = getattr(getattr(alarm, "tag", None), "value", None)
                alarm.unshelve(current_value=current)
        except Exception:
            import logging

            logging.getLogger("pyautomation").debug(
                "ALM.WORKER.event failed kind=%s", kind, exc_info=True
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.record_latency.observe_us(elapsed_ms * 1000.0)
        if kind in (KIND_ABNORMAL, KIND_NORMAL):
            to_state = getattr(alarm, "last_transition_to", None) or ""
            self.kpi.record_event(to_state)
            if to_state == "Unack Alarm":
                self.kpi.record_activation(alarm)
            elif to_state == "Ack Alarm":
                self.kpi.record_ack(alarm, 0.0)
            self.sync_alarm(alarm)

    def note_history_insert(self) -> None:
        self.history_rows_total += 1

    def sync_alarm(self, alarm) -> None:
        ident = getattr(alarm, "identifier", None)
        if not ident:
            return
        state = getattr(alarm, "state", None)
        name = getattr(state, "state", None) or "Normal"
        annunciate = str(getattr(state, "annunciate_status", "") or "")
        was_active = ident in self._annunciated
        is_active = annunciate.lower() == "annunciated"
        if is_active:
            self._annunciated[ident] = alarm
        else:
            self._annunciated.pop(ident, None)
        if is_active and not was_active:
            self._count_active += 1
        elif was_active and not is_active:
            self._count_active = max(0, self._count_active - 1)
        mnemonic = getattr(state, "mnemonic", None)
        if mnemonic in ("SHLVD", "DSUPR", "OOSRV"):
            self.suppression.update(ident, mnemonic)
        else:
            self.suppression.update(ident, None)
        if is_active:
            self._count_by_state[name] = self._count_by_state.get(name, 0)
        self._rebuild_state_counts()
        self._active_cache_ts = 0.0

    def _rebuild_state_counts(self) -> None:
        counts: dict[str, int] = defaultdict(int)
        for alarm in self._annunciated.values():
            state = getattr(getattr(alarm, "state", None), "state", None) or "Normal"
            counts[state] += 1
        self._count_by_state = counts

    def active_alarms(self, limit: int = 100) -> list:
        now = time.monotonic()
        if self._active_cache and (now - self._active_cache_ts) < _ACTIVE_CACHE_TTL_S:
            return self._active_cache[:limit]
        items = list(self._annunciated.values())

        def _key(alarm):
            stamp = getattr(alarm, "last_transition_ts", None) or getattr(alarm, "timestamp", None)
            return stamp or 0

        items.sort(key=_key, reverse=True)
        self._active_cache = items
        self._active_cache_ts = now
        return items[:limit]

    def snapshot(self) -> dict:
        lat = self.latency.percentiles()
        rec = self.record_latency.percentiles()
        p99 = lat["p99"]
        pending_depth = self.queue_depth()
        worker = self.worker
        worker_alive = self.is_worker_alive_recently(timeout_s=5.0)
        lag_stats = worker.get_lag_stats() if worker is not None else {
            "p50": 0.0,
            "p95": 0.0,
            "p99": round(self._last_lag_ms, 3),
            "count": 0,
        }
        violations = []
        if not worker_alive:
            violations.append("WORKER_DEAD")
        if pending_depth >= self._PENDING_TRANSITIONS_MAXLEN:
            violations.append("QUEUE_OVERFLOW")
        elif pending_depth >= self._PENDING_TRANSITIONS_WARN_THRESHOLD:
            violations.append("QUEUE_BACKLOG")
        if float(lag_stats.get("p99") or 0.0) > _WORKER_LAG_HIGH_MS:
            violations.append("WORKER_LAG_HIGH")
        if p99 > _HOT_PATH_P99_BUDGET_US:
            violations.append("HOT_PATH_O1_VIOLATION")
        status = "healthy"
        if "WORKER_DEAD" in violations or "QUEUE_OVERFLOW" in violations:
            status = "unhealthy"
        elif violations:
            status = "degraded"
        return {
            "status": status,
            "transition_worker_alive": worker_alive,
            "worker_lag_ms": lag_stats,
            "pending_depth": pending_depth,
            "pending_max_seen": self._pending_max_seen,
            "pending_overflow_count": self._overflow_count,
            "on_tag_value_p50_us": round(lat["p50"], 3),
            "on_tag_value_p99_us": round(p99, 3),
            "on_tag_value_p999_us": round(lat["p999"], 3),
            "transition_queue_depth": pending_depth,
            "transition_worker_lag_ms": round(float(lag_stats.get("p99") or self._last_lag_ms), 3),
            "active_count": self.count_active(),
            "count_by_state": self.count_by_state(),
            "history_rows_total": self.history_rows_total,
            "chatter_detected_total": self.kpi.chatter_detected_total,
            "record_transition_p99_ms": round(rec["p99"] / 1000.0, 3),
            "perf_flags": dict(self._perf_flags),
            "violations": violations,
        }


_RUNTIME: AlarmRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_alarm_runtime() -> AlarmRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        with _RUNTIME_LOCK:
            if _RUNTIME is None:
                _RUNTIME = AlarmRuntime()
    return _RUNTIME


def reset_alarm_runtime_for_tests() -> AlarmRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            _RUNTIME.stop_worker()
        _RUNTIME = AlarmRuntime()
        return _RUNTIME


def logging_warning_once(depth: int) -> None:
    """Kept for import compatibility. Backlog is emitted from enqueue_transition."""
    _LOGGER.warning("ALM.QUEUE.depth=%s exceeds 10000", depth)
