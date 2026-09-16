# -*- coding: utf-8 -*-
"""SuppressionType Strategy. Context: API. Complexity: O(1). OCP: 5º tipo sin tocar manager."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta

from .constants import _SHELVE_MAX_H, _SILENCE_MAX_MIN


class SuppressionType(ABC):
    @abstractmethod
    def validate(self, **kwargs) -> None: ...

    @abstractmethod
    def compute_expiry(self, clock) -> object: ...

    @abstractmethod
    def name(self) -> str: ...


class SilenceType(SuppressionType):
    MAX_DURATION_MIN = _SILENCE_MAX_MIN

    def __init__(self):
        self._duration_min = _SILENCE_MAX_MIN

    def validate(self, duration_min: int = 30, reason: str = "", **_):
        duration_min = int(duration_min)
        if not 1 <= duration_min <= self.MAX_DURATION_MIN:
            raise ValueError("silence 1..30 min")
        if not str(reason or "").strip():
            raise ValueError("reason required")
        self._duration_min = duration_min

    def compute_expiry(self, clock):
        return clock.now() + timedelta(minutes=self._duration_min)

    def name(self):
        return "silence"


class ShelveType(SuppressionType):
    def __init__(self):
        self._hours = _SHELVE_MAX_H

    def validate(self, duration_h: int = 24, reason: str = "", **_):
        duration_h = int(duration_h)
        if not 1 <= duration_h <= _SHELVE_MAX_H:
            raise ValueError("shelve 1..24 h")
        if not str(reason or "").strip():
            raise ValueError("reason required")
        self._hours = duration_h

    def compute_expiry(self, clock):
        return clock.now() + timedelta(hours=self._hours)

    def name(self):
        return "shelve"


class DisableType(SuppressionType):
    def validate(self, reason: str = "", **_):
        if not str(reason or "").strip():
            raise ValueError("reason required")

    def compute_expiry(self, clock):
        return None

    def name(self):
        return "disable"


class OOSType(SuppressionType):
    def validate(self, reason: str = "", **_):
        if not str(reason or "").strip():
            raise ValueError("reason required")

    def compute_expiry(self, clock):
        return None

    def name(self):
        return "oos"


class NoSuppression(SuppressionType):
    """Null Object. Context: COLD. Complexity: O(1)."""

    def validate(self, **kwargs) -> None:
        return None

    def compute_expiry(self, clock):
        return None

    def name(self):
        return "none"
