# -*- coding: utf-8 -*-
"""SuppressionManager. Context: HOT lookup / API apply. Complexity: O(1)."""
from __future__ import annotations

from .clock import SystemClock
from .constants import _MAX_SUPPRESSIONS
from .events import MemoryEventLogger
from .suppression_cache import SuppressionCache
from .suppression_types import DisableType, NoSuppression, OOSType, ShelveType, SilenceType, SuppressionType


class SuppressionRecord:
    __slots__ = ("alarm_id", "type_name", "reason", "expires_at", "active")

    def __init__(self, alarm_id, type_name: str, reason: str, expires_at, active: bool = True):
        self.alarm_id = alarm_id
        self.type_name = type_name
        self.reason = reason
        self.expires_at = expires_at
        self.active = active


class SuppressionDecorator:
    """Decorator: is_suppressed without touching the SM. Context: HOT. O(1)."""

    def __init__(self, reader):
        self._reader = reader

    def is_suppressed(self, alarm_id) -> bool:
        return self._reader.is_suppressed(alarm_id)


class SuppressionManager:
    """Context: HOT is_suppressed / API apply. Complexity: O(1). OCP via register()."""

    _types: dict[str, type[SuppressionType]] = {
        "silence": SilenceType,
        "shelve": ShelveType,
        "disable": DisableType,
        "oos": OOSType,
        "none": NoSuppression,
    }

    def __init__(self, cache=None, clock=None, events=None):
        self._clock = clock or SystemClock()
        self._cache = cache or SuppressionCache(self._clock)
        self._events = events or MemoryEventLogger(self._clock)
        self._active: dict[object, SuppressionRecord] = {}
        self._next_id = 1
        self._legacy: dict[object, str] = {}

    @classmethod
    def register(cls, name: str, impl: type[SuppressionType]) -> None:
        cls._types[str(name)] = impl

    def is_suppressed(self, alarm_id) -> bool:
        """Context: HOT. Complexity: O(1)."""
        if alarm_id in self._legacy:
            return True
        return self._cache.is_suppressed(alarm_id)

    def update(self, alarm_id, state: str | None) -> None:
        """Context: COLD. Complexity: O(1). Compat T-75 / runtime.sync_alarm."""
        if state:
            self._legacy[alarm_id] = state
            self._cache.set(alarm_id, True)
        else:
            self._legacy.pop(alarm_id, None)
            self._cache.set(alarm_id, False)

    def apply(self, alarm_id, type: str, **kw) -> int:
        """Context: API/COLD. Complexity: O(1) + Event."""
        impl_cls = self._types.get(str(type))
        if impl_cls is None:
            raise ValueError(f"unknown suppression type {type}")
        impl = impl_cls()
        impl.validate(**kw)
        expiry = impl.compute_expiry(self._clock)
        if len(self._active) >= _MAX_SUPPRESSIONS:
            oldest = next(iter(self._active))
            self._active.pop(oldest, None)
        rec_id = self._next_id
        self._next_id += 1
        reason = str(kw.get("reason") or "")
        self._active[rec_id] = SuppressionRecord(alarm_id, impl.name(), reason, expiry, True)
        self._cache.set(alarm_id, True)
        self._events.log(
            name="ALM.SUPPRESSION.APPLIED",
            alarm_id=alarm_id,
            suppression_type=impl.name(),
            reason=reason,
            expires_at=expiry,
        )
        return rec_id

    def release(self, alarm_id, op_id: int = 0) -> None:
        """Context: API/COLD. Complexity: O(1)."""
        for rec_id, rec in list(self._active.items()):
            if rec.alarm_id == alarm_id and rec.active:
                rec.active = False
        self._cache.set(alarm_id, False)
        self._legacy.pop(alarm_id, None)
        self._events.log(name="ALM.SUPPRESSION.RELEASED", alarm_id=alarm_id, user_id=op_id)

    def expire_due(self) -> int:
        """Context: BG. Complexity: O(N_suppressions) N≤500."""
        now = self._clock.now()
        n = 0
        for rec in self._active.values():
            if rec.active and rec.expires_at is not None and rec.expires_at <= now:
                rec.active = False
                self._cache.set(rec.alarm_id, False)
                n += 1
        return n
