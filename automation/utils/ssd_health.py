# -*- coding: utf-8 -*-
"""SSD SMART / temperature / wear. Best-effort; never raises; never blocks the hot path.

``smartctl`` is typically absent inside distroless. Set ``AUTOMATION_SSD_DEVICE``
on the host (or bind-mount smartctl) so the sampler can poll every 60 s.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

_LOGGER = logging.getLogger("pyautomation.metrics")

DEFAULT_WEAR_WARN = 80.0
DEFAULT_TEMP_WARN = 65.0
_SMART_TIMEOUT_S = 8.0


def wear_warn_percent(environ: dict | None = None) -> float:
    env = os.environ if environ is None else environ
    return _float_env(env, "AUTOMATION_SSD_WEAR_WARN", DEFAULT_WEAR_WARN, 1.0, 100.0)


def temp_warn_c(environ: dict | None = None) -> float:
    env = os.environ if environ is None else environ
    return _float_env(env, "AUTOMATION_SSD_TEMP_WARN", DEFAULT_TEMP_WARN, 0.0, 125.0)


def _float_env(env, name: str, default: float, lo: float, hi: float) -> float:
    raw = env.get(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


def configured_device(environ: dict | None = None) -> str:
    env = os.environ if environ is None else environ
    return str(env.get("AUTOMATION_SSD_DEVICE") or "").strip()


def parse_smartctl_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract wear % and temperature from smartctl -j (ATA or NVMe)."""
    wear = None
    temp = None
    nvme = payload.get("nvme_smart_health_information_log") or {}
    if isinstance(nvme, dict):
        used = nvme.get("percentage_used")
        if used is not None:
            try:
                wear = float(used)
            except (TypeError, ValueError):
                wear = None
        nvme_temp = nvme.get("temperature")
        if nvme_temp is not None:
            try:
                temp = float(nvme_temp)
            except (TypeError, ValueError):
                temp = None
    temp_block = payload.get("temperature")
    if temp is None and isinstance(temp_block, dict) and temp_block.get("current") is not None:
        try:
            temp = float(temp_block["current"])
        except (TypeError, ValueError):
            temp = None
    table = ((payload.get("ata_smart_attributes") or {}).get("table")) or []
    for attr in table:
        if not isinstance(attr, dict):
            continue
        attr_id = attr.get("id")
        raw = attr.get("raw") or {}
        raw_value = raw.get("value") if isinstance(raw, dict) else None
        name = str(attr.get("name") or "").lower()
        if attr_id in (194, 190) or "temperature" in name:
            if temp is None and raw_value is not None:
                try:
                    temp = float(raw_value)
                except (TypeError, ValueError):
                    pass
        if attr_id in (177, 231, 233) or "wear" in name or "percent_lifetime" in name:
            if wear is None and raw_value is not None:
                try:
                    wear = float(raw_value)
                except (TypeError, ValueError):
                    pass
    return {
        "available": wear is not None or temp is not None,
        "wear_percent": wear,
        "temp_c": temp,
        "source": "smartctl",
    }


def collect(device: str | None = None, *, runner=None) -> dict[str, Any]:
    """Return SMART snapshot. ``runner`` is a test hook ``(argv) -> (rc, stdout)``."""
    empty = {
        "available": False,
        "wear_percent": None,
        "temp_c": None,
        "source": "none",
        "device": device or configured_device() or None,
    }
    target = (device or configured_device()).strip()
    if not target:
        return empty
    empty["device"] = target
    argv = ["smartctl", "-A", "-j", target]
    try:
        if runner is not None:
            rc, stdout = runner(argv)
        else:
            binary = shutil.which("smartctl")
            if not binary:
                return empty
            argv[0] = binary
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=_SMART_TIMEOUT_S,
                check=False,
            )
            rc, stdout = completed.returncode, completed.stdout or ""
        if not stdout.strip():
            return empty
        data = json.loads(stdout)
        parsed = parse_smartctl_json(data if isinstance(data, dict) else {})
        parsed["device"] = target
        parsed["available"] = bool(parsed.get("available"))
        return parsed
    except Exception:
        _LOGGER.debug("SMART collection failed device=%s", target, exc_info=True)
        return empty


def alarm_active(sample: dict[str, Any], *, wear_warn: float | None = None, temp_warn: float | None = None) -> bool:
    if not sample.get("available"):
        return False
    wear_limit = DEFAULT_WEAR_WARN if wear_warn is None else float(wear_warn)
    temp_limit = DEFAULT_TEMP_WARN if temp_warn is None else float(temp_warn)
    wear = sample.get("wear_percent")
    temp = sample.get("temp_c")
    if wear is not None and float(wear) >= wear_limit:
        return True
    if temp is not None and float(temp) >= temp_limit:
        return True
    return False
