# -*- coding: utf-8 -*-
"""ChatterDetector. Context: COLD. Complexity: O(1). INV-106 deque(maxlen=10)."""
from __future__ import annotations

from collections import deque

from ..states import HISTORY_RTNUN, HISTORY_UNACK
from .clock import SystemClock
from .constants import (
    _CHATTER_RESET_IDLE_S,
    _CHATTER_THRESHOLD,
    _CHATTER_WINDOW_S,
    _MAX_CHATTER,
    _MAX_CHATTER_WINDOW,
)
from .repository import MemoryAlarmRepository

_BD_PAIRS = {
    (HISTORY_UNACK, HISTORY_RTNUN),
    (HISTORY_RTNUN, HISTORY_UNACK),
}


def _key(alarm) -> object:
    if isinstance(alarm, (str, int)):
        return alarm
    return getattr(alarm, "identifier", None) or getattr(alarm, "name", None) or id(alarm)


class ChatterDetector:
    """Context: COLD. Complexity: O(1) por transición. SRP: solo chatter."""

    _WINDOW_SIZE = _MAX_CHATTER_WINDOW
    _THRESHOLD_TRANSITIONS = _CHATTER_THRESHOLD
    _WINDOW_DURATION_S = _CHATTER_WINDOW_S
    _RESET_IDLE_S = _CHATTER_RESET_IDLE_S

    def __init__(self, clock=None, alarm_repo=None):
        self._clock = clock or SystemClock()
        self._repo = alarm_repo or MemoryAlarmRepository()
        self._windows: dict[object, deque] = {}
        self._active_alarm_ids: deque = deque(maxlen=_MAX_CHATTER)
        self._last_ts: dict[object, float] = {}

    def on_transition(self, alarm, from_state: str = "", to_state: str = "") -> bool:
        """Context: COLD. Complexity: O(1).

        Legacy: on_transition(alarm_id: str) — T-74.
        P2: on_transition(alarm, from_state, to_state) — CA-B4-1.
        """
        key = _key(alarm)
        if from_state and to_state and (from_state, to_state) not in _BD_PAIRS:
            return False
        now = self._clock.monotonic()
        window = self._windows.get(key)
        if window is None:
            if len(self._windows) >= _MAX_CHATTER:
                oldest = self._active_alarm_ids.popleft() if self._active_alarm_ids else None
                if oldest is not None:
                    self._windows.pop(oldest, None)
                    self._last_ts.pop(oldest, None)
            window = deque(maxlen=self._WINDOW_SIZE)
            self._windows[key] = window
        window.append(now)
        self._last_ts[key] = now
        if key not in self._active_alarm_ids:
            self._active_alarm_ids.append(key)
        obj = alarm if not isinstance(alarm, (str, int)) else None
        self._maybe_reset(key, obj, now)
        if len(window) >= self._THRESHOLD_TRANSITIONS:
            span = window[-1] - window[0]
            if span <= self._WINDOW_DURATION_S:
                if obj is not None and not getattr(obj, "chattering", False):
                    obj.chattering = True
                    obj.chatter_count = 0
                    self._repo.set_chattering(key, True)
                if obj is not None:
                    obj.chatter_count = int(getattr(obj, "chatter_count", 0) or 0) + 1
                    obj.last_chatter_ts = now
                    self._repo.set_chatter_count(key, obj.chatter_count)
                return True
        return False

    def _maybe_reset(self, key, alarm, now: float) -> None:
        """Context: COLD. Complexity: O(1)."""
        last = self._last_ts.get(key)
        chatting = bool(getattr(alarm, "chattering", False)) if alarm is not None else False
        if chatting and last is not None and (now - last) >= self._RESET_IDLE_S:
            if alarm is not None:
                alarm.chattering = False
                alarm.chatter_count = 0
            self._repo.set_chattering(key, False)
            self._windows[key] = deque(maxlen=self._WINDOW_SIZE)

    def is_chattering(self, alarm) -> bool:
        """Context: COLD/API. Complexity: O(1)."""
        if not isinstance(alarm, (str, int)):
            return bool(getattr(alarm, "chattering", False))
        return bool(self._repo._row(alarm).get("chattering"))
