"""Cold start of the embedded server.

The endpoint and the folder tree are built once. Existing entities are enqueued,
not materialized, so ``while_starting`` stays off the per-node path (L-START-1).
Complexity: O(N + M + E) enqueues, plus one access prefetch.
"""

from __future__ import annotations

import logging
import time

from .analog_item import apply_analog_fallback
from .async_core.commands import StartEndpoint
from .async_core.runner import AsyncioRunner
from .bridge import bind
from .exposures.alarm_exposer import AlarmExposer
from .exposures.common import canonical_for
from .exposures.cvt_exposer import CvtExposer
from .exposures.engine_exposer import EngineExposer
from .flags import namespace_uri, server_host
from .registry import exposer_registry, lint_registry, publisher_registry
from .scope import owns_tag
from .watchdog import bind_watchdog

_LOG = logging.getLogger("pyautomation")


def start_endpoint(server) -> bool:
    """Open the endpoint. Complexity: O(N + M + E) enqueues. False retries without a rebuild."""
    if getattr(server, "_opcua_ready", False):
        server.send("start_to_wait")
        return False
    if getattr(server, "runner", None) is None:
        from pathlib import Path

        host = getattr(server, "host", None) or server_host()
        server.host = host
        server.runner = AsyncioRunner(server)
        server.runner.start()
        shelf = Path(f"opcua_standard_aspace_{server.port}.shelf")
        server.runner.submit(
            StartEndpoint(
                host=str(host),
                port=int(server.port),
                namespace_uri=namespace_uri(),
                shelf_file=str(shelf),
            )
        )
    if not getattr(server, "_opcua_endpoint_up", False):
        if not server.runner.wait_ready(30):
            return False
        if server.runner.error is not None:
            err = server.runner.error
            server.runner.error = None
            busy = getattr(err, "errno", None) == 98 or "address already in use" in str(err).lower()
            if busy:
                server.runner.stop()
                server.runner = None
                _LOG.warning(
                    "OPC UA server port %s busy; retrying without rebuilding address space",
                    server.port,
                )
                time.sleep(1.0)
                return False
            raise err
        server._opcua_endpoint_up = True
        if server.builder is not None and server._cvt_exposer is None:
            server._cvt_exposer = CvtExposer(server.builder, server._ua_nodes, server._by_namespace)
            server._alarm_exposer = AlarmExposer(server.builder, server._ua_nodes, server._by_namespace)
            server._engine_exposer = EngineExposer(server.builder, server._ua_nodes, server._by_namespace)
            apply_analog_fallback(server, bool(server.analog_item_supported))
            if getattr(server, "watchdog", None) is not None:
                bind_watchdog(server.watchdog)
    if not getattr(server, "_opcua_space_loaded", False):
        _cold_sync(server)
        server._opcua_space_loaded = True
    logging.getLogger("asyncua").setLevel(logging.ERROR)
    server._opcua_ready = True
    _freeze_registries()
    bind(server)
    server.send("start_to_wait")
    return True


def _freeze_registries() -> None:
    """Load lint rules, then refuse further registration. Complexity: O(1)."""
    from .linting import rules as _rules

    del _rules
    for registry in (exposer_registry, lint_registry, publisher_registry):
        registry.freeze()


def _node_namespace(index: int, identifier: str) -> str:
    return f"ns={int(index)};s={identifier}"


def _cold_sync(server) -> None:
    """Prefetch access for computed NodeIds, then enqueue. Complexity: O(N + M + E)."""
    from .runtime import precompute_node_ids

    precompute_node_ids(server)
    namespaces: list[str] = []
    index = int(getattr(server, "_namespace_idx", 0) or 0)
    try:
        for tag in server.cvt.iter_tags():
            if not owns_tag(tag):
                continue
            namespaces.append(_node_namespace(index, canonical_for("t", tag)))
            name = getattr(tag, "name", None)
            if name:
                server.enqueue_expose("t", name)
    except Exception:
        _LOG.debug("OPC UA cold tag sync skipped", exc_info=True)
    try:
        alarms = server.alarm_manager.get_alarms() or {}
        for alarm in alarms.values():
            namespaces.append(_node_namespace(index, canonical_for("a", alarm)))
            name = getattr(alarm, "name", None)
            if name:
                server.enqueue_expose("a", name)
    except Exception:
        _LOG.debug("OPC UA cold alarm sync skipped", exc_info=True)
    try:
        for engine, _, _ in server.machine.machine_manager.get_machines():
            ename = engine.name.value if hasattr(engine.name, "value") else str(engine.name)
            if not ename or ename == "OPCUAServer":
                continue
            namespaces.append(_node_namespace(index, canonical_for("e", engine)))
            server.enqueue_expose("e", ename)
    except Exception:
        _LOG.debug("OPC UA cold engine sync skipped", exc_info=True)
    server.access.prefetch(namespaces)
