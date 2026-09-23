"""AccessLevel bitmask. Complexity of every helper: O(1)."""

from __future__ import annotations

from enum import IntFlag

_MASK = 0x7F


class AccessLevel(IntFlag):
    """Seven OPC UA Part 3 bits. The high bit stays reserved."""

    CURRENT_READ = 0x01
    CURRENT_WRITE = 0x02
    HISTORY_READ = 0x04
    HISTORY_WRITE = 0x08
    SEMANTIC_CHANGE = 0x10
    STATUS_WRITE = 0x20
    TIMESTAMP_WRITE = 0x40


_LABELS = {1: "Read", 2: "Write", 3: "ReadWrite"}
_NAMES = {
    "read": 1,
    "write": 2,
    "readwrite": 3,
    "currentread": 1,
    "currentwrite": 2,
    "historyread": 4,
    "historywrite": 8,
    "semanticchange": 0x10,
    "statuswrite": 0x20,
    "timestampwrite": 0x40,
}
_BIT_NAMES = (
    (AccessLevel.CURRENT_READ, "CurrentRead"),
    (AccessLevel.CURRENT_WRITE, "CurrentWrite"),
    (AccessLevel.HISTORY_READ, "HistoryRead"),
    (AccessLevel.HISTORY_WRITE, "HistoryWrite"),
    (AccessLevel.SEMANTIC_CHANGE, "SemanticChange"),
    (AccessLevel.STATUS_WRITE, "StatusWrite"),
    (AccessLevel.TIMESTAMP_WRITE, "TimestampWrite"),
)


def parse_access_level(value) -> int:
    """Accept an int, a hex string or a label. Complexity: O(1)."""
    if isinstance(value, bool) or value is None:
        raise ValueError("access level is required")
    if isinstance(value, int):
        return int(value) & _MASK
    text = str(value).strip()
    if not text:
        raise ValueError("access level is required")
    if text.lower().startswith("0x"):
        return int(text, 16) & _MASK
    key = text.lower().replace(" ", "").replace("_", "")
    if key in _NAMES:
        return _NAMES[key]
    if text.isdigit():
        return int(text) & _MASK
    raise ValueError(f"unknown access level {text}")


def access_label(level: int) -> str:
    """Human label. Combined masks join bit names. Complexity: O(1)."""
    masked = int(level) & _MASK
    if masked in _LABELS:
        return _LABELS[masked]
    names = [name for bit, name in _BIT_NAMES if masked & bit]
    return "|".join(names) if names else "None"
