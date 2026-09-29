# -*- coding: utf-8 -*-
"""In-memory p95 windows. Not a persistent histogram (debt D-01)."""
from __future__ import annotations

import threading
from collections import deque

_LOCK = threading.Lock()
_ACK_MS: deque[float] = deque(maxlen=256)


def record_ack_ms(elapsed_ms: float) -> None:
    with _LOCK:
        _ACK_MS.append(float(elapsed_ms))


def ack_p95_ms() -> float:
    with _LOCK:
        samples = list(_ACK_MS)
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, int(round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])
