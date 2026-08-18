# -*- coding: utf-8 -*-
"""Resolve the Area/Segment stamp for events and alarm-history rows.

Line/edge actions inherit the node area (or the source object's area). Plant-wide
identity actions — user create, password, role — must keep ``area=None``.
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


def resolve_event_area(
    *,
    area: Any = None,
    plant_wide: bool = False,
    source: Any = None,
) -> str | None:
    """Pick the area that should be persisted with an event.

    * ``plant_wide=True`` → always ``None`` (whole-plant identity actions).
    * else explicit ``area``, then ``source.area`` / ``source.tag.area``,
      then the current node scope.
    """
    if plant_wide:
        return None
    explicit = _clean(area)
    if explicit:
        return explicit
    for item in _iter_sources(source):
        found = _area_from_obj(item)
        if found:
            return found
    return node_area()
