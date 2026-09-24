"""Shared helpers for exposers."""

from __future__ import annotations

from ..identity import make_browse_name, make_node_id, short_browse_name


def entity_area(entity) -> str | None:
    area = getattr(entity, "area", None) or getattr(entity, "segment", None)
    if not area and hasattr(entity, "tag"):
        tag = entity.tag
        area = getattr(tag, "area", None) or getattr(tag, "segment", None)
    return area or None


def entity_site(entity) -> str | None:
    site = getattr(entity, "manufacturer", None)
    if not site and hasattr(entity, "tag"):
        site = getattr(entity.tag, "manufacturer", None)
    return site or None


def leaf_name(entity, entity_type: str) -> str:
    qualified = _plain(getattr(entity, "name", ""))
    if entity_type == "a":
        return alarm_browse_name(qualified or str(getattr(entity, "display_name", "") or ""))
    display = getattr(entity, "display_name", None) or qualified
    return short_browse_name(str(display or qualified), entity_type)


def alarm_browse_name(qualified_name: str) -> str:
    """Keep the engine segment so ``ppa.leak`` is not shown as ``leak``."""
    parts = [part for part in str(qualified_name or "").strip().split(".") if part]
    if len(parts) >= 2:
        return make_browse_name(f"{parts[-2]}.{parts[-1]}", "a")
    return make_browse_name(parts[-1] if parts else "", "a")


_CANONICAL_CACHE: dict[tuple[str, str, str], str] = {}


def _plain(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value") and not isinstance(value, str):
        value = value.value
    return str(value or "")


def _cache_key(entity_type: str, area: str | None, name: str) -> tuple[str, str, str]:
    return (entity_type, _plain(area), _plain(name))


def remember_node_id(entity_type: str, area: str | None, name: str, identifier: str) -> None:
    """Store one canonical id. Complexity: O(1)."""
    _CANONICAL_CACHE[_cache_key(entity_type, area, name)] = identifier


def clear_canonical_cache() -> None:
    """Drop precomputed ids. Complexity: O(1) for the dict clear."""
    _CANONICAL_CACHE.clear()


def canonical_for(entity_type: str, entity) -> str:
    """Return the cached NodeId. Complexity: O(1) after precompute."""
    area = entity_area(entity)
    name = _plain(getattr(entity, "name", "") or "")
    key = _cache_key(entity_type, area, name)
    cached = _CANONICAL_CACHE.get(key)
    if cached is not None:
        return cached
    identifier = make_node_id(entity_type, area, name)
    _CANONICAL_CACHE[key] = identifier
    return identifier


def set_display(node, text: str) -> None:
    try:
        from asyncua import ua

        attr = node.get_attribute(ua.AttributeIds.DisplayName)
        attr.Value.Value.Text = text
        node.set_attribute(ua.AttributeIds.DisplayName, attr.Value)
    except Exception:
        try:
            node.set_attribute = node.set_attribute
        except Exception:
            return


def apply_display_name(node, text: str) -> None:
    """Best-effort DisplayName. python-opcua nodes accept set via attribute write."""
    try:
        from asyncua import ua

        display = node.get_display_name()
        display.Text = text or ""
        value = ua.DataValue(ua.Variant(display))
        node.set_attribute(ua.AttributeIds.DisplayName, value)
    except Exception:
        return


def browse_label(name: str, entity_type: str) -> str:
    return make_browse_name(name, entity_type)


def published_unit(entity) -> str:
    """Unit of the value this server publishes. That value is already in the display unit."""
    display = ""
    getter = getattr(entity, "get_display_unit", None)
    if callable(getter):
        display = getter() or ""
    if not display:
        display = getattr(entity, "display_unit", None) or ""
    if display:
        return str(display)
    getter = getattr(entity, "get_unit", None)
    if callable(getter):
        return str(getter() or "")
    return str(getattr(entity, "unit", "") or "")
