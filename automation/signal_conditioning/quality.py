# -*- coding: utf-8 -*-
"""OPC-style quality codes for wavelet filtering (float wire format)."""
from __future__ import annotations

import math

GOOD = 1.0
UNCERTAIN = 0.5
BAD = 0.0


def is_good_quality(quality: float | None) -> bool:
    if quality is None:
        return True
    return float(quality) > 0.0


def is_good_sample(raw, quality: float | None) -> bool:
    if not is_good_quality(quality):
        return False
    try:
        return math.isfinite(float(raw))
    except (TypeError, ValueError):
        return False


def publication_quality_label(quality: float | None) -> str:
    if quality is None:
        return "GOOD"
    q = float(quality)
    if q >= 0.99:
        return "GOOD"
    if q >= 0.25:
        return "UNCERTAIN"
    return "BAD"
