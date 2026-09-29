"""CVT tag exposer. At most 5 properties (6 nodes including the variable)."""

from __future__ import annotations

import json

from .base import NodeExposer
from .common import apply_display_name, canonical_for, entity_area, entity_site, leaf_name, published_unit
from ..data_value import push_value
from ..identity import classify_entity_kind

_MAX_PROPS = 5


def _eu_range(data_range):
    """Range when both ends are numeric. Complexity: O(1)."""
    low, high = _range_ends(data_range)
    try:
        from asyncua import ua

        rng = ua.Range()
        rng.Low = float(low)
        rng.High = float(high)
        return rng
    except Exception:
        return str(data_range)


def _range_ends(data_range):
    if isinstance(data_range, (tuple, list)) and len(data_range) >= 2:
        return data_range[0], data_range[1]
    low = getattr(data_range, "Low", None)
    high = getattr(data_range, "High", None)
    if low is None:
        low = getattr(data_range, "low", None)
    if low is None:
        low = getattr(data_range, "min", None)
    if high is None:
        high = getattr(data_range, "high", None)
    if high is None:
        high = getattr(data_range, "max", None)
    return low, high


class CvtExposer(NodeExposer):
    entity_kind = "t"

    def __init__(self, builder, nodes: dict, by_namespace: dict) -> None:
        self._builder = builder
        self._nodes = nodes
        self._by_namespace = by_namespace
        self._props: dict[str, dict] = {}

    @property
    def entity_type(self) -> str:
        return "t"

    def owns(self, entity) -> bool:
        from ..scope import owns_tag

        return owns_tag(entity)

    def ensure_folder(self, builder, entity):
        from ..grouping import engine_groups_for_tag

        groups = engine_groups_for_tag(str(getattr(entity, "name", "") or ""))
        if groups:
            return builder.ensure_group(entity_site(entity), entity_area(entity), "Engines", groups[0])
        from ..grouping import browse_under_default

        return builder.ensure_branch(
            entity_site(entity),
            entity_area(entity),
            "Process",
            under_default=browse_under_default("t", str(getattr(entity, "name", "") or "")),
        )

    def _prop(self, node, identifier: str, key: str, value, bucket: list) -> None:
        if len(bucket) >= _MAX_PROPS:
            return
        prop = self._builder.add_property(node, f"{identifier}.{key}", key, value)
        bucket.append(key)
        self._remember(prop)

    def _remember(self, node) -> None:
        try:
            self._by_namespace[node.nodeid.to_string()] = node
        except Exception:
            return

    def upsert(self, key: str, entity):
        """Create or refresh a tag. Complexity: O(P), P <= 5."""
        identifier = canonical_for("t", entity)
        existing = self._nodes.get(identifier)
        if existing is not None:
            self.update_value(identifier, entity)
            return existing
        folder = self.ensure_folder(self._builder, entity)
        data_type = ""
        if hasattr(entity, "get_data_type"):
            data_type = entity.get_data_type() or ""
        else:
            data_type = getattr(entity, "data_type", "") or ""
        variable = ""
        if hasattr(entity, "get_variable"):
            variable = entity.get_variable() or ""
        kind = classify_entity_kind(variable, data_type)
        initial = "" if kind == "string" else (False if kind == "bool" else 0.0)
        browse = leaf_name(entity, "t")
        node = self._builder.add_variable(folder, identifier, browse, initial)
        apply_display_name(node, browse)
        if kind == "analog":
            self._builder.try_analog_item(node)
        self._nodes[identifier] = node
        self._remember(node)
        props: list[str] = []
        unit = published_unit(entity)
        if kind == "analog":
            self._prop(node, identifier, "unit", unit or "", props)
        self._prop(node, identifier, "variable", variable or "", props)
        if kind == "analog":
            data_range = getattr(entity, "data_range", None)
            if data_range:
                self._prop(node, identifier, "EURange", _eu_range(data_range), props)
            runtime = {}
            scan = entity.get_scan_time() if hasattr(entity, "get_scan_time") else None
            if scan:
                runtime["scan_time"] = scan
            dead = entity.get_dead_band() if hasattr(entity, "get_dead_band") else None
            if dead:
                runtime["dead_band"] = dead
            if runtime:
                self._prop(node, identifier, "runtime_config", json.dumps(runtime), props)
            if getattr(entity, "filter_enabled", False):
                self._prop(
                    node,
                    identifier,
                    "filter_config",
                    json.dumps(
                        {
                            "enabled": True,
                            "wavelet": getattr(entity, "filter_wavelet", None),
                            "level": getattr(entity, "filter_level", None),
                            "threshold_factor": getattr(entity, "filter_threshold_factor", None),
                        }
                    ),
                    props,
                )
        self._props[identifier] = {name: name for name in props}
        self.update_value(identifier, entity)
        return node

    def update_value(self, key: str, entity) -> None:
        node = self._nodes.get(key) or self._nodes.get(canonical_for("t", entity))
        if node is None or not callable(getattr(node, "set_data_value", None)):
            return
        push_value(node, entity)

    def remove(self, key: str) -> None:
        node = self._nodes.pop(key, None)
        if node is None:
            return
        try:
            self._by_namespace.pop(node.nodeid.to_string(), None)
        except Exception:
            node = None
        self._props.pop(key, None)
        try:
            node.delete()
        except Exception:
            return None

    def node_count(self, key: str) -> int:
        node = self._nodes.get(key)
        if node is None:
            return 0
        try:
            return 1 + len(node.get_properties())
        except Exception:
            return 1 + len(self._props.get(key, {}))


from ..registry import exposer_registry

exposer_registry.register(CvtExposer.entity_kind, CvtExposer)
