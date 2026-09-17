# -*- coding: utf-8 -*-
"""In-memory filters for serialized tags (GET /tags/). Applied before paging."""
from __future__ import annotations

from typing import Any, Mapping


def _needle(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains(haystack: Any, needle: str) -> bool:
    if not needle:
        return True
    return needle in str(haystack if haystack is not None else "").lower()


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _opcua_client_label(tag: Mapping[str, Any]) -> str:
    name = tag.get("opcua_client_name")
    if name:
        return str(name)
    address = tag.get("opcua_address")
    if address:
        return str(address)
    return "-"


def _node_label(tag: Mapping[str, Any]) -> str:
    namespace = tag.get("node_namespace")
    if namespace:
        return str(namespace)
    return "-"


def _scan_time_label(tag: Mapping[str, Any]) -> str:
    scan_time = tag.get("scan_time")
    return str(scan_time) if scan_time not in (None, "") else "-"


def _dead_band_label(tag: Mapping[str, Any]) -> str:
    if "dead_band" not in tag or tag.get("dead_band") is None:
        return "-"
    return str(tag.get("dead_band"))


def tag_matches_column_filters(
    tag: Mapping[str, Any],
    *,
    name: str = "",
    variable: str = "",
    value: str = "",
    display_unit: str = "",
    opcua_client: str = "",
    node: str = "",
    scan_time: str = "",
    dead_band: str = "",
) -> bool:
    if not _contains(tag.get("name"), name):
        return False
    if not _contains(tag.get("variable"), variable):
        return False
    if not _contains(_format_value(tag.get("value")), value):
        return False
    unit_haystack = tag.get("display_unit") if tag.get("display_unit") not in (None, "") else "-"
    if not _contains(unit_haystack, display_unit):
        return False
    if not _contains(_opcua_client_label(tag), opcua_client):
        return False
    if not _contains(_node_label(tag), node):
        return False
    if not _contains(_scan_time_label(tag), scan_time):
        return False
    if not _contains(_dead_band_label(tag), dead_band):
        return False
    return True


def filter_serialized_tags(
    tags: list[Mapping[str, Any]] | None,
    *,
    name: str = "",
    variable: str = "",
    value: str = "",
    display_unit: str = "",
    opcua_client: str = "",
    node: str = "",
    scan_time: str = "",
    dead_band: str = "",
) -> list[Mapping[str, Any]]:
    name_n = _needle(name)
    variable_n = _needle(variable)
    value_n = _needle(value)
    display_unit_n = _needle(display_unit)
    opcua_n = _needle(opcua_client)
    node_n = _needle(node)
    scan_n = _needle(scan_time)
    dead_n = _needle(dead_band)
    if not any((name_n, variable_n, value_n, display_unit_n, opcua_n, node_n, scan_n, dead_n)):
        return list(tags or [])
    matched: list[Mapping[str, Any]] = []
    for tag in tags or []:
        if not isinstance(tag, Mapping):
            continue
        if tag_matches_column_filters(
            tag,
            name=name_n,
            variable=variable_n,
            value=value_n,
            display_unit=display_unit_n,
            opcua_client=opcua_n,
            node=node_n,
            scan_time=scan_n,
            dead_band=dead_n,
        ):
            matched.append(tag)
    return matched
