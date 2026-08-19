# -*- coding: utf-8 -*-
"""ISA-18.2 BOOL alarms for node performance (CPU, disk, SAF, HTTP, …).

Tags and alarms live in the AlarmManager. The sampler only drives BOOL values.
Ack / shelve / unshelve stay on the existing alarm endpoints.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .connection_alarms import (
    _ensure_bool_alarm,
    _scoped_name,
    _write_disconnected,
    _app,
)
from .system_event_audit import clip, persist_system_event

_LOGGER = logging.getLogger("pyautomation.metrics")


@dataclass(frozen=True)
class PerfAlarmSpec:
    key: str
    snapshot_field: str
    tag_suffix: str
    alarm_suffix: str
    display_name: str
    unit: str
    tag_description: str
    alarm_description: str
    compare: str = "gte"


PERF_ALARM_SPECS: tuple[PerfAlarmSpec, ...] = (
    PerfAlarmSpec(
        key="cpu",
        snapshot_field="HOST_CPU_PERCENT",
        tag_suffix="SYS.PERF.CPU",
        alarm_suffix="ALM.PERF.CPU",
        display_name="CPU High",
        unit="%",
        tag_description="True when host CPU stays above the performance threshold",
        alarm_description="System · CPU high",
    ),
    PerfAlarmSpec(
        key="disk",
        snapshot_field="HOST_DISK_USED_PERCENT",
        tag_suffix="SYS.PERF.DISK",
        alarm_suffix="ALM.PERF.DISK",
        display_name="Disk High",
        unit="%",
        tag_description="True when host disk usage stays above the performance threshold",
        alarm_description="System · Disk high",
    ),
    PerfAlarmSpec(
        key="saf_queue",
        snapshot_field="SAF_QUEUE_DEPTH",
        tag_suffix="SYS.PERF.SAF_QUEUE",
        alarm_suffix="ALM.PERF.SAF_QUEUE",
        display_name="SAF Queue High",
        unit="",
        tag_description="True when the SAF journal queue stays above the performance threshold",
        alarm_description="System · SAF queue high",
    ),
    PerfAlarmSpec(
        key="saf_lag",
        snapshot_field="SAF_REPLICATION_LAG_MS",
        tag_suffix="SYS.PERF.SAF_LAG",
        alarm_suffix="ALM.PERF.SAF_LAG",
        display_name="SAF Lag High",
        unit="ms",
        tag_description="True when SAF replication lag stays above the performance threshold",
        alarm_description="System · SAF lag high",
    ),
    PerfAlarmSpec(
        key="metrics_age",
        snapshot_field="METRICS_AGE_MS",
        tag_suffix="SYS.PERF.METRICS_AGE",
        alarm_suffix="ALM.PERF.METRICS_AGE",
        display_name="Metrics Stale",
        unit="ms",
        tag_description="True when the metrics snapshot is older than the performance threshold",
        alarm_description="System · Metrics snapshot stale",
    ),
    PerfAlarmSpec(
        key="db_conn",
        snapshot_field="DB_ACTIVE_CONNECTIONS",
        tag_suffix="SYS.PERF.DB_CONN",
        alarm_suffix="ALM.PERF.DB_CONN",
        display_name="DB Connections High",
        unit="",
        tag_description="True when PostgreSQL backends stay above the performance threshold",
        alarm_description="System · Historian connections high",
    ),
    PerfAlarmSpec(
        key="http_5xx",
        snapshot_field="HTTP_5XX_1M",
        tag_suffix="SYS.PERF.HTTP_5XX",
        alarm_suffix="ALM.PERF.HTTP_5XX",
        display_name="HTTP 5xx High",
        unit="/min",
        tag_description="True when HTTP 5xx/min stays above the performance threshold",
        alarm_description="System · HTTP 5xx high",
    ),
)

_SPECS_BY_KEY = {spec.key: spec for spec in PERF_ALARM_SPECS}


def spec_for(key: str) -> PerfAlarmSpec | None:
    return _SPECS_BY_KEY.get(key)


def perf_tag_name(key: str) -> str:
    spec = _SPECS_BY_KEY[key]
    return _scoped_name(spec.tag_suffix)


def perf_alarm_name(key: str) -> str:
    spec = _SPECS_BY_KEY[key]
    return _scoped_name(spec.alarm_suffix)


def threshold_description(spec: PerfAlarmSpec, threshold: Any) -> str:
    unit = f" {spec.unit}" if spec.unit else ""
    return clip(f"{spec.alarm_description}. Triggers when {spec.snapshot_field} ≥ {threshold}{unit}.", 256)


def ensure_performance_alarms(config: dict[str, Any] | None = None) -> None:
    """Create all performance BOOL tags/alarms once. Never raises."""
    try:
        app = _app()
        cfg = config or {}
        for spec in PERF_ALARM_SPECS:
            threshold = cfg.get(f"perf_{spec.key}_threshold")
            _ensure_bool_alarm(
                app,
                tag_name=perf_tag_name(spec.key),
                alarm_name=perf_alarm_name(spec.key),
                tag_description=spec.tag_description,
                alarm_description=threshold_description(spec, threshold),
                display_name=spec.display_name,
            )
    except Exception:
        _LOGGER.error("Failed to ensure performance alarms", exc_info=True)


def set_performance_alarm(key: str, active: bool, *, value: Any = None, threshold: Any = None) -> bool:
    """Drive one performance BOOL alarm. Returns True if the BOOL flipped. Never raises."""
    try:
        spec = spec_for(key)
        if spec is None:
            return False
        tag_name = perf_tag_name(key)
        app = _app()
        tag = app.cvt.get_tag_by_name(tag_name)
        previous = False
        if tag is not None:
            try:
                previous = bool(getattr(tag.value, "value", False))
            except Exception:
                previous = False
        _write_disconnected(tag_name, bool(active))
        flipped = previous is not bool(active)
        if flipped:
            persist_system_event(
                message=f"Performance alarm {spec.alarm_suffix} {'activated' if active else 'cleared'}",
                description=clip(
                    f"value={value} threshold={threshold} field={spec.snapshot_field}",
                    256,
                ),
                classification="System",
                priority=2,
                criticity=3 if active else 1,
            )
        return flipped
    except Exception:
        _LOGGER.error("Failed to update performance alarm %s", key, exc_info=True)
        return False


def catalog_for_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    """O(1) copy-friendly catalog for GET /health/node."""
    alarms = []
    for spec in PERF_ALARM_SPECS:
        alarms.append(
            {
                "key": spec.key,
                "field": spec.snapshot_field,
                "enabled": bool(config.get(f"perf_{spec.key}_enabled", True)),
                "threshold": config.get(f"perf_{spec.key}_threshold"),
                "unit": spec.unit,
                "alarm": perf_alarm_name(spec.key),
                "tag": perf_tag_name(spec.key),
            }
        )
    return {
        "enabled": bool(config.get("perf_alarms_enabled", True)),
        "debounce_count": int(config.get("perf_debounce_count") or 3),
        "alarms": alarms,
    }
