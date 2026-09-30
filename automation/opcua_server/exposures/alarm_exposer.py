"""Alarm exposer: one variable plus the live alarm fields. Not AlarmConditionType."""

from __future__ import annotations

from .base import NodeExposer
from .common import apply_display_name, canonical_for, entity_area, entity_site, leaf_name
from .published import alarm_properties
from ..identity import property_node_id


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
        from ..grouping import browse_under_default

        return builder.ensure_branch(
            entity_site(entity),
            entity_area(entity),
            "Alarms",
            under_default=browse_under_default("a", str(getattr(entity, "name", "") or "")),
        )

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
        props = self._write_properties(identifier, node, entity)
        self._prop_nodes[identifier] = props
        return node

    def update_value(self, key: str, entity) -> None:
        identifier = key if key in self._prop_nodes or key in self._nodes else canonical_for("a", entity)
        node = self._nodes.get(identifier)
        props = self._prop_nodes.setdefault(identifier, {})
        written = self._write_properties(identifier, node, entity, props)
        self._prop_nodes[identifier] = written

    def _write_properties(self, identifier: str, node, entity, props: dict | None = None) -> dict:
        current = dict(props or {})
        for prop_key, value in alarm_properties(entity):
            published = "" if value is None else value
            prop = current.get(prop_key)
            if prop is None and node is not None:
                prop = self._builder.add_property(
                    node, property_node_id(identifier, prop_key), prop_key, published
                )
                current[prop_key] = prop
                try:
                    self._by_namespace[prop.nodeid.to_string()] = prop
                except Exception:
                    pass
                continue
            if prop is None:
                continue
            try:
                prop.set_value(published)
            except Exception:
                continue
        return current

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
