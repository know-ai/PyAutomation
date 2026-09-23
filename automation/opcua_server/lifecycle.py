"""Reset, snapshot and dirty marks. The facade delegates here.

Complexity: reset is O(1) clears. Snapshot is O(1). Each mark is O(1).
"""

from __future__ import annotations

import logging
import time

from .audit import audit_failure
from .listing import list_attrs as _list_attrs

_LOG = logging.getLogger("pyautomation")


def mark_tag(server, tag) -> None:
    """Mark one tag dirty. Complexity: O(1)."""
    name = getattr(tag, "name", None)
    if not name:
        return
    value = tag.get_value() if hasattr(tag, "get_value") else None
    server.tag_tracker.mark(name, value)
    server._last_touch[name] = time.monotonic()


def mark_tag_name(server, name: str) -> None:
    """Resolve a tag by name and mark it. Complexity: O(1)."""
    tag = server.cvt.get_tag_by_name(name=name) if name else None
    if tag is not None:
        mark_tag(server, tag)


def mark_alarm(server, name: str) -> None:
    """Mark one alarm dirty. Complexity: O(1)."""
    if name:
        server.alarm_tracker.mark(name, None)


def mark_engine(server, name: str) -> None:
    """Mark one engine dirty. Complexity: O(1)."""
    if name and name != "OPCUAServer":
        server.engine_tracker.mark(name, None)


def build_snapshot(server) -> dict:
    """Copy the health gauges. Complexity: O(1). Allocations: one dict."""
    structures = {
        "ua_nodes": len(server._ua_nodes),
        "expose_queue": len(server._expose_queue),
        "dirty_tags": len(server._dirty_tags),
        "dirty_alarms": len(server._dirty_alarms),
        "dirty_engines": len(server._dirty_engines),
        "node_id_cache": len(server._node_id_cache),
        "access_cache": len(server._access_cache),
        "write_subscriptions": server.writeback.active,
        "last_value": len(server._last_value),
        "dead_bands": len(server._dead_bands),
    }
    from .identity import folder_token

    server.metrics.write_subscriptions = server.writeback.active
    return server.metrics.as_dict(
        ready=server._opcua_ready,
        namespace_idx=server._namespace_idx,
        structures=structures,
        host=getattr(server, "host", "0.0.0.0"),
        port=getattr(server, "port", 0),
        site=folder_token(getattr(server, "manufacturer", None), "Default"),
        area=folder_token(getattr(server, "segment", None), "Global"),
    )


def list_nodes(server) -> list:
    """List exposed variables. Complexity: O(V) in the node map."""
    return _list_attrs(server)


def apply_node_access(server, node, access_level) -> None:
    """Remember and apply one AccessLevel. Complexity: O(1) to enqueue."""
    from .access.level import parse_access_level
    from .runtime import _apply_cached_access

    namespace = node.nodeid.to_string()
    try:
        level = parse_access_level(access_level)
    except ValueError:
        level = 1
    server.access.remember(namespace, level)
    if not int(level) & 0x02:
        server.writeback.unsubscribe(namespace)
    _apply_cached_access(server, node)


def reset_structures(server) -> None:
    """Stop the endpoint and clear every map. Complexity: O(1) dict.clear calls."""
    runner = getattr(server, "runner", None)
    if runner is not None:
        try:
            runner.stop()
        except Exception:
            audit_failure("OPC UA server stop failed", "reset")
        server.runner = None
    else:
        try:
            if server.server is not None:
                server.server.stop()
        except Exception:
            audit_failure("OPC UA server stop failed", "reset")
    audit_failure("OPC UA server reset", "reset", criticity=3)
    publisher = getattr(server, "publisher", None)
    if publisher is not None:
        publisher.shutdown()
    for name, observer in list(server._tag_observers.items()):
        tag = server.cvt.get_tag_by_name(name=name) if name else None
        if tag is None:
            continue
        try:
            tag.detach(observer)
        except Exception:
            _LOG.debug("OPC UA observer detach skipped", exc_info=True)
    server.server = None
    server.objects = None
    server.builder = None
    server._cvt_exposer = None
    server._alarm_exposer = None
    server._engine_exposer = None
    server.writeback.clear()
    server._ua_nodes.clear()
    server._by_namespace.clear()
    listings = getattr(server, "_node_listings", None)
    if hasattr(listings, "clear"):
        listings.clear()
    server._expose_queue.clear()
    server._expose_seen.clear()
    server._dirty_tags.clear()
    server._dirty_alarms.clear()
    server._dirty_engines.clear()
    server._node_id_cache.clear()
    from .exposures.common import clear_canonical_cache

    clear_canonical_cache()
    server._access_cache.clear()
    for attr in ("_access_policy", "_write_limits", "_opc_names", "_client_write_marks"):
        bucket = getattr(server, attr, None)
        if hasattr(bucket, "clear"):
            bucket.clear()
    server._last_value.clear()
    server._dead_bands.clear()
    server._last_touch.clear()
    server._tag_observers.clear()
    server._watch_order.clear()
    server._name_to_canonical.clear()
    server._watch_index = 0
    server._tick_counter = 0
    server._opcua_ready = False
    server._opcua_endpoint_up = False
    server._opcua_space_loaded = False
    server._namespace_idx = 0
    server.metrics.nodes_tags = 0
    server.metrics.nodes_alarms = 0
    server.metrics.nodes_engines = 0
    from .bridge import unbind

    unbind(server)
