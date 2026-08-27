# -*- coding: utf-8 -*-
"""Performance-alarm thresholds: app_config.json (HMI) > env bootstrap > defaults."""
from __future__ import annotations

import os
from typing import Any

# Spec CA-PERF defaults. Clamp ranges keep operator input from becoming nonsense.
_DEFAULTS: dict[str, Any] = {
    "perf_alarms_enabled": True,
    "perf_debounce_count": 3,
    "perf_cpu_enabled": True,
    "perf_cpu_threshold": 85.0,
    "perf_disk_enabled": True,
    "perf_disk_threshold": 90.0,
    "perf_saf_queue_enabled": True,
    "perf_saf_queue_threshold": 5000.0,
    "perf_saf_lag_enabled": True,
    "perf_saf_lag_threshold": 10000.0,
    "perf_metrics_age_enabled": True,
    "perf_metrics_age_threshold": 30000.0,
    "perf_db_conn_enabled": True,
    "perf_db_conn_threshold": 10.0,
    "perf_http_5xx_enabled": True,
    "perf_http_5xx_threshold": 5.0,
    "perf_field_stale_enabled": True,
    "perf_field_stale_threshold": 1.0,
    "perf_saf_deadletter_enabled": True,
    "perf_saf_deadletter_threshold": 1.0,
    "perf_hub_lag_enabled": True,
    "perf_hub_lag_threshold": 2000.0,
    "perf_saf_shed_enabled": True,
    "perf_saf_shed_threshold": 1.0,
    "perf_saf_ingest_enabled": True,
    "perf_saf_ingest_threshold": 15000.0,
    "perf_saf_rate_enabled": True,
    "perf_saf_rate_threshold": 1.0,
}

_ENV_MAP = {
    "AUTOMATION_PERF_ALARMS_ENABLED": ("perf_alarms_enabled", bool),
    "AUTOMATION_PERF_DEBOUNCE_COUNT": ("perf_debounce_count", int),
    "AUTOMATION_PERF_CPU_THRESHOLD": ("perf_cpu_threshold", float),
    "AUTOMATION_PERF_DISK_THRESHOLD": ("perf_disk_threshold", float),
    "AUTOMATION_PERF_SAF_QUEUE_THRESHOLD": ("perf_saf_queue_threshold", float),
    "AUTOMATION_PERF_SAF_LAG_THRESHOLD": ("perf_saf_lag_threshold", float),
    "AUTOMATION_PERF_METRICS_AGE_THRESHOLD": ("perf_metrics_age_threshold", float),
    "AUTOMATION_PERF_DB_CONN_THRESHOLD": ("perf_db_conn_threshold", float),
    "AUTOMATION_PERF_HTTP_5XX_THRESHOLD": ("perf_http_5xx_threshold", float),
    "AUTOMATION_PERF_FIELD_STALE_THRESHOLD": ("perf_field_stale_threshold", float),
    "AUTOMATION_PERF_SAF_DEADLETTER_THRESHOLD": ("perf_saf_deadletter_threshold", float),
    "AUTOMATION_PERF_HUB_LAG_THRESHOLD": ("perf_hub_lag_threshold", float),
    "AUTOMATION_PERF_SAF_SHED_THRESHOLD": ("perf_saf_shed_threshold", float),
    "AUTOMATION_PERF_SAF_INGEST_THRESHOLD": ("perf_saf_ingest_threshold", float),
    "AUTOMATION_PERF_SAF_RATE_THRESHOLD": ("perf_saf_rate_threshold", float),
}

_BOOL_KEYS = {
    "perf_alarms_enabled",
    "perf_cpu_enabled",
    "perf_disk_enabled",
    "perf_saf_queue_enabled",
    "perf_saf_lag_enabled",
    "perf_metrics_age_enabled",
    "perf_db_conn_enabled",
    "perf_http_5xx_enabled",
    "perf_field_stale_enabled",
    "perf_saf_deadletter_enabled",
    "perf_hub_lag_enabled",
    "perf_saf_shed_enabled",
    "perf_saf_ingest_enabled",
    "perf_saf_rate_enabled",
}

_CLAMP: dict[str, tuple[float, float]] = {
    "perf_debounce_count": (1, 12),
    "perf_cpu_threshold": (1, 100),
    "perf_disk_threshold": (1, 100),
    "perf_saf_queue_threshold": (1, 10_000_000),
    "perf_saf_lag_threshold": (1, 86_400_000),
    "perf_metrics_age_threshold": (1000, 600_000),
    "perf_db_conn_threshold": (1, 10_000),
    "perf_http_5xx_threshold": (1, 100_000),
    "perf_field_stale_threshold": (1, 1),
    "perf_saf_deadletter_threshold": (1, 10_000_000),
    "perf_hub_lag_threshold": (100, 60_000),
    "perf_saf_shed_threshold": (1, 1),
    "perf_saf_ingest_threshold": (1000, 600_000),
    "perf_saf_rate_threshold": (1, 1),
}

_CAMEL_TO_SNAKE = {
    "enabled": "perf_alarms_enabled",
    "debounceCount": "perf_debounce_count",
    "cpuThreshold": "perf_cpu_threshold",
    "diskThreshold": "perf_disk_threshold",
    "safQueueThreshold": "perf_saf_queue_threshold",
    "safLagThreshold": "perf_saf_lag_threshold",
    "metricsAgeThreshold": "perf_metrics_age_threshold",
    "dbConnThreshold": "perf_db_conn_threshold",
    "http5xxThreshold": "perf_http_5xx_threshold",
    "fieldStaleThreshold": "perf_field_stale_threshold",
    "safDeadletterThreshold": "perf_saf_deadletter_threshold",
    "hubLagThreshold": "perf_hub_lag_threshold",
    "safShedThreshold": "perf_saf_shed_threshold",
    "safIngestThreshold": "perf_saf_ingest_threshold",
    "safRateThreshold": "perf_saf_rate_threshold",
}

ALARM_KEYS = (
    "cpu",
    "disk",
    "saf_queue",
    "saf_lag",
    "metrics_age",
    "db_conn",
    "http_5xx",
    "field_stale",
    "saf_deadletter",
    "hub_lag",
    "saf_shed",
    "saf_ingest",
    "saf_rate",
)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(key: str, value: float) -> float:
    lo, hi = _CLAMP.get(key, (value, value))
    return max(lo, min(hi, value))


def normalize_payload(raw: dict | None) -> dict[str, Any]:
    """Accept snake_case, camelCase spec keys, or nested ``alarms`` list."""
    payload: dict[str, Any] = {}
    data = dict(raw or {})
    for camel, snake in _CAMEL_TO_SNAKE.items():
        if camel in data and snake not in data:
            data[snake] = data[camel]
    nested = data.get("performanceAlarms")
    if isinstance(nested, dict):
        data.update(normalize_payload(nested))
    for key in _DEFAULTS:
        if key in data and data[key] is not None:
            payload[key] = data[key]
    alarms = data.get("alarms")
    if isinstance(alarms, list):
        for item in alarms:
            if not isinstance(item, dict):
                continue
            name = str(item.get("key") or "").strip().lower().replace("-", "_")
            if name not in ALARM_KEYS:
                continue
            if "enabled" in item:
                payload[f"perf_{name}_enabled"] = item["enabled"]
            if "threshold" in item:
                payload[f"perf_{name}_threshold"] = item["threshold"]
            if "debounce" in item and name == "cpu":
                payload["perf_debounce_count"] = item["debounce"]
            if "debounce_count" in item:
                payload["perf_debounce_count"] = item["debounce_count"]
    return payload


def load_performance_alarm_config(app_config: dict | None = None) -> dict[str, Any]:
    """Load thresholds. HMI-persisted app_config wins over env bootstrap."""
    merged = dict(_DEFAULTS)
    persisted = app_config or {}
    for env_name, (key, caster) in _ENV_MAP.items():
        if key in persisted and persisted[key] is not None:
            continue
        raw = os.environ.get(env_name)
        if raw is None or str(raw).strip() == "":
            continue
        if caster is bool:
            merged[key] = _parse_bool(raw)
        elif caster is int:
            try:
                merged[key] = int(raw)
            except ValueError:
                continue
        else:
            try:
                merged[key] = float(raw)
            except ValueError:
                continue
    for key in _DEFAULTS:
        if key in persisted and persisted[key] is not None:
            merged[key] = persisted[key]
    for key in _BOOL_KEYS:
        merged[key] = _parse_bool(merged.get(key))
    merged["perf_debounce_count"] = int(_clamp("perf_debounce_count", _as_number(merged["perf_debounce_count"], 3)))
    for key in _CLAMP:
        if key == "perf_debounce_count":
            continue
        merged[key] = _clamp(key, _as_number(merged.get(key), _DEFAULTS[key]))
    return merged


def alarm_entry(config: dict[str, Any], key: str) -> dict[str, Any]:
    return {
        "key": key,
        "enabled": bool(config.get(f"perf_{key}_enabled", True)),
        "threshold": config.get(f"perf_{key}_threshold"),
    }


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Operator-facing snapshot (GET /settings/performance)."""
    return {
        "enabled": bool(config.get("perf_alarms_enabled", True)),
        "debounce_count": int(config.get("perf_debounce_count") or 3),
        "alarms": [alarm_entry(config, key) for key in ALARM_KEYS],
        **{key: config[key] for key in _DEFAULTS},
    }
