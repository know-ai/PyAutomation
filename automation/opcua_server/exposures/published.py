"""Live OPC UA properties for alarms and engines.

Tags already follow the CVT observer. These pairs are the alarm and engine
fields the address space rewrites when the application changes them.
"""

from __future__ import annotations

import json

_ALARM_FIELDS = (
    "state",
    "process_condition",
    "mnemonic",
    "alarm_status",
    "annunciate_status",
    "acknowledge_status",
    "description",
    "display_name",
    "tag",
    "alarm_type",
    "trigger_value",
    "on_delay",
    "off_delay",
    "on_delay_units",
    "off_delay_units",
    "timestamp",
    "ack_timestamp",
    "condition_met",
    "delay_phase",
    "last_transition_from",
    "last_transition_to",
)

_ENGINE_FIRST = (
    "state",
    "classification",
    "description",
    "threshold",
    "on_delay",
    "criticity",
    "priority",
)
_ENGINE_LIVE = ("criticity", "priority")
# Nombres que solo publica el motor que los declara en ``opcua_attributes``.
_ENGINE_OPT_IN = frozenset({"maneuver", "fluid", "operation"})
_ENGINE_SKIP = frozenset({"manufacturer", "segment", "has_domain_config"})
_ENGINE_CONFIG_PVS = frozenset({"threshold"})


def _plain(value):
    if value is None:
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    inner = getattr(value, "value", None)
    if isinstance(inner, (bool, int, float, str)):
        return inner
    return str(value)


def _is_process_variable(value) -> bool:
    """Live CVT binding. The tag node already publishes this value."""
    return isinstance(value, dict) and "value" in value and "tag" in value and "unit" in value


def _engine_value(key: str, value):
    if _is_process_variable(value):
        if key not in _ENGINE_CONFIG_PVS:
            return None
        return _plain(value.get("value"))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), default=str)
    return _plain(value)


def alarm_properties(entity) -> tuple[tuple[str, object], ...]:
    """O(P) snapshot of the alarm fields published as OPC UA properties."""
    state = getattr(entity, "state", None)
    serialized = state.serialize() if hasattr(state, "serialize") else {}
    if not isinstance(serialized, dict):
        serialized = {}
    setpoint = {}
    trigger = getattr(entity, "alarm_setpoint", None)
    if hasattr(trigger, "serialize"):
        try:
            raw = trigger.serialize()
        except Exception:
            raw = None
        if isinstance(raw, dict):
            setpoint = raw
    tag = getattr(entity, "tag", None)
    tag_name = getattr(tag, "name", "") if tag is not None and not isinstance(tag, str) else (tag or "")
    on_delay = entity._on_delay_s() if callable(getattr(entity, "_on_delay_s", None)) else getattr(entity, "on_delay", "")
    off_delay = entity._off_delay_s() if callable(getattr(entity, "_off_delay_s", None)) else getattr(entity, "off_delay", "")
    delay_phase = entity._delay_phase() if callable(getattr(entity, "_delay_phase", None)) else getattr(entity, "delay_phase", "")
    condition = getattr(entity, "_condition_met", getattr(entity, "condition_met", ""))
    values = {
        "state": serialized.get("state", getattr(state, "state", "")),
        "process_condition": serialized.get("process_condition", getattr(state, "process_condition", "")),
        "mnemonic": serialized.get("mnemonic", getattr(state, "mnemonic", "")),
        "alarm_status": serialized.get("alarm_status", getattr(state, "alarm_status", "")),
        "annunciate_status": serialized.get("annunciate_status", getattr(state, "annunciate_status", "")),
        "acknowledge_status": serialized.get("acknowledge_status", getattr(state, "acknowledge_status", "")),
        "description": serialized.get("description", getattr(entity, "description", "")),
        "display_name": getattr(entity, "display_name", ""),
        "tag": tag_name,
        "alarm_type": setpoint.get("type", getattr(entity, "alarm_type", "")),
        "trigger_value": setpoint.get("value", getattr(entity, "trigger_value", "")),
        "on_delay": on_delay,
        "off_delay": off_delay,
        "on_delay_units": getattr(entity, "on_delay_units", ""),
        "off_delay_units": getattr(entity, "off_delay_units", ""),
        "timestamp": getattr(entity, "timestamp", ""),
        "ack_timestamp": getattr(entity, "ack_timestamp", ""),
        "condition_met": condition,
        "delay_phase": delay_phase,
        "last_transition_from": getattr(entity, "last_transition_from", ""),
        "last_transition_to": getattr(entity, "last_transition_to", ""),
    }
    return tuple((key, _plain(values.get(key))) for key in _ALARM_FIELDS)


def engine_properties(entity) -> tuple[tuple[str, object], ...]:
    """O(A) scalar attributes. Process variables stay on their tag nodes."""
    payload = entity.serialize() if hasattr(entity, "serialize") else {}
    if not isinstance(payload, dict):
        payload = {}
    ordered: list[tuple[str, object]] = []
    seen: set[str] = set()
    opt_in = _opt_in_keys(entity)

    def add(key: str) -> None:
        if key in _ENGINE_OPT_IN and key not in opt_in:
            return
        if key in seen or key in _ENGINE_SKIP or key.startswith("_") or key not in payload:
            return
        value = payload[key]
        published = _engine_value(key, value)
        if published is None and _is_process_variable(value):
            return
        seen.add(key)
        ordered.append((key, "" if published is None else published))

    for key in _ENGINE_FIRST:
        add(key)
    for key in sorted(payload):
        add(key)
    for key in _ENGINE_LIVE:
        if key in seen:
            continue
        live = _live_scalar(entity, key)
        if live is None:
            continue
        seen.add(key)
        ordered.append((key, live))
    for key in opt_in:
        if key in seen:
            continue
        live = _live_scalar(entity, key)
        if live is None and key in payload:
            live = _engine_value(key, payload[key])
        if live is None:
            continue
        seen.add(key)
        ordered.append((key, live))
    return tuple(ordered)


def _opt_in_keys(entity) -> tuple[str, ...]:
    raw = getattr(entity, "opcua_attributes", ()) or ()
    keys = []
    for key in raw:
        text = str(key or "").strip()
        if text and text not in keys:
            keys.append(text)
    return tuple(keys)


def _live_scalar(entity, key: str):
    """Read an IntegerType-style attribute when serialize() omitted it."""
    if not hasattr(entity, key):
        return None
    raw = getattr(entity, key)
    if raw is None:
        return None
    return _plain(getattr(raw, "value", raw))
