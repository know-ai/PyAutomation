# -*- coding: utf-8 -*-
"""Named plant bounds. Context: all. Complexity: O(1). SPEC-ISA18-2-P2-CLOSURE-v2 §0bis.3."""

_MAX_ALARMS = 5_000
_MAX_ACTIVE = 1_000
_MAX_TAGS = 10_000
_MAX_ALARMS_PER_TAG = 20
_MAX_SUPPRESSIONS = 500
_MAX_CHATTER = 500
_MAX_CHATTER_WINDOW = 10
_CHATTER_THRESHOLD = 3
_CHATTER_WINDOW_S = 600.0
_CHATTER_RESET_IDLE_S = 1_800.0
_MAX_KPI_RATE_WINDOW = 3_600
_MAX_KPI_ACK_LATENCIES = 1_000
_MAX_PRIORITY_KEYS = 4
_PRIORITY_MIN = 1
_PRIORITY_MAX = 4
_PRIORITY_DEFAULT = 4


def coerce_alarm_priority(value, default: int = _PRIORITY_DEFAULT) -> int:
    """ISA-18.2 alarm priority: 1 (most urgent) through 4. None uses the default."""
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"priority {value!r} is not an integer") from exc
    if not _PRIORITY_MIN <= number <= _PRIORITY_MAX:
        raise ValueError(f"priority {number} out of range [{_PRIORITY_MIN}, {_PRIORITY_MAX}]")
    return number


def alarm_priority_or_default(value, default: int = _PRIORITY_DEFAULT) -> int:
    """Same scale as ``coerce_alarm_priority``, but a bad value falls back to the default."""
    try:
        return coerce_alarm_priority(value, default=default)
    except ValueError:
        return default
_SUPPRESSION_CACHE_MAX = 2_000
_SUPPRESSION_TTL_S = 60.0
_SILENCE_MAX_MIN = 30
_SHELVE_MAX_H = 24
_ARCHIVE_CHUNK = 10_000
_RETENTION_DAYS = 365
_KPI_HISTORY_DAYS = 90
_PARTITION_PAST_MONTHS = 9
_PARTITION_FUTURE_MONTHS = 3
_PARTITION_DROP_YEARS = 7
_API_ROW_CAP = 1_000
_EVENT_LOG_MAX = 1_000
_FOOTER_ACTIVE_CAP = 100
