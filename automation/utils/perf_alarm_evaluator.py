# -*- coding: utf-8 -*-
"""Debounced threshold evaluator for node performance alarms.

O(n) with n=len(PERF_ALARM_SPECS). Never touches OPC or the historian. The sampler calls evaluate()
once per tick; BOOL writes happen only on state change.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .performance_alarm_config import load_performance_alarm_config
from .performance_alarms import PERF_ALARM_SPECS, set_performance_alarm

_LOGGER = logging.getLogger("pyautomation.metrics")


class PerfAlarmEvaluator:
    def __init__(
        self,
        config_provider: Callable[[], dict] | None = None,
        writer: Callable[..., bool] | None = None,
    ):
        self._config_provider = config_provider
        self._writer = writer or set_performance_alarm
        self._config: dict[str, Any] = {}
        self._counts: dict[str, int] = {spec.key: 0 for spec in PERF_ALARM_SPECS}
        self._active: dict[str, bool] = {spec.key: False for spec in PERF_ALARM_SPECS}
        self.reload()

    def reload(self, config: dict[str, Any] | None = None) -> None:
        if config is not None:
            self._config = dict(config)
            return
        try:
            persisted = self._config_provider() if self._config_provider else {}
        except Exception:
            persisted = {}
        self._config = load_performance_alarm_config(persisted)

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def evaluate(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        """Update BOOL alarms from one sampler snapshot. Returns active map."""
        cfg = self._config
        global_on = bool(cfg.get("perf_alarms_enabled", True))
        debounce = max(1, int(cfg.get("perf_debounce_count") or 3))
        for spec in PERF_ALARM_SPECS:
            enabled = global_on and bool(cfg.get(f"perf_{spec.key}_enabled", True))
            threshold = cfg.get(f"perf_{spec.key}_threshold")
            raw = snapshot.get(spec.snapshot_field)
            exceeded = False
            if enabled and raw is not None and threshold is not None:
                try:
                    exceeded = float(raw) >= float(threshold)
                except (TypeError, ValueError):
                    exceeded = False
            if not enabled:
                self._counts[spec.key] = 0
                next_active = False
            elif raw is None:
                next_active = self._active[spec.key]
            elif exceeded:
                self._counts[spec.key] = min(debounce, self._counts[spec.key] + 1)
                next_active = self._counts[spec.key] >= debounce
            else:
                self._counts[spec.key] = 0
                next_active = False
            self._writer(spec.key, next_active, value=raw, threshold=threshold)
            self._active[spec.key] = next_active
        return dict(self._active)
