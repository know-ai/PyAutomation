# -*- coding: utf-8 -*-
"""Resolve the Area/Segment stamp for events and alarm-history rows.

Line/edge actions inherit the node area (or the source object's area). SAF
rejects ``area=None``; plant-wide identity actions still receive the node
area (or ``"System"``) so the journal is never dropped.
"""
from __future__ import annotations

from typing import Any, Iterable


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iter_sources(source: Any) -> Iterable[Any]:
    if source is None:
        return
    if isinstance(source, (tuple, list)):
        for item in source:
            yield from _iter_sources(item)
        return
    yield source


def _area_from_obj(obj: Any) -> str | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return _clean(obj.get("area"))
    area = _clean(getattr(obj, "area", None))
    if area:
        return area
    tag = getattr(obj, "tag", None)
    if tag is not None and tag is not obj:
        found = _area_from_obj(tag)
        if found:
            return found
    catalog = getattr(obj, "catalog_payload", None)
    if callable(catalog):
        try:
            payload = catalog() or {}
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            return _clean(payload.get("area"))
    return None


def node_area() -> str | None:
    """Area of this acquisition node, if multi-edge identity is valid."""
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except Exception:
        return None
    if getattr(scope, "enabled", False) and getattr(scope, "is_valid", False):
        return _clean(getattr(scope, "area", None))
    return None


SYSTEM_AREA = "System"


def resolve_event_area(
    *,
    area: Any = None,
    plant_wide: bool = False,
    source: Any = None,
) -> str:
    """Pick the area that should be persisted with an event.

    Never returns ``None``. Explicit ``area`` wins unless ``plant_wide=True``,
    then source.area / source.tag.area, then the current node scope, then
    ``"System"``.
    """
    if not plant_wide:
        explicit = _clean(area)
        if explicit:
            return explicit
        for item in _iter_sources(source):
            found = _area_from_obj(item)
            if found:
                return found
    node = node_area()
    if node:
        return node
    fallback = _clean(area)
    return fallback or SYSTEM_AREA
