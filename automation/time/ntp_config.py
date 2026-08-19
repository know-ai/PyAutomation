# -*- coding: utf-8 -*-
"""NTP monitor configuration: app_config.json (HMI) > env bootstrap > defaults."""
from __future__ import annotations

import os
import re
from typing import Any

# Hostname, IPv4, IPv6 (with optional brackets), port suffix for literals
_SERVER_RE = re.compile(
    r"^(\[[0-9a-fA-F:]+\]|[0-9a-fA-F:.]+|[a-zA-Z0-9](?:[a-zA-Z0-9.\-]*[a-zA-Z0-9])?)$"
)
_DEFAULTS = {
    "ntp_servers": "",
    "ntp_check_interval_s": 3600,
    "ntp_warn_offset_ms": 50,
    "ntp_alarm_offset_ms": 1000,
    "ntp_step_threshold_ms": 2000,
    "ntp_fail_closed": False,
    "ntp_enabled": True,
    "ntp_auth_type": "none",
}
_ENV_MAP = {
    "AUTOMATION_NTP_SERVERS": ("ntp_servers", str),
    "AUTOMATION_NTP_CHECK_INTERVAL_S": ("ntp_check_interval_s", int),
    "AUTOMATION_NTP_WARN_OFFSET_MS": ("ntp_warn_offset_ms", int),
    "AUTOMATION_NTP_ALARM_OFFSET_MS": ("ntp_alarm_offset_ms", int),
    "AUTOMATION_NTP_STEP_THRESHOLD_MS": ("ntp_step_threshold_ms", int),
    "AUTOMATION_NTP_FAIL_CLOSED": ("ntp_fail_closed", bool),
    "AUTOMATION_NTP_ENABLED": ("ntp_enabled", bool),
    "AUTOMATION_NTP_AUTH_TYPE": ("ntp_auth_type", str),
}


def _parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_server_list(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = str(raw).split(",")
    servers: list[str] = []
    seen: set[str] = set()
    for item in items:
        host = str(item or "").strip()
        if not host:
            continue
        key = host.lower()
        if key in seen:
            continue
        seen.add(key)
        servers.append(host)
    return servers


def validate_server_list(servers: list[str]) -> tuple[bool, str | None]:
    if not servers:
        return True, None
    for server in servers:
        candidate = server.strip()
        if len(candidate) > 253 or not _SERVER_RE.match(candidate):
            return False, f"Invalid NTP server: {server}"
    return True, None


def load_ntp_config(app_config: dict | None = None) -> dict[str, Any]:
    """Load NTP settings.

    Priority:
    1. ``db/app_config.json`` (written by HMI Settings → NTP Sync) — operator source of truth
    2. Environment variables — optional bootstrap when a key is not yet persisted
    3. Built-in defaults
    """
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
            merged[key] = str(raw).strip()
    for key in _DEFAULTS:
        if key in persisted and persisted[key] is not None:
            merged[key] = persisted[key]
    servers = parse_server_list(merged.get("ntp_servers"))
    merged["ntp_servers_list"] = servers
    merged["ntp_check_interval_s"] = max(60, min(86400, int(merged.get("ntp_check_interval_s") or 3600)))
    merged["ntp_warn_offset_ms"] = max(1, int(merged.get("ntp_warn_offset_ms") or 50))
    merged["ntp_alarm_offset_ms"] = max(
        merged["ntp_warn_offset_ms"],
        int(merged.get("ntp_alarm_offset_ms") or 1000),
    )
    merged["ntp_step_threshold_ms"] = max(100, int(merged.get("ntp_step_threshold_ms") or 2000))
    auth_type = str(merged.get("ntp_auth_type") or "none").strip().lower()
    if auth_type not in {"none", "symmetric", "nts"}:
        auth_type = "none"
    merged["ntp_auth_type"] = auth_type
    enabled = bool(merged.get("ntp_enabled", True))
    merged["effective_enabled"] = enabled and bool(servers)
    return merged
