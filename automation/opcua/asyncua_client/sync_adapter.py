"""Gevent-side wait over the field-client loop. No network calls here."""

from __future__ import annotations

import time
import uuid
from typing import Any

from automation.opcua_server.async_core.primitives import Event, Lock

from .commands import (
    Browse,
    CommandResult,
    Connect,
    DasResult,
    Disconnect,
    Discover,
    ReadBatch,
    ReadBatchResult,
    Subscribe,
    Unsubscribe,
    Write,
)
from .runner import ClientRunner

_runner: ClientRunner | None = None
_guard = Lock()
_pending: dict[str, dict] = {}
_pending_lock = Lock()
_drain_started = False

def get_runner() -> ClientRunner:
    global _runner, _drain_started
    with _guard:
        if _runner is None:
            _runner = ClientRunner()
            _runner.start()
        runner = _runner
    if not _drain_started:
        _start_drain(runner)
    return runner
def reset_runner_for_tests() -> None:
    """Stop the process runner. Tests that start their own runner call this first."""
    global _runner, _drain_started
    with _guard:
        runner = _runner
        _runner = None
        _drain_started = False
    if runner is not None:
        runner.stop()
    with _pending_lock:
        _pending.clear()
def is_connected(client_name: str) -> bool:
    runner = _runner
    if runner is None:
        return False
    return runner.is_connected(client_name)
class SubscriptionLease:
    """One subscription token per client. Network work is a command, not a call."""
    def __init__(self, client_name: str, period_ms: int) -> None:
        self.client_name = client_name
        self.period_ms = period_ms
        self.deleted = False
    def subscribe_data_change(self, node):
        namespace = node.nodeid.to_string() if hasattr(node, "nodeid") else str(node)
        get_runner().submit(Subscribe(self.client_name, (namespace,), self.period_ms))
        return namespace
    def unsubscribe(self, item) -> None:
        get_runner().submit(Unsubscribe(self.client_name, (str(item),)))
    def delete(self) -> None:
        self.deleted = True
        get_runner().submit(Unsubscribe(self.client_name, ()))
def open_session(url: str, client_name: str, timeout: float, username: str | None = None, password: str | None = None) -> None:
    correlation_id = uuid.uuid4().hex
    event = _register(correlation_id)
    get_runner().submit(
        Connect(
            url=url,
            client_name=client_name,
            correlation_id=correlation_id,
            timeout=float(timeout or 60),
            username=username,
            password=password,
        )
    )
    if not _wait(event, max(1.0, float(timeout or 60))):
        raise TimeoutError(f"connect timeout client={client_name}")
    slot = _take(correlation_id)
    if slot is None or not slot.get("ok", False):
        raise OSError((slot or {}).get("error") or f"connect failed client={client_name}")
def close_session(client_name: str, timeout: float = 10) -> None:
    correlation_id = uuid.uuid4().hex
    event = _register(correlation_id)
    get_runner().submit(Disconnect(client_name, correlation_id))
    if not _wait(event, timeout):
        raise TimeoutError(f"disconnect timeout client={client_name}")
    slot = _take(correlation_id)
    if slot is None or not slot.get("ok", False):
        raise OSError((slot or {}).get("error") or f"disconnect failed client={client_name}")
def read_batch(client_name: str, node_ids: list[str], timeout: float, inflight: dict | None):
    """Return a value map, or None when the previous Read is still in flight."""
    if inflight and inflight.get("id"):
        if not inflight["event"].is_set():
            return None
        slot = _take(inflight["id"])
        inflight.clear()
        return _finish(slot, node_ids)
    correlation_id = uuid.uuid4().hex
    event = _register(correlation_id, list(node_ids))
    get_runner().submit(ReadBatch(client_name, tuple(node_ids), correlation_id))
    if not _wait(event, timeout):
        if inflight is not None:
            inflight.clear()
            inflight.update({"id": correlation_id, "event": event, "names": list(node_ids)})
        return None
    return _finish(_take(correlation_id), node_ids)
def browse(client_name: str, node_id: str, mode: str, depth: int, max_nodes: int, include_properties: bool, include_property_values: bool, timeout: float = 30):
    correlation_id = uuid.uuid4().hex
    event = _register(correlation_id)
    get_runner().submit(
        Browse(
            client_name=client_name,
            node_id=node_id,
            depth=depth,
            correlation_id=correlation_id,
            mode=mode,
            max_nodes=max_nodes,
            include_properties=include_properties,
            include_property_values=include_property_values,
        )
    )
    if not _wait(event, timeout):
        raise TimeoutError(f"browse timeout client={client_name}")
    slot = _take(correlation_id)
    if slot is None or not slot.get("ok", False):
        raise OSError((slot or {}).get("error") or "browse failed")
    return slot.get("payload")
def write_value(client_name: str, node_id: str, value: Any, timeout: float = 5):
    correlation_id = uuid.uuid4().hex
    event = _register(correlation_id)
    get_runner().submit(Write(client_name, node_id, value, correlation_id))
    if not _wait(event, timeout):
        raise TimeoutError(f"write timeout client={client_name}")
    slot = _take(correlation_id)
    if slot is None or not slot.get("ok", False):
        raise OSError((slot or {}).get("error") or "write failed")
    return slot.get("payload")
def discover(url: str, kind: str, timeout: float = 10):
    correlation_id = uuid.uuid4().hex
    event = _register(correlation_id)
    get_runner().submit(Discover(url, correlation_id, kind))
    if not _wait(event, timeout):
        raise TimeoutError(f"discover timeout url={url}")
    slot = _take(correlation_id)
    if slot is None or not slot.get("ok", False):
        raise OSError((slot or {}).get("error") or "discover failed")
    return slot.get("payload")
def _register(correlation_id: str, names=None):
    event = Event()
    with _pending_lock:
        _pending[correlation_id] = {"event": event, "names": list(names or []), "ok": False, "payload": None, "error": None}
    return event
def _take(correlation_id: str):
    with _pending_lock:
        return _pending.pop(correlation_id, None)
def _finish(slot, node_ids):
    if slot is None or slot.get("payload") is None:
        return {ns: None for ns in node_ids}
    source_names = slot.get("names") or list(node_ids)
    packed = {}
    for index, namespace in enumerate(source_names):
        packed[namespace] = slot["payload"][index] if index < len(slot["payload"]) else None
    if list(source_names) == list(node_ids):
        return packed
    return {ns: packed.get(ns) for ns in node_ids}
def _apply(item) -> None:
    if isinstance(item, ReadBatchResult):
        with _pending_lock:
            slot = _pending.get(item.correlation_id)
            if slot is None:
                return
            slot["payload"] = item.data_values
            slot["ok"] = item.data_values is not None
            if item.data_values is None:
                slot["error"] = "read-failed"
            slot["event"].set()
        return
    if isinstance(item, CommandResult):
        with _pending_lock:
            slot = _pending.get(item.correlation_id)
            if slot is None:
                return
            slot["ok"] = item.ok
            slot["payload"] = item.payload
            slot["error"] = item.error
            slot["event"].set()
        return
    if isinstance(item, DasResult):
        _apply_das(item)
def _apply_das(item: DasResult) -> None:
    def write() -> None:
        from ..subscription import DAS
        from ...signal_conditioning.quality import map_opc_status
        node = _NamespaceNode(item.namespace)
        DAS().update_tag_value(
            node,
            item.value,
            item.source_timestamp,
            quality=map_opc_status(item.status_code),
        )
    try:
        import gevent
        from gevent import monkey
        if monkey.is_module_patched("threading"):
            gevent.get_hub().loop.run_callback(write)
            return
    except Exception:
        pass
    write()
class _NamespaceNode:
    def __init__(self, namespace: str) -> None:
        self.nodeid = self
        self._namespace = namespace
    def to_string(self) -> str:
        return self._namespace
def drain_once(runner: ClientRunner | None = None) -> int:
    current = runner or _runner
    if current is None:
        return 0
    items = current.results.drain()
    for item in items:
        _apply(item)
    return len(items)
def _start_drain(runner: ClientRunner) -> None:
    global _drain_started
    with _guard:
        if _drain_started:
            return
        _drain_started = True
    def loop() -> None:
        while getattr(runner, "_thread", None) is not None and runner._thread.is_alive():
            try:
                drain_once(runner)
            except Exception:
                pass
            _sleep_drain()
    from automation.opcua_server.async_core.primitives import Thread
    Thread(target=loop, name="opcua-client-drain", daemon=True).start()
def _sleep_drain() -> bool:
    time.sleep(0.02)
    return True
def _wait(event, timeout: float) -> bool:
    try:
        import gevent
        from gevent import monkey
        if monkey.is_module_patched("threading"):
            deadline = time.monotonic() + float(timeout)
            while time.monotonic() < deadline:
                if event.is_set():
                    return True
                gevent.sleep(0.005)
            return event.is_set()
    except Exception:
        pass
    return bool(event.wait(float(timeout)))
