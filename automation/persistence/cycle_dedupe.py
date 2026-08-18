# -*- coding: utf-8 -*-
"""Volatile per-cycle sample cache.

Drops silent re-writes of the same tag/value inside one machine cycle so they
never reach the journal. Business algorithms keep calling ``set_value``; the
gateway absorbs the duplicates.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from .contracts import IPersistable
from .records import DOMAIN

DEFAULT_TTL_S = 2.0


class CycleSampleCache:
    """Last-sample ring indexed by tag name, keyed to the cycle timestamp."""

    def __init__(self, ttl_s: float = DEFAULT_TTL_S):
        self._ttl_s = float(ttl_s)
        self._lock = threading.Lock()
        self._last: dict[str, tuple[str, Any, float]] = {}
        self.dropped = 0
        self._last_prune = 0.0
        self._prune_every_s = 0.5

    def should_drop(self, persistable: IPersistable) -> bool:
        """True when this tag already queued the same value for this cycle."""
        if persistable.domain() != DOMAIN.TAG:
            return False
        payload = persistable.payload()
        tag = str(persistable.entity_id() or payload.get("tag") or "")
        ts = str(payload.get("timestamp") or "")
        value = payload.get("value")
        if not tag or not ts:
            return False
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune >= self._prune_every_s:
                self._prune_locked(now)
                self._last_prune = now
            prev = self._last.get(tag)
            if prev is not None:
                prev_ts, prev_value, seen = prev
                if now - seen >= self._ttl_s:
                    self._last.pop(tag, None)
                elif prev_ts == ts and prev_value == value:
                    self.dropped += 1
                    return True
            self._last[tag] = (ts, value, now)
            return False

    def _prune_locked(self, now: float) -> None:
        cutoff = now - self._ttl_s
        stale = [name for name, (_ts, _value, seen) in self._last.items() if seen < cutoff]
        for name in stale:
            del self._last[name]
