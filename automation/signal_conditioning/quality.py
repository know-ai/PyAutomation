# -*- coding: utf-8 -*-
"""OPC-style quality codes for CVT / wavelet / HMI (float wire format).

Maps OPC UA Part 4 StatusCode severity bits to GOOD / UNCERTAIN / BAD.
The frozen ``Quality`` object is the OPC-edge contract; the hot path keeps a
float so acquisition stays O(1) with no extra allocations on the GOOD path.
"""
from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass

GOOD = 1.0
UNCERTAIN = 0.5
BAD = 0.0

_SEVERITY_GOOD = 0
_SEVERITY_UNCERTAIN = 1
_SEVERITY_BAD = 2

_SUBSTATUS_BY_NAME = {
    "BadSensorFailure": "SensorFailure",
    "BadDeviceFailure": "DeviceFailure",
    "BadOutOfRange": "Overrange",
    "BadOutOfService": "OutOfService",
    "BadNoCommunication": "NoCommunication",
    "BadNotConnected": "NotConnected",
    "BadWaitingForInitialData": "NoData",
    "UncertainLastUsableValue": "LastUsable",
    "UncertainSensorNotAccurate": "SensorNotAccurate",
    "UncertainEngineeringUnitsExceeded": "Overrange",
    "UncertainSubstituteValue": "SubstituteValue",
}

_inhibit_lock = threading.Lock()
_inhibit_uncertain = False
_inhibit_loaded = False


@dataclass(frozen=True)
class Quality:
    """Immutable quality snapshot at the OPC / CVT boundary."""

    severity: float = GOOD
    opc_code: int | None = None
    substatus: str | None = None
    stale: bool = False
    stale_age_ms: int | None = None

    def is_bad(self) -> bool:
        return is_bad_quality(self.severity)

    def is_good(self) -> bool:
        return float(self.severity) >= 0.99


def is_good_quality(quality: float | None) -> bool:
    """True when quality is usable for the wavelet ring (GOOD or UNCERTAIN)."""
    if quality is None:
        return True
    return float(quality) > 0.0


def is_bad_quality(quality: float | None) -> bool:
    if quality is None:
        return False
    return float(quality) < 0.25


def is_uncertain_quality(quality: float | None) -> bool:
    if quality is None:
        return False
    q = float(quality)
    return 0.25 <= q < 0.99


def is_good_sample(raw, quality: float | None) -> bool:
    if not is_good_quality(quality):
        return False
    try:
        return math.isfinite(float(raw))
    except (TypeError, ValueError):
        return False


def publication_quality_label(quality: float | None) -> str:
    if quality is None:
        return "GOOD"
    q = float(quality)
    if q >= 0.99:
        return "GOOD"
    if q >= 0.25:
        return "UNCERTAIN"
    return "BAD"


def quality_badge_letter(quality: float | None) -> str:
    label = publication_quality_label(quality)
    return label[0] if label else "G"


def _status_int(status_code) -> int | None:
    if status_code is None:
        return None
    try:
        return int(getattr(status_code, "value", status_code))
    except (TypeError, ValueError, AttributeError):
        return None


def status_code_substatus(status_code) -> str | None:
    """Human substatus for HMI / Events (SensorFailure, LastUsable, …)."""
    name = getattr(status_code, "name", None)
    if isinstance(name, str) and name:
        mapped = _SUBSTATUS_BY_NAME.get(name)
        if mapped:
            return mapped
        if name.startswith("Bad") and name != "Bad":
            return name[3:]
        if name.startswith("Uncertain") and name != "Uncertain":
            return name[9:]
        if name in ("Good", "Uncertain", "Bad"):
            return None
        return name
    return None


def status_code_to_quality(status_code) -> float:
    """Map an OPC UA StatusCode (or int / None) to GOOD / UNCERTAIN / BAD.

    OPC UA Part 4: top two bits of the StatusCode are the severity field
    (0=Good, 1=Uncertain, 2/3=Bad).
    """
    if status_code is None:
        return GOOD
    try:
        if hasattr(status_code, "is_good") and callable(status_code.is_good):
            if status_code.is_good():
                return GOOD
        value = int(getattr(status_code, "value", status_code))
    except (TypeError, ValueError, AttributeError):
        return UNCERTAIN
    severity = (value >> 30) & 0x3
    if severity == _SEVERITY_GOOD:
        return GOOD
    if severity == _SEVERITY_UNCERTAIN:
        return UNCERTAIN
    return BAD


def map_opc_status(status_code) -> Quality:
    """OPC-edge mapper: StatusCode → immutable Quality (severity + forensics)."""
    return Quality(
        severity=status_code_to_quality(status_code),
        opc_code=_status_int(status_code),
        substatus=status_code_substatus(status_code),
    )


def normalize_sample_quality(raw, quality: float | None) -> float:
    """Force BAD when the raw numeric sample is non-finite."""
    q = float(quality) if quality is not None else GOOD
    if isinstance(raw, bool):
        return q
    if isinstance(raw, (int, float)):
        try:
            if not math.isfinite(float(raw)):
                return BAD
        except (TypeError, ValueError):
            return BAD
    return q


def is_process_alarm_allowed(
    quality: float | None,
    *,
    inhibit_uncertain: bool = False,
) -> bool:
    """ISA-18.2-style gate: process setpoints must not fire on Bad PV.

    UNCERTAIN is allowed by default; set ``inhibit_uncertain=True`` (or app
    config ``alarm_inhibit_uncertain_quality``) to inhibit it as well.
    """
    if quality is None:
        return True
    q = float(quality)
    if q >= 0.99:
        return True
    if q >= 0.25:
        return not inhibit_uncertain
    return False


def set_inhibit_uncertain_quality(value: bool) -> None:
    """Hot-path cache for Settings → alarm_inhibit_uncertain_quality."""
    global _inhibit_uncertain, _inhibit_loaded
    with _inhibit_lock:
        _inhibit_uncertain = bool(value)
        _inhibit_loaded = True


def get_inhibit_uncertain_quality() -> bool:
    """O(1) after first load. Never reads JSON on the acquisition path."""
    global _inhibit_loaded
    if not _inhibit_loaded:
        reload_inhibit_uncertain_from_config()
    return _inhibit_uncertain


def reload_inhibit_uncertain_from_config(config: dict | None = None) -> bool:
    """Load inhibit flag from app config. Safe to call from Settings PUT."""
    global _inhibit_uncertain, _inhibit_loaded
    value = False
    try:
        if config is None:
            from automation import PyAutomation

            config = PyAutomation().get_app_config() or {}
        value = bool((config or {}).get("alarm_inhibit_uncertain_quality", False))
    except Exception:
        logging.getLogger("pyautomation").debug(
            "inhibit_uncertain config load skipped",
            exc_info=True,
        )
        value = False
    with _inhibit_lock:
        _inhibit_uncertain = value
        _inhibit_loaded = True
    return value
