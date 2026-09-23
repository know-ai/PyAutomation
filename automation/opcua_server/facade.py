"""Embedded OPC UA server facade.

Contracts: IPublisher, IDirtyTracker, WatchdogSupervisor.
Invariants: one canonical plane; tick O(B + K); reset O(1).
The facade orchestrates. Node creation, dirty tracking and the watchdog live elsewhere.
"""

from __future__ import annotations

from collections import deque

from ..managers.alarms import AlarmManager
from ..state_machine import StateMachineCore
from ..tags.cvt import CVTEngine
from .access import AccessControlService
from .audit import audit_failure
from .bootstrap import start_endpoint
from .dirty.per_tag import PerTagDirtyTracker
from .flags import server_host
from .lifecycle import (
    apply_node_access,
    build_snapshot,
    list_nodes,
    mark_alarm,
    mark_engine,
    mark_tag,
    mark_tag_name,
    reset_structures,
)
from .metrics import OpcUaServerMetrics
from .publishing.canonical_publisher import CanonicalPublisher
from .runtime import TICK_BUDGET, process_expose_queue, process_one_tick, reconcile_full, register_tag
from .watchdog import bind_watchdog
from .watchdog.supervisor import WatchdogSupervisor
from .writeback import WriteBackHandler

_EXPOSE_MAX = 10_000


class OPCUAServer(StateMachineCore):
    """Canonical OPC UA server. Complexity: tick O(B + K), reset O(1)."""

    def __init__(self, name: str = "OPCUAServer", description: str = "", classification: str = "OPC UA Server"):
        """Build empty structures. Complexity: O(1). Allocations: the fixed maps. No network."""
        from .. import AUTOMATION_OPCUA_SERVER_PORT
        from ..state_machine import Machine

        self.cvt = CVTEngine()
        self.alarm_manager = AlarmManager()
        self.machine = Machine()
        self.port = AUTOMATION_OPCUA_SERVER_PORT
        self.host = server_host()
        if not isinstance(name, str):
            name = getattr(name, "value", str(name))
        super().__init__(name=name, description=description, classification=classification)
        self.server = None
        self.objects = None
        self.builder = None
        self._cvt_exposer = None
        self._alarm_exposer = None
        self._engine_exposer = None
        self._namespace_idx = 0
        self._opcua_ready = False
        self._opcua_endpoint_up = False
        self._opcua_space_loaded = False
        self._tick_counter = 0
        self._watch_index = 0
        self._ua_nodes: dict = {}
        self._by_namespace: dict = {}
        self._expose_queue: deque = deque(maxlen=_EXPOSE_MAX)
        self._expose_seen: set = set()
        self._dirty_tags: set = set()
        self._dirty_alarms: set = set()
        self._dirty_engines: set = set()
        self._node_id_cache: dict = {}
        self._access_cache: dict = {}
        self._last_value: dict = {}
        self._dead_bands: dict = {}
        self._last_touch: dict = {}
        self._tag_observers: dict = {}
        self._watch_order: list = []
        self._name_to_canonical: dict = {}
        self._drain_scratch: list = [None] * TICK_BUDGET["dirty_tags_max"]
        self.metrics = OpcUaServerMetrics()
        self.access = AccessControlService(self._access_cache)
        self.writeback = WriteBackHandler()
        from .loop_prevention import bind_access_runtime
        bind_access_runtime(self)
        self.analog_item_supported = None
        self._analog_fallback_audited = False
        self.tag_tracker = PerTagDirtyTracker(self._dead_bands, self._dirty_tags, self)
        self.alarm_tracker = PerTagDirtyTracker({}, self._dirty_alarms, None)
        self.engine_tracker = PerTagDirtyTracker({}, self._dirty_engines, None)
        self.watchdog = WatchdogSupervisor(self)
        self.publisher = CanonicalPublisher(self)
        bind_watchdog(self.watchdog)

    def while_starting(self):
        """Open the endpoint and enqueue the catalog. Complexity: O(N + M + E) enqueues."""
        start_endpoint(self)

    def while_waiting(self):
        """Move to run. Complexity: O(1)."""
        self.send("wait_to_run")

    def while_running(self):
        """One tick. Complexity: O(B + K)."""
        process_one_tick(self)

    def while_resetting(self):
        """Clear and return to start. Complexity: O(1)."""
        reset_structures(self)
        self.send("reset_to_start")

    def enqueue_expose(self, entity_type: str, name: str) -> None:
        """Push one expose. Complexity: O(1)."""
        if entity_type not in {"t", "a", "e"} or not name:
            return
        key = (entity_type, name)
        if key in self._expose_seen:
            return
        if len(self._expose_queue) >= _EXPOSE_MAX:
            dropped = self._expose_queue.popleft()
            self._expose_seen.discard(dropped)
            self.metrics.expose_failures += 1
            audit_failure("OPC UA publish queue overflow", f"dropped {dropped}", criticity=4)
        self._expose_seen.add(key)
        self._expose_queue.append(key)
        from .runtime import cache_enqueued_node_id

        cache_enqueued_node_id(self, entity_type, name)
        self.metrics.note_queue(len(self._expose_queue))

    def mark_tag(self, tag) -> None:
        """Complexity: O(1)."""
        mark_tag(self, tag)

    def mark_tag_name(self, name: str) -> None:
        """Complexity: O(1)."""
        mark_tag_name(self, name)

    def mark_alarm(self, name: str) -> None:
        """Complexity: O(1)."""
        mark_alarm(self, name)

    def mark_engine(self, name: str) -> None:
        """Complexity: O(1)."""
        mark_engine(self, name)

    def _process_one_tick(self) -> None:
        process_one_tick(self)

    def _process_expose_queue(self, budget_ms: int = TICK_BUDGET["expose_ms"]) -> int:
        return process_expose_queue(self)

    def force_full_sync(self) -> None:
        """Mark the catalog dirty. Complexity: O(N + M + E). Not a tick."""
        reconcile_full(self)

    def sync_cvt_tags(self) -> int:
        """Cold-path alias used by core reconcile. Complexity: O(N + M + E)."""
        self.force_full_sync()
        return len(self._dirty_tags)

    def _flush_pending_cvt_expose(self) -> int:
        return self._process_expose_queue()

    def expose_cvt_tag(self, tag) -> bool:
        """Enqueue, or materialize when the endpoint is already up. Complexity: O(1) or O(P)."""
        name = getattr(tag, "name", None)
        if not name:
            return False
        if not self._opcua_ready or getattr(self, "runner", None) is not None:
            self.enqueue_expose("t", name)
            return False
        return register_tag(self, tag)

    def snapshot(self) -> dict:
        """Complexity: O(1)."""
        return build_snapshot(self)

    def list_attrs(self) -> list:
        """Complexity: O(V)."""
        return list_nodes(self)

    def find_node_by_namespace(self, namespace: str):
        """Complexity: O(1)."""
        return self._by_namespace.get(namespace)

    def apply_access(self, node, access_level) -> None:
        """Complexity: O(1) to enqueue."""
        apply_node_access(self, node, access_level)

    def shutdown(self) -> None:
        """Idempotent stop. Complexity: O(1)."""
        reset_structures(self)

    def _reset_structures(self) -> None:
        reset_structures(self)
