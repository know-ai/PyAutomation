"""Status codes for one client write. Complexity: O(1)."""

from __future__ import annotations

import math

from asyncua import ua

from .level import AccessLevel


def _good(status) -> bool:
    if status is None:
        return True
    value = getattr(status, "value", status)
    try:
        return int(value) == 0 or bool(getattr(status, "is_good", lambda: False)())
    except (TypeError, ValueError):
        return False


def check_value_write(
    access_level: int,
    user_access_level: int,
    *,
    status_code=None,
    explicit_timestamp: bool = False,
    value=None,
    expected: str | None = None,
    low: float | None = None,
    high: float | None = None,
    rate_ok: bool = True,
):
    """Return a StatusCode, or None when the write may proceed. Complexity: O(1)."""
    access = int(access_level)
    user = int(user_access_level)
    if not access & AccessLevel.CURRENT_WRITE:
        return ua.StatusCodes.BadNotWritable
    if not user & AccessLevel.CURRENT_WRITE:
        return ua.StatusCodes.BadUserAccessDenied
    if not _good(status_code) and not access & AccessLevel.STATUS_WRITE:
        return ua.StatusCodes.BadNotWritable
    if explicit_timestamp and not access & AccessLevel.TIMESTAMP_WRITE:
        return ua.StatusCodes.BadNotWritable
    if expected and not _type_ok(value, expected):
        return ua.StatusCodes.BadTypeMismatch
    if not _in_range(value, low, high):
        return ua.StatusCodes.BadOutOfRange
    if not rate_ok:
        return ua.StatusCodes.BadTooManyOperations
    return None


def check_history_read(access_level: int):
    """History read without the bit. Complexity: O(1)."""
    if int(access_level) & AccessLevel.HISTORY_READ:
        return None
    return ua.StatusCodes.BadUserAccessDenied


def check_history_write(access_level: int):
    """History write without the bit. Complexity: O(1)."""
    if int(access_level) & AccessLevel.HISTORY_WRITE:
        return None
    return ua.StatusCodes.BadNotWritable


def _type_ok(value, expected: str) -> bool:
    kind = expected.lower()
    if kind in {"bool", "boolean"}:
        return isinstance(value, bool)
    if kind in {"string", "str"}:
        return isinstance(value, str)
    if kind in {"analog", "float", "number", "int"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _in_range(value, low, high) -> bool:
    if low is None or high is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return float(low) <= float(value) <= float(high)
