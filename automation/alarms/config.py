# -*- coding: utf-8 -*-
"""Alarm subsystem flags. SPEC-ISA18-2-CLOSURE-v3 INV-41 / INV-42."""
from __future__ import annotations

import logging
import os
import sys

_LOGGER = logging.getLogger("pyautomation")
_WARNED_PROD_DRAIN = False


def _is_test_runner() -> bool:
    return "unittest" in sys.modules or "pytest" in sys.modules


def _flag_true(name: str = "ALARM_SYNC_DRAIN") -> bool:
    return os.getenv(name, "").strip().lower() == "true"


class AlarmConfig:
    """INV-41: production default is false. Production ignores the env flag."""

    @classmethod
    def sync_drain_requested(cls) -> bool:
        return _flag_true("ALARM_SYNC_DRAIN")

    @classmethod
    def is_sync_drain_allowed(cls) -> bool:
        env = os.getenv("AUTOMATION_ENV", "").strip().lower()
        if env in ("production", "prod"):
            cls._warn_if_ignored()
            return False
        runner = _is_test_runner()
        if env in ("test", "ci") or runner:
            raw = os.getenv("ALARM_SYNC_DRAIN")
            if raw is None:
                return runner
            return raw.strip().lower() == "true"
        cls._warn_if_ignored()
        return False

    @classmethod
    def _warn_if_ignored(cls) -> None:
        global _WARNED_PROD_DRAIN
        if cls.sync_drain_requested() and not _WARNED_PROD_DRAIN:
            _WARNED_PROD_DRAIN = True
            _LOGGER.warning(
                "ALARM_SYNC_DRAIN=true ignored in production (AUTOMATION_ENV=%s)",
                os.getenv("AUTOMATION_ENV", "production"),
            )
