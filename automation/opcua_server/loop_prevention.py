"""Rate limit, oscillation and the command window. Complexity: O(1) per call."""

from __future__ import annotations

import time
from collections import deque

from .access.contracts import IOscillationDetector, IRateLimiter

_MAX_KEYS = 10_000


class SlidingWindowRateLimiter(IRateLimiter):
    """Per-tag and per-session caps. Complexity: O(1)."""

    def __init__(self, tag_per_s: int = 10, session_per_s: int = 100, window_s: float = 1.0) -> None:
        self.tag_per_s = tag_per_s
        self.session_per_s = session_per_s
        self.window_s = window_s
        self._tags: dict[str, deque] = {}
        self._sessions: dict[str, deque] = {}
        self.hits = 0

    def allow(self, tag_key: str, session_key: str) -> bool:
        """Complexity: O(1)."""
        now = time.monotonic()
        if not self._allow(self._tags, tag_key, self.tag_per_s, now):
            self.hits += 1
            return False
        if not self._allow(self._sessions, session_key or "anonymous", self.session_per_s, now):
            self.hits += 1
            return False
        return True

    def _allow(self, bucket: dict, key: str, limit: int, now: float) -> bool:
        if key not in bucket and len(bucket) >= _MAX_KEYS:
            bucket.pop(next(iter(bucket)))
        stamps = bucket.setdefault(key, deque(maxlen=limit))
        while stamps and now - stamps[0] > self.window_s:
            stamps.popleft()
        if len(stamps) >= limit:
            return False
        stamps.append(now)
        return True


class WindowOscillationDetector(IOscillationDetector):
    """More than ``limit`` changes inside ``window_s`` throttles the tag. Complexity: O(1)."""

    def __init__(self, limit: int = 8, window_s: float = 10.0, throttle_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self.throttle_s = throttle_s
        self._stamps: dict[str, deque] = {}
        self._until: dict[str, float] = {}
        self.detected = 0

    def observe(self, tag_key: str, value) -> bool:
        """Complexity: O(1). ``value`` is part of the trace and is not stored."""
        del value
        now = time.monotonic()
        if self.throttled(tag_key, now):
            return False
        if tag_key not in self._stamps and len(self._stamps) >= _MAX_KEYS:
            self._stamps.pop(next(iter(self._stamps)))
        stamps = self._stamps.setdefault(tag_key, deque(maxlen=self.limit))
        while stamps and now - stamps[0] > self.window_s:
            stamps.popleft()
        stamps.append(now)
        if len(stamps) < self.limit:
            return False
        self._until[tag_key] = now + self.throttle_s
        self.detected += 1
        return True

    def throttled(self, tag_key: str, now: float | None = None) -> bool:
        """Complexity: O(1)."""
        until = self._until.get(tag_key, 0.0)
        return (now if now is not None else time.monotonic()) < until


class CommandWindow:
    """PLC stays the authority after the window. Complexity: O(1)."""

    def __init__(self, seconds: float = 5.0) -> None:
        self.seconds = seconds
        self._open: dict[str, tuple[float, object]] = {}

    def open(self, tag_key: str, value) -> None:
        """Complexity: O(1)."""
        if tag_key not in self._open and len(self._open) >= _MAX_KEYS:
            self._open.pop(next(iter(self._open)))
        self._open[tag_key] = (time.monotonic() + self.seconds, value)

    def holds(self, tag_key: str, value) -> bool:
        """True when the field sample repeats the commanded value. Complexity: O(1)."""
        slot = self._open.get(tag_key)
        if slot is None or time.monotonic() > slot[0]:
            self._open.pop(tag_key, None)
            return False
        return slot[1] == value

    def clear(self, tag_key: str) -> None:
        """Complexity: O(1)."""
        self._open.pop(tag_key, None)


def bind_access_runtime(server) -> None:
    """Attach the write-path maps. Complexity: O(1)."""
    server._access_policy = {}
    server._write_limits = {}
    server._opc_names = {}
    server._client_write_marks = {}
    server.rate_limiter = SlidingWindowRateLimiter()
    server.oscillation = WindowOscillationDetector()
    server.command_window = CommandWindow()
    server.scada_sink = None


def note_field_sample(tag_name: str, value) -> None:
    """A field sample that differs from the command window can oscillate. Complexity: O(1)."""
    try:
        from .. import PyAutomation
        from ..models import StringType

        machine = PyAutomation().get_machine(name=StringType("OPCUAServer"))
    except Exception:
        return
    if machine is None:
        return
    window = getattr(machine, "command_window", None)
    if window is not None and window.holds(str(tag_name), value):
        return
    if window is not None:
        window.clear(str(tag_name))
    detector = getattr(machine, "oscillation", None)
    if detector is None or not detector.observe(str(tag_name), value):
        return
    from .observability import emit_access_event, note_metric

    note_metric(machine, "oscillation_detected")
    emit_access_event("oscillation", "field", str(tag_name))
