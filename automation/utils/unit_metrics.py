# -*- coding: utf-8 -*-
"""Process-wide counters for tag-unit health (spec 12 CA-UNIT-09/11/12)."""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
_SAF_SAMPLES_WITHOUT_UNIT = 0
_UNITS_MISMATCH_COUNT = 0


def inc_saf_samples_without_unit(n: int = 1) -> int:
    global _SAF_SAMPLES_WITHOUT_UNIT
    with _LOCK:
        _SAF_SAMPLES_WITHOUT_UNIT += max(0, int(n))
        return _SAF_SAMPLES_WITHOUT_UNIT


def get_saf_samples_without_unit() -> int:
    with _LOCK:
        return _SAF_SAMPLES_WITHOUT_UNIT


def inc_units_mismatch(n: int = 1) -> int:
    global _UNITS_MISMATCH_COUNT
    with _LOCK:
        _UNITS_MISMATCH_COUNT += max(0, int(n))
        return _UNITS_MISMATCH_COUNT


def get_units_mismatch_runtime() -> int:
    with _LOCK:
        return _UNITS_MISMATCH_COUNT


def reset_unit_metrics() -> None:
    global _SAF_SAMPLES_WITHOUT_UNIT, _UNITS_MISMATCH_COUNT
    with _LOCK:
        _SAF_SAMPLES_WITHOUT_UNIT = 0
        _UNITS_MISMATCH_COUNT = 0


def health_unit_metrics() -> dict[str, int]:
    """Snapshot for ``GET /api/health/system``."""
    mismatch = get_units_mismatch_runtime()
    try:
        from ..variables.units_contract import scan_process_type_unit_mismatches

        mismatch = max(mismatch, int(scan_process_type_unit_mismatches()))
    except Exception:
        pass
    return {
        "UNITS_MISMATCH_COUNT": mismatch,
        "SAF_SAMPLES_WITHOUT_UNIT": get_saf_samples_without_unit(),
    }
