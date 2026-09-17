# -*- coding: utf-8 -*-
"""In-memory filters for OPC UA Server attribute listings."""
from __future__ import annotations

from typing import Any, Mapping


def _contains(haystack: Any, needle: str) -> bool:
    if not needle:
        return True
    return needle in str(haystack if haystack is not None else "").lower()


def opcua_server_attr_matches_name(attr: Mapping[str, Any], *, name: str = "") -> bool:
    needle = str(name or "").strip().lower()
    if not needle:
        return True
    return _contains(attr.get("name"), needle) or _contains(attr.get("namespace"), needle)


def filter_opcua_server_attrs(
    attrs: list[dict],
    *,
    name: str = "",
) -> list[dict]:
    needle = str(name or "").strip()
    if not needle:
        return attrs
    return [attr for attr in attrs if opcua_server_attr_matches_name(attr, name=needle)]
