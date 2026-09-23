"""Alarm exposer: one variable plus four properties. Not AlarmConditionType."""

from __future__ import annotations

from .base import NodeExposer
from .common import apply_display_name, canonical_for, entity_area, entity_site, leaf_name

_ALARM_PROPS = ("state", "process_condition", "mnemonic", "description")


class AlarmExposer(NodeExposer):
    entity_kind = "a"

    def __init__(self, builder, nodes: dict, by_namespace: dict) -> None:
        self._builder = builder
        self._nodes = nodes
        self._by_namespace = by_namespace
        self._prop_nodes: dict[str, dict] = {}

    @property
    def entity_type(self) -> str:
        return "a"

    def owns(self, entity) -> bool:
        from ..scope import owns_tag

        return owns_tag(getattr(entity, "tag", None))

    def ensure_folder(self, builder, entity):
        return builder.ensure_branch(entity_site(entity), entity_area(entity), "Alarms")

    def upsert(self, key: str, entity):
        """Complexity: O(P), four properties."""
        identifier = canonical_for("a", entity)
        existing = self._nodes.get(identifier)
        if existing is not None:
            self.update_value(identifier, entity)
            return existing
        folder = self.ensure_folder(self._builder, entity)
        browse = leaf_name(entity, "a")
        node = self._builder.add_variable(folder, identifier, browse, 0)
        apply_display_name(node, getattr(entity, "name", browse) or browse)
        self._nodes[identifier] = node
        try:
            self._by_namespace[node.nodeid.to_string()] = node
        except Exception:
            return node
        props = {}
        state = getattr(entity, "state", None)
        serialized = state.serialize() if hasattr(state, "serialize") else {}
        for prop_key in _ALARM_PROPS:
            value = serialized.get(prop_key, getattr(entity, prop_key, ""))
            prop = self._builder.add_property(node, f"{identifier}.{prop_key}", prop_key, value if value is not None else "")
            props[prop_key] = prop
            try:
                self._by_namespace[prop.nodeid.to_string()] = prop
            except Exception:
                continue
        self._prop_nodes[identifier] = props
        return node

    def update_value(self, key: str, entity) -> None:
        identifier = key if key in self._prop_nodes else canonical_for("a", entity)
        props = self._prop_nodes.get(identifier) or {}
        state = getattr(entity, "state", None)
        serialized = state.serialize() if hasattr(state, "serialize") else {}
        for prop_key, prop in props.items():
            if prop_key == "description":
                value = serialized.get(prop_key, getattr(entity, "description", ""))
            else:
                value = serialized.get(prop_key)
                if value is None and state is not None:
                    value = getattr(state, prop_key, "")
            try:
                prop.set_value(value if value is not None else "")
            except Exception:
                continue

    def remove(self, key: str) -> None:
        node = self._nodes.pop(key, None)
        self._prop_nodes.pop(key, None)
        if node is not None:
            try:
                node.delete()
            except Exception:
                return

    def property_count(self, key: str) -> int:
        return len(self._prop_nodes.get(key, {}))


from ..registry import exposer_registry

exposer_registry.register(AlarmExposer.entity_kind, AlarmExposer)
