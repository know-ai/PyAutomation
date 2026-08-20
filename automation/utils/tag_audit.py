# -*- coding: utf-8 -*-
"""Human-readable change lists for Tag configuration events."""
from __future__ import annotations

from typing import Any, Callable

_GETTERS: tuple[tuple[str, Callable[[Any], Any]], ...] = (
    ("name", lambda t: getattr(t, "name", None)),
    ("display_name", lambda t: t.get_display_name() if hasattr(t, "get_display_name") else getattr(t, "display_name", None)),
    ("unit", lambda t: t.get_unit() if hasattr(t, "get_unit") else getattr(t, "unit", None)),
    ("display_unit", lambda t: t.get_display_unit() if hasattr(t, "get_display_unit") else getattr(t, "display_unit", None)),
    ("data_type", lambda t: t.get_data_type() if hasattr(t, "get_data_type") else getattr(t, "data_type", None)),
    ("description", lambda t: t.get_description() if hasattr(t, "get_description") else getattr(t, "description", None)),
    ("variable", lambda t: t.get_variable() if hasattr(t, "get_variable") else getattr(t, "variable", None)),
    ("opcua_address", lambda t: t.get_opcua_address() if hasattr(t, "get_opcua_address") else getattr(t, "opcua_address", None)),
    ("opcua_client_name", lambda t: t.get_opcua_client_name() if hasattr(t, "get_opcua_client_name") else getattr(t, "opcua_client_name", None)),
    ("node_namespace", lambda t: t.get_node_namespace() if hasattr(t, "get_node_namespace") else getattr(t, "node_namespace", None)),
    ("scan_time", lambda t: t.get_scan_time() if hasattr(t, "get_scan_time") else getattr(t, "scan_time", None)),
    ("dead_band", lambda t: t.get_dead_band() if hasattr(t, "get_dead_band") else getattr(t, "dead_band", None)),
    ("segment", lambda t: getattr(t, "segment", None)),
    ("manufacturer", lambda t: getattr(t, "manufacturer", None)),
    ("kp", lambda t: t.get_kp() if hasattr(t, "get_kp") else getattr(t, "kp", None)),
    ("filter_enabled", lambda t: getattr(t, "filter_enabled", None)),
    ("filter_wavelet", lambda t: getattr(t, "filter_wavelet", None)),
    ("filter_level", lambda t: getattr(t, "filter_level", None)),
    ("filter_threshold_factor", lambda t: getattr(t, "filter_threshold_factor", None)),
    ("filter_persist", lambda t: getattr(t, "filter_persist", None)),
)


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".6g")
    return str(value)


def _norm(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".6g")
    text = str(value).strip()
    if text.lower() in {"true", "yes", "on"}:
        return "1"
    if text.lower() in {"false", "no", "off"}:
        return "0"
    return text


def describe_tag_update(tag: Any, kwargs: dict) -> str:
    """Build ``Tag: NAME; field: old → new; ...`` from applied kwargs."""
    name = _fmt(getattr(tag, "name", None) or kwargs.get("name") or "")
    changes: list[str] = []
    for key, getter in _GETTERS:
        if key not in kwargs:
            continue
        try:
            old = getter(tag)
        except Exception:
            old = None
        new = kwargs.get(key)
        if _norm(old) == _norm(new):
            continue
        changes.append(f"{key}: {_fmt(old)} → {_fmt(new)}")
    if not changes:
        return f"Tag: {name}"
    return f"Tag: {name}; " + "; ".join(changes)
