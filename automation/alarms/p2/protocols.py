# -*- coding: utf-8 -*-
"""ISP protocols. Context: COLD/API. Complexity: O(1) signatures only."""
from __future__ import annotations

from datetime import datetime
from typing import Any, ContextManager, Optional, Protocol


class IPriorityReader(Protocol):
    def get_priority(self, alarm_id) -> int: ...


class IPriorityWriter(Protocol):
    def set_priority(self, alarm_id, p: int, op_id: int) -> None: ...


class IChatterDetector(Protocol):
    def on_transition(self, alarm, f: str = "", t: str = "") -> bool: ...


class ISuppressionReader(Protocol):
    def is_suppressed(self, alarm_id) -> bool: ...


class ISuppressionWriter(Protocol):
    def apply(self, alarm_id, type: str, **kw) -> int: ...


class IAlarmRepository(Protocol):
    def get_priority(self, alarm_id) -> int: ...
    def set_priority(self, alarm_id, p: int) -> None: ...
    def set_chattering(self, alarm_id, value: bool) -> None: ...
    def set_chatter_count(self, alarm_id, count: int) -> None: ...
    def transaction(self) -> ContextManager: ...


class IEventLogger(Protocol):
    def log(self, name: str, **fields: Any) -> None: ...


class IMetricsSink(Protocol):
    def emit(self, name: str, value: float) -> None: ...


class IClock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...
