"""Engine exposer: one variable plus three properties."""

from __future__ import annotations

from .base import NodeExposer
from .common import apply_display_name, leaf_name
from ..identity import make_node_id

_ENGINE_PROPS = ("state", "classification", "fluid")


def _text(value) -> str:
    if value is None:
        return ""
    inner = getattr(value, "value", value)
    return "" if inner is None else str(inner)


class EngineExposer(NodeExposer):
    entity_kind = "e"

    def __init__(self, builder, nodes: dict, by_namespace: dict) -> None:
        self._builder = builder
        self._nodes = nodes
        self._by_namespace = by_namespace
        self._prop_nodes: dict[str, dict] = {}

    @property
    def entity_type(self) -> str:
        return "e"

    def owns(self, entity) -> bool:
        return entity is not None

    def ensure_folder(self, builder, entity):
        site = getattr(entity, "manufacturer", None)
        area = getattr(entity, "segment", None) or getattr(entity, "area", None)
        from ..grouping import engine_folder_name

        return builder.ensure_group(site, area, "Engines", engine_folder_name(entity))

    def _name(self, entity) -> str:
        name = getattr(entity, "name", "")
        return _text(name)

    def upsert(self, key: str, entity):
        """Complexity: O(P), three properties."""
        name = self._name(entity)
        area = getattr(entity, "segment", None) or getattr(entity, "area", None)
        identifier = make_node_id("e", _text(area) or None, name)
        existing = self._nodes.get(identifier)
        if existing is not None:
            self.update_value(identifier, entity)
            return existing
        folder = self.ensure_folder(self._builder, entity)
        browse = leaf_name(type("E", (), {"name": name, "display_name": name})(), "e")
        node = self._builder.add_variable(folder, identifier, browse, 0)
        apply_display_name(node, name)
        self._nodes[identifier] = node
        try:
            self._by_namespace[node.nodeid.to_string()] = node
        except Exception:
            return node
        payload = entity.serialize() if hasattr(entity, "serialize") else {}
        props = {}
        for prop_key in _ENGINE_PROPS:
            prop = self._builder.add_property(
                node, f"{identifier}.{prop_key}", prop_key, _text(payload.get(prop_key, getattr(entity, prop_key, "")))
            )
            props[prop_key] = prop
        self._prop_nodes[identifier] = props
        return node

    def update_value(self, key: str, entity) -> None:
        name = self._name(entity)
        area = getattr(entity, "segment", None) or getattr(entity, "area", None)
        identifier = key if key in self._prop_nodes else make_node_id("e", _text(area) or None, name)
        props = self._prop_nodes.get(identifier) or {}
        payload = entity.serialize() if hasattr(entity, "serialize") else {}
        for prop_key, prop in props.items():
            try:
                prop.set_value(_text(payload.get(prop_key, getattr(entity, prop_key, ""))))
            except Exception:
                continue

    def remove(self, key: str) -> None:
        self._nodes.pop(key, None)
        self._prop_nodes.pop(key, None)

    def property_count(self, key: str) -> int:
        return len(self._prop_nodes.get(key, {}))


from ..registry import exposer_registry

exposer_registry.register(EngineExposer.entity_kind, EngineExposer)
