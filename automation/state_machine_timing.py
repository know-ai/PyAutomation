# -*- coding: utf-8 -*-
"""Temporal decoupling for state machines: acquisition ≥ sampling ≥ execution.

Contract: specs/02-STATE-MACHINE-TEMPORAL-DECOUPLING.md
"""
from __future__ import annotations

import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from .buffer import Buffer

MIN_EXECUTION_INTERVAL_S = 0.01
MAX_BUFFER_POINTS = 10_000
DEFAULT_SCAN_TIME_MS = 1000

_LOGGER = logging.getLogger("pyautomation")
_metrics_lock = threading.Lock()
_metrics: dict[str, dict[str, float]] = defaultdict(dict)


class MachineConfigError(ValueError):
    """Rejected temporal configuration. API maps this to HTTP 400."""


class IBufferProvider(ABC):
    """Abstraction the state machine depends on (DIP). Sampling writes; execution reads."""

    @abstractmethod
    def ensure_tag(self, tag_name: str, maxlen: int, roll: str = "backward") -> None:
        raise NotImplementedError

    @abstractmethod
    def push(self, tag_name: str, value: Any, timestamp: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_buffer(self, tag_name: str):
        raise NotImplementedError

    @abstractmethod
    def as_dict(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def utilization_pct(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class DequeBufferProvider(IBufferProvider):
    """Thread-safe FIFO rings capped at MAX_BUFFER_POINTS."""

    def __init__(self):
        self._buffers: dict[str, Buffer] = {}
        self._lock = threading.Lock()

    def ensure_tag(self, tag_name: str, maxlen: int, roll: str = "backward") -> None:
        cap = _clamp_maxlen(maxlen)
        with self._lock:
            existing = self._buffers.get(tag_name)
            if existing is None:
                self._buffers[tag_name] = Buffer(size=cap, roll=roll)
                return
            if existing.size != cap:
                existing.size = cap

    def push(self, tag_name: str, value: Any, timestamp: Any) -> None:
        if value is None:
            return
        with self._lock:
            buf = self._buffers.get(tag_name)
        if buf is None:
            return
        buf((value, timestamp))

    def get_buffer(self, tag_name: str):
        with self._lock:
            return self._buffers.get(tag_name)

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._buffers)

    def utilization_pct(self) -> float:
        with self._lock:
            items = list(self._buffers.values())
        if not items:
            return 0.0
        ratios = []
        for buf in items:
            cap = max(int(buf.size), 1)
            ratios.append(100.0 * (len(buf) / cap))
        return sum(ratios) / len(ratios)

    def clear(self) -> None:
        with self._lock:
            rebuilt = {}
            for name, buf in self._buffers.items():
                rebuilt[name] = Buffer(size=buf.size, roll=buf.roll)
            self._buffers = rebuilt


def _clamp_maxlen(maxlen: int) -> int:
    return max(2, min(int(maxlen), MAX_BUFFER_POINTS))


def compute_sample_buffer_maxlen(
    execution_interval: float | None,
    sample_interval: float | None,
    buffer_size: int | None,
) -> int:
    user = max(int(buffer_size or 10), 2)
    if sample_interval and sample_interval > 0 and execution_interval and execution_interval > 0:
        window = max(2, int(math.ceil(execution_interval / sample_interval) * 2))
    else:
        window = user
    return _clamp_maxlen(max(user, window))


def samples_per_execution(execution_interval: float, sample_interval: float) -> int:
    if sample_interval <= 0:
        return 1
    return max(1, int(math.ceil(execution_interval / sample_interval)))


def coop_sleep(seconds: float) -> None:
    if seconds <= 0:
        return
    try:
        import gevent

        gevent.sleep(seconds)
    except Exception:
        time.sleep(seconds)


def record_sample_metrics(machine_name: str, cycle_s: float, lag_ms: float, utilization_pct: float) -> None:
    with _metrics_lock:
        slot = _metrics[machine_name]
        slot["SAMPLE_CYCLE_S"] = cycle_s
        slot["SAMPLE_LAG_MS"] = lag_ms
        slot["BUFFER_UTILIZATION_%"] = utilization_pct


def record_execution_metrics(machine_name: str, cycle_us: float) -> None:
    with _metrics_lock:
        _metrics[machine_name]["EXECUTION_CYCLE_US"] = cycle_us


def snapshot_timing_metrics() -> dict:
    with _metrics_lock:
        machines = dict(_metrics)
    if not machines:
        return {
            "SAMPLE_LAG_MS": 0.0,
            "EXECUTION_CYCLE_US": 0.0,
            "BUFFER_UTILIZATION_%": 0.0,
            "SAMPLE_LOOP_MACHINES": 0,
        }
    lags = [m.get("SAMPLE_LAG_MS", 0.0) for m in machines.values()]
    execs = [m.get("EXECUTION_CYCLE_US", 0.0) for m in machines.values()]
    utils = [m.get("BUFFER_UTILIZATION_%", 0.0) for m in machines.values()]
    return {
        "SAMPLE_LAG_MS": round(max(lags), 3),
        "EXECUTION_CYCLE_US": round(max(execs), 3),
        "BUFFER_UTILIZATION_%": round(max(utils), 2),
        "SAMPLE_LOOP_MACHINES": len(machines),
    }


def _tag_scan_seconds(tag) -> float:
    scan_ms = None
    getter = getattr(tag, "get_scan_time", None)
    if callable(getter):
        try:
            scan_ms = getter()
        except Exception:
            scan_ms = None
    if scan_ms is None:
        scan_ms = getattr(tag, "scan_time", None)
    try:
        scan_ms = float(scan_ms) if scan_ms is not None else DEFAULT_SCAN_TIME_MS
    except (TypeError, ValueError):
        scan_ms = DEFAULT_SCAN_TIME_MS
    if scan_ms <= 0:
        scan_ms = DEFAULT_SCAN_TIME_MS
    return scan_ms / 1000.0


def _subscribed_tags(machine) -> dict:
    getter = getattr(machine, "get_subscribed_tags", None)
    if not callable(getter):
        return {}
    try:
        return getter() or {}
    except Exception:
        return {}


def validate_temporal_config(machine, new_execution, new_sample, overrides) -> bool:
    """Golden rule: execution_interval >= sample_interval >= scan_time.

    ``new_sample is None`` is legacy mode (sample inside the execution tick).
    """
    execution = new_execution
    if execution is None:
        getter = getattr(machine, "get_interval", None)
        execution = getter() if callable(getter) else None
    try:
        execution = float(execution)
    except (TypeError, ValueError):
        raise MachineConfigError("execution_interval must be a number")
    classification = ""
    try:
        classification = str(getattr(getattr(machine, "classification", None), "value", "") or "").lower()
    except Exception:
        classification = ""
    is_acquisition = "data acquisition" in classification or machine.__class__.__name__ == "DAQ"
    if not is_acquisition and execution < MIN_EXECUTION_INTERVAL_S:
        raise MachineConfigError(
            f"execution_interval must be >= {MIN_EXECUTION_INTERVAL_S} s"
        )

    sample = new_sample
    if sample is not None:
        try:
            sample = float(sample)
        except (TypeError, ValueError):
            raise MachineConfigError("sample_interval must be a number or null")
        if sample <= 0:
            raise MachineConfigError("sample_interval must be greater than 0")
        if execution < sample:
            raise MachineConfigError(
                "execution_interval cannot be less than sample_interval"
            )

    overrides = overrides or {}
    for tag_name, process_type in _subscribed_tags(machine).items():
        tag = getattr(process_type, "tag", None) if process_type is not None else None
        if tag is None:
            continue
        name = getattr(tag, "name", tag_name) or tag_name
        if name in overrides and overrides[name] is not None:
            effective = overrides[name]
        elif tag_name in overrides and overrides[tag_name] is not None:
            effective = overrides[tag_name]
        else:
            effective = sample
        if effective is None:
            continue
        try:
            effective = float(effective)
        except (TypeError, ValueError):
            raise MachineConfigError(
                f"Sample interval for {name} must be a number"
            )
        tag_scan_sec = _tag_scan_seconds(tag)
        if effective < tag_scan_sec:
            raise MachineConfigError(
                f"Sample interval for {name} ({effective}s) "
                f"cannot be less than its acquisition scan_time ({tag_scan_sec}s)"
            )
    return True
