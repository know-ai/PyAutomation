# -*- coding: utf-8 -*-
"""Single source of truth for historian time resolution.

TagValue stores unix epoch ticks at millisecond precision (Peewee
``TimestampField(resolution=3)``). Sub-millisecond noise from duplicate
``set_value`` calls in the same machine cycle collapses under UNIQUE
``(tag_id, timestamp)``.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Peewee TimestampField resolution for TagValue (3 = milliseconds).
TAGVALUE_TIMESTAMP_RESOLUTION = 3

# Discriminators for legacy bigint columns (seconds / ms / µs).
SECONDS_CEILING = 10_000_000_000  # 1e10 — below: unix seconds
MICROSECONDS_FLOOR = 100_000_000_000_000  # 1e14 — at/above: unix microseconds


DISPLAY_DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


def ensure_utc(value: datetime | None) -> datetime:
    """Treat naive timestamps as UTC; convert aware timestamps to UTC."""
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_display_datetime(value: datetime | None, timezone_name: str | None = None) -> str | None:
    """Format a UTC instant for historical APIs in an IANA zone (plant fallback)."""
    if value is None:
        return None
    import os
    import pytz

    name = timezone_name or os.environ.get("AUTOMATION_TIMEZONE") or "America/Caracas"
    target = pytz.timezone(name)
    return ensure_utc(value).astimezone(target).strftime(DISPLAY_DATETIME_FORMAT)


def quantize_datetime_ms(value: datetime) -> datetime:
    """Drop sub-millisecond component; keep timezone."""
    value = ensure_utc(value)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def iso_millis(value: datetime | str | None) -> str | None:
    """UTC ISO-8601 with millisecond precision (timespec='milliseconds')."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        value = parsed
    value = quantize_datetime_ms(value)
    return value.isoformat(timespec="milliseconds")


def epoch_seconds_from_db_tick(numeric: float | int) -> float:
    """Interpret a TagValue bigint tick that may be s, ms, or µs (legacy mix)."""
    value = float(numeric)
    if value >= MICROSECONDS_FLOOR:
        return value / 1_000_000.0
    if value >= SECONDS_CEILING:
        return value / 1_000.0
    return value
