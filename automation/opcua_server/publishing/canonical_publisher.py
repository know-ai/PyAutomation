"""Canonical plane: Objects/PyAutomationIO/{Site}/{Area}/{Process,Alarms,Engines}."""

from __future__ import annotations

from ..identity import make_node_id
from ..registry import register_publisher
from ..scope import owns_tag
from .publisher import IPublisher


def _lookup_alarm(server, name: str):
    """O(1) alarm lookup by name."""
    manager = server.alarm_manager
    if hasattr(manager, "get_alarm_by_name"):
        found = manager.get_alarm_by_name(name=name)
        if found is not None:
            return found
    alarms = manager.get_alarms() if hasattr(manager, "get_alarms") else {}
    if isinstance(alarms, dict):
        return alarms.get(name)
    return None


def _engine_name(engine) -> str:
    raw = getattr(engine, "name", "")
    return raw.value if hasattr(raw, "value") else str(raw)


@register_publisher("canonical")
class CanonicalPublisher(IPublisher):
    """All three entity kinds under PyAutomationIO. O(1) per entity."""

    plane = "canonical"

    def __init__(self, server) -> None:
        self._server = server
        self._closed = False

    def prepare(self) -> None:
        server = self._server
        if server.builder is None:
            return
        server.builder.build_tree(server.manufacturer, server.segment)

    def publish_tag(self, tag_object) -> None:
        """Enqueue a tag. Complexity: O(1). Allocations: one queue entry."""
        if self._closed:
            return
        name = getattr(tag_object, "name", None)
        if name:
            self._server.enqueue_expose("t", name)

    def publish_alarm(self, alarm_object) -> None:
        """Enqueue an alarm. Complexity: O(1)."""
        if self._closed:
            return
        name = getattr(alarm_object, "name", None)
        if name:
            self._server.enqueue_expose("a", name)

    def publish_engine(self, engine_object) -> None:
        """Enqueue an engine. Complexity: O(1)."""
        if self._closed:
            return
        name = _engine_name(engine_object)
        if name:
            self._server.enqueue_expose("e", name)

    def materialize_tag(self, tag_object) -> bool:
        server = self._server
        if tag_object is None or not owns_tag(tag_object) or server._cvt_exposer is None:
            return False
        from ..exposures.common import canonical_for

        name = tag_object.name
        ident = canonical_for("t", tag_object)
        existed = ident in server._ua_nodes
        node = server._cvt_exposer.upsert(name, tag_object)
        server._name_to_canonical[("t", name)] = ident
        server._node_id_cache[name] = ident
        self._access(node)
        return node is not None and not existed

    def materialize_alarm(self, alarm_object) -> bool:
        server = self._server
        if alarm_object is None or server._alarm_exposer is None:
            return False
        if not server._alarm_exposer.owns(alarm_object):
            return False
        from ..exposures.common import canonical_for

        name = alarm_object.name
        ident = canonical_for("a", alarm_object)
        existed = ident in server._ua_nodes
        node = server._alarm_exposer.upsert(name, alarm_object)
        server._name_to_canonical[("a", name)] = ident
        self._access(node)
        return node is not None and not existed

    def materialize_engine(self, engine_object) -> bool:
        server = self._server
        if engine_object is None or server._engine_exposer is None:
            return False
        name = _engine_name(engine_object)
        if not name or name == "OPCUAServer":
            return False
        area = getattr(engine_object, "segment", None) or getattr(engine_object, "area", None)
        area_text = area.value if hasattr(area, "value") else area
        ident = make_node_id("e", area_text, name)
        existed = ident in server._ua_nodes
        node = server._engine_exposer.upsert(name, engine_object)
        server._name_to_canonical[("e", name)] = ident
        self._access(node)
        return node is not None and not existed

    def push_tag(self, name: str, server_ts=None) -> None:
        from ..data_value import push_value

        server = self._server
        tag = server.cvt.get_tag_by_name(name=name)
        if tag is None or server._cvt_exposer is None:
            return
        ident = server._name_to_canonical.get(("t", name))
        node = server._ua_nodes.get(ident) if ident else None
        if node is not None and callable(getattr(node, "set_data_value", None)):
            push_value(node, tag, server_ts)

    def push_alarm(self, name: str, server_ts=None) -> None:
        del server_ts
        server = self._server
        if server._alarm_exposer is None:
            return
        alarm = _lookup_alarm(server, name)
        ident = server._name_to_canonical.get(("a", name))
        if alarm is not None and ident:
            server._alarm_exposer.update_value(ident, alarm)

    def push_engine(self, name: str, server_ts=None) -> None:
        del server_ts
        server = self._server
        if server._engine_exposer is None:
            return
        try:
            engine = server.machine.get_machine(name)
        except Exception:
            engine = None
        ident = server._name_to_canonical.get(("e", name))
        if engine is not None and ident:
            server._engine_exposer.update_value(ident, engine)

    def shutdown(self) -> None:
        """Idempotent. Complexity: O(1)."""
        if self._closed:
            return
        self._closed = True

    def _access(self, node) -> None:
        from ..runtime import _apply_cached_access

        _apply_cached_access(self._server, node)
