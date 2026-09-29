"""Tick, expose queue and dirty-set drain. Not named while_running (lint AP-1)."""

from __future__ import annotations

import logging
import time

from datetime import datetime, timezone

from .audit import audit_failure
from .flags import constant_mode
from .scope import owns_tag

_LOG = logging.getLogger("pyautomation")
TICK_BUDGET = {
    "expose_ops": 200,
    "expose_ms": 50,
    "dirty_tags_max": 1000,
    "total_ms": 100,
}
EXPOSE_BUDGET = {
    "cold_start": {"ops": 1000, "ms": 200},
    "steady_state": {"ops": 200, "ms": 50},
    "backpressure": {"ops": 100, "ms": 30},
}
_RECENT_TICKS = 5
RECONCILE_EVERY_N_TICKS = 60
WATCHDOG_S = 300.0
WATCHDOG_SLICE = 200


def _numeric(value):
    if hasattr(value, "value"):
        value = value.value
    return value


def bind_exposed_tag(server, entity_type: str, name: str) -> None:
    """Follow CVT changes for a tag that the async runner just queued. Complexity: O(1)."""
    if entity_type != "t" or not name:
        return
    tag = _entity_for(server, "t", name)
    if tag is None:
        return
    attach_observer(server, tag)
    server._dirty_tags.add(name)


def attach_observer(server, tag) -> None:
    """Complexity: O(1). The tracker implementation is whatever object sits on the server."""
    name = getattr(tag, "name", None)
    if not name or name in server._tag_observers:
        return
    tracker = getattr(server, "tag_tracker", None)
    if tracker is None:
        return
    if name not in server._watch_order:
        server._watch_order.append(name)
    server._last_touch[name] = time.monotonic()
    dead = 0.0
    try:
        dead = float(tag.get_dead_band() or 0.0)
    except Exception:
        dead = 0.0
    server._dead_bands[name] = dead
    value = _numeric(tag.get_value() if hasattr(tag, "get_value") else None)
    tracker.attach(name, value)


def register_tag(server, tag) -> bool:
    """Materialize one tag. Complexity: O(P)."""
    if tag is None or not owns_tag(tag):
        return False
    publisher = getattr(server, "publisher", None)
    if publisher is None:
        return False
    created = publisher.materialize_tag(tag)
    attach_observer(server, tag)
    if created:
        server.metrics.nodes_tags += 1
        _emit_node(server, "on.opcua_server.node_added", tag.name, "t")
    return bool(created)


def register_alarm(server, alarm) -> bool:
    publisher = getattr(server, "publisher", None)
    if alarm is None or publisher is None:
        return False
    created = publisher.materialize_alarm(alarm)
    if created:
        server.metrics.nodes_alarms += 1
        _emit_node(server, "on.opcua_server.node_added", alarm.name, "a")
    return bool(created)


def register_engine(server, engine) -> bool:
    publisher = getattr(server, "publisher", None)
    if engine is None or publisher is None:
        return False
    created = publisher.materialize_engine(engine)
    if created:
        name = engine.name.value if hasattr(engine.name, "value") else str(engine.name)
        server.metrics.nodes_engines += 1
        _emit_node(server, "on.opcua_server.node_added", name, "e")
    return bool(created)


def _apply_cached_access(server, node) -> None:
    if node is None:
        return
    try:
        namespace = node.nodeid.to_string()
    except Exception:
        return
    level = server.access.resolve(namespace)
    runner = getattr(server, "runner", None)
    if runner is None:
        return
    from .async_core.commands import ApplyAccess

    runner.submit(ApplyAccess(namespace=namespace, access_level=int(level)))


def _emit_node(server, event: str, name: str, entity_type: str) -> None:
    try:
        from .. import PyAutomation

        sio = getattr(PyAutomation(), "sio", None)
        if sio is not None:
            sio.emit(event, {"name": name, "entity_type": entity_type})
    except Exception:
        return


def push_tag(server, name: str, server_ts=None) -> None:
    tag = server.cvt.get_tag_by_name(name=name)
    if tag is None:
        return
    publisher = getattr(server, "publisher", None)
    if publisher is not None:
        publisher.push_tag(name, server_ts)
    server._last_value[name] = _numeric(tag.get_value() if hasattr(tag, "get_value") else None)
    server._last_touch[name] = time.monotonic()


def push_alarm(server, name: str, server_ts=None) -> None:
    publisher = getattr(server, "publisher", None)
    if publisher is None:
        return
    publisher.push_alarm(name, server_ts)


def push_engine(server, name: str, server_ts=None) -> None:
    publisher = getattr(server, "publisher", None)
    if publisher is None:
        return
    publisher.push_engine(name, server_ts)


def _recent_p95(samples) -> float:
    """p95 of a window of at most five samples is the maximum. Complexity: O(1)."""
    if not samples:
        return 0.0
    return max(samples)


def current_expose_budget(server) -> dict:
    """Pick the expose budget for this tick. Complexity: O(1)."""
    if len(server._expose_queue) > 1000:
        return EXPOSE_BUDGET["cold_start"]
    recent = getattr(server, "_recent_ticks", None)
    if recent and _recent_p95(recent) > 100:
        return EXPOSE_BUDGET["backpressure"]
    return EXPOSE_BUDGET["steady_state"]


def precompute_node_ids(server) -> None:
    """Fill the NodeId cache once. Complexity: O(N + M + E)."""
    from .exposures.common import entity_area, remember_node_id
    from .identity import make_node_id

    cache = server._node_id_cache
    try:
        for tag in server.cvt.iter_tags():
            if not owns_tag(tag):
                continue
            _store_node_id(cache, "t", tag, entity_area(tag), remember_node_id, make_node_id)
    except Exception:
        _LOG.debug("OPC UA tag id precompute skipped", exc_info=True)
    try:
        alarms = server.alarm_manager.get_alarms() or {}
        for alarm in alarms.values():
            _store_node_id(cache, "a", alarm, entity_area(alarm), remember_node_id, make_node_id)
    except Exception:
        _LOG.debug("OPC UA alarm id precompute skipped", exc_info=True)
    try:
        for engine, _, _ in server.machine.machine_manager.get_machines():
            ename = engine.name.value if hasattr(engine.name, "value") else str(engine.name)
            if not ename or ename == "OPCUAServer":
                continue
            _store_node_id(cache, "e", engine, entity_area(engine), remember_node_id, make_node_id)
    except Exception:
        _LOG.debug("OPC UA engine id precompute skipped", exc_info=True)


def _store_node_id(cache, kind: str, entity, area, remember_node_id, make_node_id) -> None:
    from .exposures.common import _plain

    name = getattr(entity, "name", None)
    if hasattr(name, "value"):
        name = name.value
    area_text = _plain(area) or None
    name = _plain(name)
    if not name or name == "OPCUAServer":
        return
    key = (kind, name)
    if key in cache:
        return
    identifier = make_node_id(kind, area_text, name)
    cache[key] = identifier
    remember_node_id(kind, area_text, name, identifier)


def cache_enqueued_node_id(server, entity_type: str, name: str) -> None:
    """Compute a NodeId when a new entity is enqueued. Complexity: O(1)."""
    from .exposures.common import _plain, entity_area, remember_node_id
    from .identity import make_node_id

    name = _plain(name)
    key = (entity_type, name)
    if key in server._node_id_cache:
        return
    entity = _entity_for(server, entity_type, name)
    if entity is None:
        return
    _store_node_id(server._node_id_cache, entity_type, entity, entity_area(entity), remember_node_id, make_node_id)


def _entity_for(server, entity_type: str, name: str):
    if entity_type == "t":
        return server.cvt.get_tag_by_name(name=name) if name else None
    if entity_type == "a":
        manager = server.alarm_manager
        if hasattr(manager, "get_alarm_by_name"):
            return manager.get_alarm_by_name(name=name)
        alarms = manager.get_alarms() if hasattr(manager, "get_alarms") else {}
        return alarms.get(name) if isinstance(alarms, dict) else None
    if entity_type == "e":
        return server.machine.get_machine(name)
    return None


def process_expose_queue(server) -> int:
    """Drain the expose queue under the adaptive budget. Complexity: O(B).

    The asyncio runner owns this queue. A sync drain would materialize the
    same leaf again and then call set_data_value on the listing record.
    """
    if getattr(server, "runner", None) is not None:
        return 0
    budget = current_expose_budget(server)
    server._active_expose_budget = budget
    deadline = time.monotonic() + budget["ms"] / 1000.0
    processed = 0
    started = time.monotonic()
    while server._expose_queue and processed < budget["ops"] and time.monotonic() < deadline:
        entity_type, name = server._expose_queue.popleft()
        server._expose_seen.discard((entity_type, name))
        try:
            _process_one_expose(server, entity_type, name)
        except Exception as exc:
            server.metrics.expose_failures += 1
            audit_failure("OPC UA expose failed", f"{entity_type}:{name}: {exc}")
        processed += 1
    server.metrics.last_expose_ms = (time.monotonic() - started) * 1000.0
    server.metrics.note_queue(len(server._expose_queue))
    return processed


def _process_one_expose(server, entity_type: str, name: str) -> None:
    if entity_type == "t":
        tag = server.cvt.get_tag_by_name(name=name)
        register_tag(server, tag)
    elif entity_type == "a":
        alarm = None
        if hasattr(server.alarm_manager, "get_alarm_by_name"):
            alarm = server.alarm_manager.get_alarm_by_name(name=name)
        register_alarm(server, alarm)
    elif entity_type == "e":
        engine = server.machine.get_machine(name)
        register_engine(server, engine)


def _names_for(server, kind: str, bucket: set, limit: int | None = None):
    """O(K). Prefer the tracker so a substitute implementation needs no runtime edit."""
    cap_limit = TICK_BUDGET["dirty_tags_max"] if limit is None else limit
    tracker_name = {"t": "tag_tracker", "a": "alarm_tracker", "e": "engine_tracker"}[kind]
    tracker = getattr(server, tracker_name, None)
    if tracker is not None:
        return tracker.drain(cap_limit)
    if not bucket:
        return ()
    scratch = getattr(server, "_drain_scratch", None)
    if not isinstance(scratch, list):
        scratch = [None] * TICK_BUDGET["dirty_tags_max"]
        server._drain_scratch = scratch
    index = 0
    cap = min(cap_limit, len(scratch))
    while bucket and index < cap:
        scratch[index] = bucket.pop()
        index += 1
    taken = scratch[:index]
    for slot in range(index):
        scratch[slot] = None
    return taken


def _push_name(server, kind: str, name: str, server_ts) -> None:
    if kind == "t":
        push_tag(server, name, server_ts)
    elif kind == "a":
        push_alarm(server, name, server_ts)
    else:
        push_engine(server, name, server_ts)


def watchdog_slice(server) -> None:
    order = server._watch_order
    if not order:
        return
    now = time.monotonic()
    count = min(WATCHDOG_SLICE, len(order))
    start = server._watch_index
    for step in range(count):
        name = order[(start + step) % len(order)]
        seen = server._last_touch.get(name)
        if seen is None or (now - seen) >= WATCHDOG_S:
            _LOG.debug("OPC UA watchdog refreshing stale tag %s", name)
            server._dirty_tags.add(name)
            server._last_touch[name] = now
    server._watch_index = (start + count) % len(order)


def reconcile_full(server) -> None:
    started = time.monotonic()
    try:
        for tag in server.cvt.iter_tags():
            if owns_tag(tag):
                server._dirty_tags.add(tag.name)
    except Exception:
        _LOG.debug("OPC UA tag reconcile skipped", exc_info=True)
    try:
        alarms = server.alarm_manager.get_alarms() or {}
        for name in alarms:
            server._dirty_alarms.add(name)
    except Exception:
        _LOG.debug("OPC UA alarm reconcile skipped", exc_info=True)
    supervisor = getattr(server, "watchdog", None)
    if supervisor is None:
        try:
            for engine, _, _ in server.machine.machine_manager.get_machines():
                ename = engine.name.value if hasattr(engine.name, "value") else str(engine.name)
                if ename != "OPCUAServer":
                    server._dirty_engines.add(ename)
        except Exception:
            _LOG.debug("OPC UA engine reconcile skipped", exc_info=True)
        watchdog_slice(server)
    else:
        supervisor.on_reconcile()
    server.metrics.reconcile_passes += 1
    server.metrics.last_reconcile_ms = (time.monotonic() - started) * 1000.0


def watch_identity_env(server) -> None:
    """Audit a change of manufacturer or segment. Complexity: O(1)."""
    import os

    manufacturer = os.environ.get("AUTOMATION_MANUFACTURER")
    segment = os.environ.get("AUTOMATION_SEGMENT")
    if not getattr(server, "_identity_env_latched", False):
        server._latched_manufacturer = manufacturer
        server._latched_segment = segment
        server._identity_env_latched = True
        return
    if manufacturer != server._latched_manufacturer:
        server._latched_manufacturer = manufacturer
        audit_failure("OPC UA manufacturer changed", str(manufacturer), criticity=4)
    if segment != server._latched_segment:
        server._latched_segment = segment
        audit_failure("OPC UA segment changed", str(segment), criticity=5)


def release_watched_name(server, name: str) -> None:
    """Drop one tag from the embedded watchdog and its OPC UA node. Complexity: O(W)."""
    if server is None or not name:
        return
    order = getattr(server, "_watch_order", None)
    if isinstance(order, list):
        server._watch_order = [item for item in order if item != name]
    for bucket_name in ("_last_touch", "_dead_bands"):
        bucket = getattr(server, bucket_name, None)
        if isinstance(bucket, dict):
            bucket.pop(name, None)
    dirty = getattr(server, "_dirty_tags", None)
    if isinstance(dirty, set):
        dirty.discard(name)
    tracker = getattr(server, "tag_tracker", None)
    detach = getattr(tracker, "detach", None)
    if callable(detach):
        try:
            detach(name)
        except Exception:
            pass
    observers = getattr(server, "_tag_observers", None)
    if isinstance(observers, dict):
        observers.pop(name, None)
    submit_drop(server, name)


def publish_tag_definition(server, name: str, *, previous_name: str | None = None, recreate: bool = False) -> None:
    """Push a CVT definition change to the embedded server. Complexity: O(1).

    Value changes already travel through the dirty observer. This covers the
    attributes the node actually publishes: unit, variable, range, scan, deadband,
    filter and browse name. A data-type or filter-set change recreates the node.
    """
    if server is None or not name:
        return
    if previous_name and previous_name != name:
        submit_drop(server, previous_name)
    if recreate:
        submit_drop(server, name, reexpose=True)
    else:
        enqueue = getattr(server, "enqueue_expose", None)
        if callable(enqueue):
            enqueue("t", name)
    dirty = getattr(server, "_dirty_tags", None)
    if isinstance(dirty, set):
        dirty.add(name)
    tag = None
    getter = getattr(getattr(server, "cvt", None), "get_tag_by_name", None)
    if callable(getter):
        try:
            tag = getter(name=name)
        except Exception:
            tag = None
    bands = getattr(server, "_dead_bands", None)
    if isinstance(bands, dict) and tag is not None:
        try:
            bands[name] = float(tag.get_dead_band() or 0.0)
        except Exception:
            bands[name] = 0.0
    touched = getattr(server, "_last_touch", None)
    if isinstance(touched, dict):
        touched[name] = time.monotonic()


def submit_drop(server, name: str, *, reexpose: bool = False) -> None:
    """Queue deletion of one tag node. A float re-expose follows when the variant type changed."""
    from .async_core.commands import DropTag

    if not name:
        return
    server._expose_seen.discard(("t", name))
    runner = getattr(server, "runner", None)
    if runner is not None:
        runner.submit(DropTag(name=name, reexpose=reexpose))
        return
    if reexpose:
        server.enqueue_expose("t", name)


def dispatch_runner(server, server_ts) -> None:
    """Queue expose and write snapshots. Complexity: O(B + K). No address-space calls."""
    from .async_core.commands import WriteValues
    from .async_core.snapshots import expose_snapshot, write_item

    runner = server.runner
    budget = current_expose_budget(server)
    server._active_expose_budget = budget
    ops = min(int(budget["ops"]), 200)
    deadline = time.monotonic() + budget["ms"] / 1000.0
    processed = 0
    started = time.monotonic()
    while server._expose_queue and processed < ops and time.monotonic() < deadline:
        entity_type, name = server._expose_queue.popleft()
        server._expose_seen.discard((entity_type, name))
        try:
            command = expose_snapshot(server, entity_type, name)
            if command is not None:
                runner.submit(command)
                bind_exposed_tag(server, entity_type, name)
        except Exception as exc:
            server.metrics.expose_failures += 1
            audit_failure("OPC UA expose failed", f"{entity_type}:{name}: {exc}")
        processed += 1
    server.metrics.last_expose_ms = (time.monotonic() - started) * 1000.0
    server.metrics.note_queue(len(server._expose_queue))
    items = []
    for kind, bucket in (
        ("t", server._dirty_tags),
        ("a", server._dirty_alarms),
        ("e", server._dirty_engines),
    ):
        for name in _names_for(server, kind, bucket, limit=200):
            item = write_item(server, kind, name, server_ts)
            if item is not None:
                items.append(item)
    if items:
        runner.submit(WriteValues(tuple(items)))


def process_one_tick(server) -> None:
    """Complexity: O(B + K). One timestamp for the whole tick. The dirty set is drained unsorted."""
    started = time.monotonic()
    if getattr(server, "_opcua_ready", False):
        server_ts = datetime.now(timezone.utc)
        server._tick_timestamp = server_ts
        watch_identity_env(server)
        if getattr(server, "runner", None) is not None:
            dispatch_runner(server, server_ts)
        else:
            process_expose_queue(server)
            for kind, bucket in (
                ("t", server._dirty_tags),
                ("a", server._dirty_alarms),
                ("e", server._dirty_engines),
            ):
                for name in _names_for(server, kind, bucket):
                    _push_name(server, kind, name, server_ts)
        server.metrics.note_dirty(len(server._dirty_tags))
        if constant_mode():
            supervisor = getattr(server, "watchdog", None)
            if supervisor is not None:
                supervisor.on_tick()
            else:
                watchdog_slice(server)
        else:
            server._tick_counter += 1
            if server._tick_counter % RECONCILE_EVERY_N_TICKS == 0:
                reconcile_full(server)
    elapsed_ms = (time.monotonic() - started) * 1000.0
    recent = getattr(server, "_recent_ticks", None)
    if recent is None:
        from collections import deque

        recent = deque(maxlen=_RECENT_TICKS)
        server._recent_ticks = recent
    recent.append(elapsed_ms)
    server.metrics.observe_tick(elapsed_ms)
    active = getattr(server, "_active_expose_budget", None) or EXPOSE_BUDGET["steady_state"]
    limit = 200.0 if active is EXPOSE_BUDGET["cold_start"] else TICK_BUDGET["total_ms"]
    if elapsed_ms > limit:
        server.metrics.tick_budget_exceeded += 1
        audit_failure(  # noqa: AP-8
            "OPC UA tick budget exceeded",
            f"elapsed_ms={elapsed_ms:.1f} limit={limit}",
        )
