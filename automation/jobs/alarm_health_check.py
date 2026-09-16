# -*- coding: utf-8 -*-
"""Alarm transition worker liveness. SPEC-ISA18-2-CLOSURE-v3 P1-3 / CA-P1-3-4."""
from __future__ import annotations

import logging
import time

_LOGGER = logging.getLogger("pyautomation")
_DEAD_TIMEOUT_S = 30.0


def check_worker_health() -> None:
    from ..alarms.runtime import get_alarm_runtime

    runtime = get_alarm_runtime()
    worker = runtime.worker
    if worker is None:
        return
    if runtime.is_worker_alive_recently(timeout_s=_DEAD_TIMEOUT_S):
        return
    now = time.monotonic()
    if now - runtime._last_worker_dead_log < 10.0:
        return
    runtime._last_worker_dead_log = now
    lag_s = now - getattr(worker, "_last_heartbeat", now)
    _LOGGER.critical(
        "ALARM.WORKER.Dead lag_s=%.1f queue_depth=%d",
        lag_s,
        len(runtime._pending_transitions),
    )
    try:
        runtime.restart_worker()
    except Exception:
        _LOGGER.exception("ALARM.WORKER.RestartFailed")
