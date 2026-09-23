"""DataValue with StatusCode and timestamps.

Status codes for the four severities are cached. Variants are built by a type factory.
Complexity: each conversion is O(1).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..signal_conditioning.quality import BAD, GOOD, UNCERTAIN

_STATUS_CODES: dict = {}
_VARIANT_FACTORY: dict = {}


def _status_codes() -> dict:
    if _STATUS_CODES:
        return _STATUS_CODES
    from asyncua import ua

    _STATUS_CODES["good"] = ua.StatusCode(ua.StatusCodes.Good)
    _STATUS_CODES["uncertain"] = ua.StatusCode(ua.StatusCodes.Uncertain)
    _STATUS_CODES["bad"] = ua.StatusCode(ua.StatusCodes.Bad)
    _STATUS_CODES["stale"] = ua.StatusCode(ua.StatusCodes.BadWaitingForInitialData)
    return _STATUS_CODES


def _variant_factory() -> dict:
    if _VARIANT_FACTORY:
        return _VARIANT_FACTORY
    from asyncua import ua

    _VARIANT_FACTORY["bool"] = lambda value: ua.Variant(bool(value), ua.VariantType.Boolean)
    _VARIANT_FACTORY["float"] = lambda value: ua.Variant(round(float(value), 4), ua.VariantType.Double)
    _VARIANT_FACTORY["int"] = lambda value: ua.Variant(int(value), ua.VariantType.Int64)
    _VARIANT_FACTORY["other"] = lambda value: ua.Variant(value)
    return _VARIANT_FACTORY


def _variant(raw):
    factory = _variant_factory()
    if isinstance(raw, bool):
        return factory["bool"](raw)
    if isinstance(raw, float):
        return factory["float"](raw)
    if isinstance(raw, int):
        return factory["int"](raw)
    return factory["other"](raw)


def _as_utc(value, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(fallback, datetime):
        return fallback
    return datetime.now(timezone.utc)


def quality_to_status_code(tag_object):
    """Map CVT quality onto a cached StatusCode. Complexity: O(1)."""
    codes = _status_codes()
    if bool(getattr(tag_object, "stale", False)):
        return codes["stale"]
    opc_code = getattr(tag_object, "opc_status_code", None)
    if opc_code:
        try:
            from asyncua import ua

            return ua.StatusCode(opc_code)
        except Exception:
            opc_code = None
    try:
        quality = float(getattr(tag_object, "quality", GOOD))
    except (TypeError, ValueError):
        quality = BAD
    if quality >= 0.9:
        return codes["good"]
    if quality >= UNCERTAIN:
        return codes["uncertain"]
    return codes["bad"]


def to_data_value(tag_object, server_ts=None):
    """Build a DataValue with Value, StatusCode, SourceTimestamp, ServerTimestamp. Complexity: O(1)."""
    from asyncua import ua

    raw = tag_object.get_value() if hasattr(tag_object, "get_value") else getattr(tag_object, "value", None)
    if hasattr(raw, "value"):
        raw = raw.value
    stamp = server_ts if isinstance(server_ts, datetime) else None
    source = None
    for attr in ("data_timestamp", "timestamp"):
        source = getattr(tag_object, attr, None)
        if source:
            break
    if source is None and hasattr(tag_object, "get_timestamp"):
        source = tag_object.get_timestamp()
    data_value = ua.DataValue(_variant(raw))
    data_value.StatusCode = quality_to_status_code(tag_object)
    data_value.SourceTimestamp = _as_utc(source, stamp)
    data_value.ServerTimestamp = stamp or datetime.now(timezone.utc)
    return data_value


def push_value(node, tag_object, server_ts=None) -> None:
    """Write one DataValue. Complexity: O(1)."""
    node.set_data_value(to_data_value(tag_object, server_ts=server_ts))
