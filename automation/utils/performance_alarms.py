# -*- coding: utf-8 -*-
"""ISA-18.2 BOOL alarms for node performance (CPU, disk, SAF, HTTP, …).

Tags and alarms live in the AlarmManager. The sampler only drives BOOL values.
Ack / shelve / unshelve stay on the existing alarm endpoints.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from .connection_alarms import (
    _ensure_bool_alarm,
    _scoped_name,
    _write_disconnected,
    _app,
    scoped_display_name,
)
from .system_event_audit import clip, persist_system_event

_LOGGER = logging.getLogger("pyautomation.metrics")

# Debounce repeated "historian offline" warnings (sampler may call every few seconds).
_HISTORIAN_OFFLINE_LOG_INTERVAL_S = 3600.0
_STARTUP_GRACE_S = 15.0
_process_start_mono: float = time.monotonic()
_last_historian_offline_log_mono: float = 0.0
_historian_was_offline: bool = False


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
    PerfAlarmSpec(
        key="field_stale",
        snapshot_field="FIELD_STALE",
        tag_suffix="SYS.PERF.FIELD_STALE",
        alarm_suffix="ALM.PERF.FIELD_STALE",
        display_name="Field Stale",
        unit="",
        tag_description="True when a field tag age exceeds 3× scan_time (floor 5 s), even if Socket.IO is connected",
        alarm_description="System · Field values stale",
    ),
    PerfAlarmSpec(
        key="saf_deadletter",
        snapshot_field="SAF_DEADLETTER_COUNT",
        tag_suffix="SYS.PERF.SAF_DEADLETTER",
        alarm_suffix="ALM.PERF.SAF_DEADLETTER",
        display_name="SAF Dead-letter",
        unit="",
        tag_description="True when poison journal rows have been dead-lettered after repeated failed drains",
        alarm_description="System · SAF dead-letter",
    ),
    PerfAlarmSpec(
        key="hub_lag",
        snapshot_field="HUB_LAG_MS",
        tag_suffix="SYS.PERF.HUB_LAG",
        alarm_suffix="ALM.PERF.HUB_LAG",
        display_name="Hub Lag High",
        unit="ms",
        tag_description="True when the gevent event-loop lag stays above the performance threshold",
        alarm_description="System · Hub event-loop lag",
    ),
    PerfAlarmSpec(
        key="saf_shed",
        snapshot_field="SAF_SHED",
        tag_suffix="SYS.PERF.SAF_SHED",
        alarm_suffix="ALM.PERF.SAF_SHED",
        display_name="SAF History Shed",
        unit="",
        tag_description="True when analog tag history is being shed to protect alarm/event durability",
        alarm_description="System · SAF analog shed",
    ),
    PerfAlarmSpec(
        key="saf_ingest",
        snapshot_field="SAF_INGEST_AGE_MS",
        tag_suffix="SYS.PERF.SAF_INGEST",
        alarm_suffix="ALM.PERF.SAF_INGEST",
        display_name="SAF Ingest Stale",
        unit="ms",
        tag_description="True when DAQ is running but no new domain=tag journal row arrived",
        alarm_description="System · SAF ingest heartbeat lost",
    ),
    PerfAlarmSpec(
        key="saf_rate",
        snapshot_field="SAF_RATE_MISMATCH",
        tag_suffix="SYS.PERF.SAF_RATE",
        alarm_suffix="ALM.PERF.SAF_RATE",
        display_name="SAF Drain Lagging",
        unit="",
        tag_description="True when SAF drain rate stays below ingest rate with the queue already above Low",
        alarm_description="System · SAF drain slower than ingest",
    ),
    PerfAlarmSpec(
        key="ssd",
        snapshot_field="HOST_SSD_ALARM",
        tag_suffix="SYS.PERF.SSD",
        alarm_suffix="ALM.PERF.SSD",
        display_name="SSD SMART",
        unit="",
        tag_description="True when SSD wear or temperature exceeds AUTOMATION_SSD_WEAR_WARN / AUTOMATION_SSD_TEMP_WARN",
        alarm_description="System · SSD SMART warning",
    ),
    PerfAlarmSpec(
        key="ntp",
        snapshot_field="HOST_NTP_ABS_OFFSET_MS",
        tag_suffix="SYS.PERF.NTP",
        alarm_suffix="ALM.PERF.NTP",
        display_name="NTP Offset High",
        unit="ms",
        tag_description="True when abs(HOST_NTP_OFFSET_MS) stays above the early-warning threshold (default 100 ms)",
        alarm_description="System · NTP offset high",
    ),
    PerfAlarmSpec(
        key="node_down",
        snapshot_field="HOST_PEER_DOWN",
        tag_suffix="SYS.PERF.NODE_DOWN",
        alarm_suffix="ALM.PERF.NODE_DOWN",
        display_name="Peer Node Down",
        unit="",
        tag_description="True when another registered edge has last_seen older than AUTOMATION_PEER_STALE_S",
        alarm_description="System · peer edge heartbeat lost",
    ),
)

_SPECS_BY_KEY = {spec.key: spec for spec in PERF_ALARM_SPECS}


def _in_startup_grace() -> bool:
    return (time.monotonic() - _process_start_mono) < _STARTUP_GRACE_S


def reset_startup_grace_for_tests(*, elapsed_s: float | None = None) -> None:
    """Test helper: restart grace, or pretend ``elapsed_s`` already passed."""
    global _process_start_mono, _last_historian_offline_log_mono, _historian_was_offline
    now = time.monotonic()
    if elapsed_s is None:
        _process_start_mono = now
    else:
        _process_start_mono = now - max(0.0, float(elapsed_s))
    _last_historian_offline_log_mono = 0.0
    _historian_was_offline = False


def spec_for(key: str) -> PerfAlarmSpec | None:
    return _SPECS_BY_KEY.get(key)


def perf_tag_name(key: str) -> str:
    spec = _SPECS_BY_KEY[key]
    return _scoped_name(spec.tag_suffix)


def perf_alarm_name(key: str) -> str:
    spec = _SPECS_BY_KEY[key]
    return _scoped_name(spec.alarm_suffix)


def _format_threshold_value(threshold: Any, unit: str) -> str:
    """Render a numeric threshold for alarm text; never emit the literal 'None'."""
    value = threshold
    if value is None or (isinstance(value, str) and value.strip().lower() in ("", "none", "null")):
        value = ""
    try:
        num = float(value)
        text = str(int(num)) if num == int(num) else str(num)
    except (TypeError, ValueError):
        text = str(value).strip() if value is not None else ""
    if not text or text.lower() in ("none", "null"):
        text = "?"
    unit = unit or ""
    if unit and text.endswith(unit):
        return text
    return f"{text}{unit}" if unit else text


def threshold_description(spec: PerfAlarmSpec, threshold: Any = None) -> str:
    """Canonical English description; HMI translates by alarm name + this pattern."""
    from .performance_alarm_config import _DEFAULTS

    resolved = threshold
    if resolved is None or (isinstance(resolved, str) and resolved.strip().lower() in ("", "none", "null")):
        resolved = _DEFAULTS.get(f"perf_{spec.key}_threshold")
    thresh = _format_threshold_value(resolved, spec.unit or "")
    return clip(
        f"{spec.alarm_description}. Triggers when {spec.snapshot_field} ≥ {thresh}.",
        256,
    )


_DB_DATA_TYPES = {"bool": "boolean", "int": "integer", "str": "string"}


def _unwrap_engine(result: Any) -> Any:
    if isinstance(result, dict) and "response" in result:
        return result.get("response")
    return result


def _historian_connected(app) -> bool:
    checker = getattr(app, "is_db_connected", None)
    try:
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def _perf_spec_for_tag_name(tag_name: str) -> PerfAlarmSpec | None:
    for spec in PERF_ALARM_SPECS:
        if perf_tag_name(spec.key) == tag_name:
            return spec
    return None


def _base_display_name(tag_name: str) -> str:
    parts = [part for part in (tag_name or "").split(".") if part]
    return parts[-1] if parts else tag_name


def _persist_performance_tag(app, tag) -> bool:
    """Insert/update one SYS.PERF.* tag in the central Tags table. Never raises."""
    if tag is None:
        return False
    original_type = getattr(tag, "data_type", None)
    original_display = getattr(tag, "display_name", None)
    try:
        mapped = _DB_DATA_TYPES.get(str(original_type or ""), original_type)
        tag.data_type = mapped
        spec = _perf_spec_for_tag_name(tag.name)
        tag.display_name = scoped_display_name(spec.display_name) if spec else _base_display_name(tag.name)
        app.logger_engine.set_tag(tag=tag)
        row = _unwrap_engine(app.logger_engine.get_tag_by_name(tag.name))
        return row is not None
    except Exception as exc:
        from .db_io import is_stale_historian_handle, log_historian_link_issue

        if is_stale_historian_handle(exc):
            log_historian_link_issue(
                _LOGGER,
                exc,
                where="persist_performance_tag",
                action=getattr(tag, "name", "?"),
            )
        else:
            _LOGGER.warning(
                "Performance tag %s not yet in historian Tags (will retry); "
                "alarm stays active in CVT/local catalog — no operator impact",
                getattr(tag, "name", "?"),
            )
            _LOGGER.debug("persist performance tag detail", exc_info=True)
        return False
    finally:
        try:
            tag.data_type = original_type
            tag.display_name = original_display
        except Exception:
            pass


def performance_tags_persisted(app=None) -> bool:
    """True when all SYS.PERF.* tags exist in the historian Tags table."""
    try:
        app = app or _app()
        if not _historian_connected(app):
            return False
        for spec in PERF_ALARM_SPECS:
            row = _unwrap_engine(app.logger_engine.get_tag_by_name(perf_tag_name(spec.key)))
            if row is None:
                return False
        return True
    except Exception:
        _LOGGER.debug("performance tag catalog lookup failed", exc_info=True)
        return False


def ensure_performance_alarms(config: dict[str, Any] | None = None) -> bool:
    """Create BOOL tags/alarms in CVT and persist them to Tags when the historian is up.

    Always refreshes alarm descriptions from the active thresholds so offline catalog
    and remote historian stay aligned when operators change PERF settings.

    Returns True only if the SYS.PERF.* rows exist in the central database.
    Never raises. Safe to call on every sampler tick until persisted.
    """
    try:
        app = _app()
        from .performance_alarm_config import load_performance_alarm_config

        if config is None:
            try:
                raw = app.get_app_config() if hasattr(app, "get_app_config") else {}
            except Exception:
                raw = {}
            cfg = load_performance_alarm_config(raw)
        else:
            # Merge partial/empty payloads with defaults (never leave threshold as None).
            cfg = load_performance_alarm_config(config)
        global _last_historian_offline_log_mono, _historian_was_offline
        for spec in PERF_ALARM_SPECS:
            threshold = cfg.get(f"perf_{spec.key}_threshold")
            tag_name = perf_tag_name(spec.key)
            _ensure_bool_alarm(
                app,
                tag_name=tag_name,
                alarm_name=perf_alarm_name(spec.key),
                tag_description=spec.tag_description,
                alarm_description=threshold_description(spec, threshold),
                display_name=scoped_display_name(spec.display_name),
            )
        if not _historian_connected(app):
            if _in_startup_grace():
                _LOGGER.debug(
                    "Historian not ready during startup grace (%.0fs); "
                    "performance tags deferred without operator warning",
                    _STARTUP_GRACE_S,
                )
                return False
            now = time.monotonic()
            if (
                not _historian_was_offline
                or (now - _last_historian_offline_log_mono) >= _HISTORIAN_OFFLINE_LOG_INTERVAL_S
            ):
                _LOGGER.warning(
                    "Historian offline; performance tags will persist on reconnect "
                    "(this reminder at most once per hour while still disconnected)"
                )
                _last_historian_offline_log_mono = now
            _historian_was_offline = True
            return False
        if _historian_was_offline:
            _historian_was_offline = False
            _last_historian_offline_log_mono = 0.0
        ok = True
        for spec in PERF_ALARM_SPECS:
            tag = app.cvt.get_tag_by_name(perf_tag_name(spec.key))
            if not _persist_performance_tag(app, tag):
                ok = False
        if ok:
            _LOGGER.info("Performance tags persisted to historian (%s)", len(PERF_ALARM_SPECS))
        else:
            # Sampler retries until complete. CVT + local catalog already hold the alarms.
            _LOGGER.info(
                "Performance tags not fully mirrored to historian Tags yet; "
                "retrying on next sampler tick. No data loss — PERF alarms remain in CVT/local catalog."
            )
        return ok
    except Exception:
        _LOGGER.warning("Failed to ensure performance alarms; will retry", exc_info=True)
        return False


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
