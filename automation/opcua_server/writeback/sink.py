"""Client writes are checked on the session and applied off the asyncio thread."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from asyncua import ua
from asyncua.crypto.permission_rules import User, UserRole

from ..async_core.primitives import Queue, Thread
from ..observability import emit_access_event, note_metric
from ..propagation import ClientFieldWriter, CvtRollback, FieldPropagationRouter, new_transaction

_QUEUE_MAX = 10_000


class ScadaWriteSink:
    """Enqueue client data changes. The drain thread writes the CVT. Complexity: O(1) per notification."""

    def __init__(self) -> None:
        self.queue = Queue(maxsize=_QUEUE_MAX)
        self._thread = None

    def datachange_notification(self, node, val, data) -> None:
        """Drop server-side publishes. Complexity: O(1)."""
        try:
            node_id = node.nodeid.to_string()
        except Exception:
            return
        try:
            self.queue.put_nowait(("change", node_id, val, data))
        except Exception:
            return

    def start(self, app) -> None:
        """One OS thread. Complexity: O(1)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(target=_drain, args=(app, self.queue), name="opcua-write-drain", daemon=True)
        self._thread.start()


def install_write_gate(server, app) -> None:
    """Replace the attribute write for non-admin sessions. Complexity: O(1)."""
    service = server.iserver.attribute_service
    original = service.write

    async def write(params, user=User(role=UserRole.Admin)):
        if getattr(user, "role", None) == UserRole.Admin:
            return await original(params, user)
        return await _client_write(app, original, params, user)

    service.write = write


async def _client_write(app, original, params, user):
    from ..access.enforcement import check_value_write

    indexes = []
    results = [None] * len(params.NodesToWrite)
    session = getattr(user, "name", None) or "anonymous"
    for index, item in enumerate(params.NodesToWrite):
        code = _status_for(app, item, session, check_value_write)
        if code is not None:
            results[index] = ua.StatusCode(code)
            continue
        indexes.append(index)
    if not indexes:
        return results
    subset = ua.WriteParameters()
    subset.NodesToWrite = [params.NodesToWrite[index] for index in indexes]
    for index in indexes:
        _mark(app, params.NodesToWrite[index].NodeId, session)
    written = await original(subset, user)
    for offset, index in enumerate(indexes):
        results[index] = written[offset]
        if not written[offset].is_good():
            node_id = params.NodesToWrite[index].NodeId.to_string()
            getattr(app, "_client_write_marks", {}).pop(node_id, None)
    return results


def _status_for(app, item, session, check_value_write):
    if item.AttributeId != ua.AttributeIds.Value:
        return ua.StatusCodes.BadNotWritable
    node_id = item.NodeId.to_string()
    access, user_access = _bits(app, node_id)
    value = None
    status = None
    try:
        value = item.Value.Value.Value
        status = item.Value.StatusCode
    except Exception:
        value = None
    explicit = bool(getattr(item.Value, "SourcePicoseconds", None))
    low, high, expected = _limits(app, node_id)
    code = check_value_write(
        access,
        user_access,
        status_code=status,
        explicit_timestamp=explicit,
        value=value,
        expected=expected,
        low=low,
        high=high,
        rate_ok=True,
    )
    if code is not None:
        _queue_event(app, "rejected", f"{node_id} {int(code)}")
        return code
    limiter = getattr(app, "rate_limiter", None)
    tag_key = _tag_key(app, node_id)
    if limiter is not None and not limiter.allow(tag_key, session):
        _queue_event(app, "rate", tag_key)
        return ua.StatusCodes.BadTooManyOperations
    return None


def _bits(app, node_id: str) -> tuple[int, int]:
    policy = getattr(app, "_access_policy", {}).get(node_id)
    if isinstance(policy, tuple):
        return int(policy[0]), int(policy[1])
    if policy is None:
        return 1, 1
    return int(policy), int(policy)


def _limits(app, node_id: str):
    return getattr(app, "_write_limits", {}).get(node_id, (None, None, None))


def _tag_key(app, node_id: str) -> str:
    return getattr(app, "_opc_names", {}).get(node_id, node_id)


def _mark(app, node, session: str) -> None:
    node_id = node.to_string()
    marks = getattr(app, "_client_write_marks", None)
    if marks is None:
        return
    transaction = new_transaction()
    marks[node_id] = (time.monotonic() + 2.0, transaction.transaction_id, session)
    if len(marks) > _QUEUE_MAX:
        marks.pop(next(iter(marks)))


def _queue_event(app, kind: str, detail: str) -> None:
    sink = getattr(app, "scada_sink", None)
    if sink is None:
        return
    try:
        sink.queue.put_nowait(("event", kind, detail))
    except Exception:
        return


def _drain(app, queue) -> None:
    while True:
        try:
            item = queue.get()
        except Exception:
            return
        if not item:
            continue
        if item[0] == "event":
            _event(app, item[1], item[2])
            continue
        _apply_change(app, item[1], item[2])


def _event(app, kind: str, detail: str) -> None:
    if kind == "rate":
        note_metric(app, "external_writes_rejected")
        note_metric(app, "rate_limit_hits")
    elif kind == "rejected":
        note_metric(app, "external_writes_rejected")
    emit_access_event(kind if kind in {"rate", "rejected"} else "rejected", "gate", detail)


def _apply_change(app, node_id: str, value) -> None:
    marks = getattr(app, "_client_write_marks", {})
    mark = marks.pop(node_id, None)
    if mark is None or mark[0] < time.monotonic():
        return
    transaction_id = mark[1]
    name = _tag_key(app, node_id)
    tag = None
    try:
        tag = app.cvt.get_tag_by_name(name=name)
    except Exception:
        tag = None
    if tag is None:
        emit_access_event("rejected", transaction_id, f"tag missing {name}")
        return
    note_metric(app, "external_writes")
    emit_access_event("received", transaction_id, name)
    previous = _previous(tag)
    converted = _convert(tag, value)
    depth = int(getattr(tag, "propagation_depth", 1) or 1)
    try:
        app.cvt.set_value_fast(
            id=tag.id,
            value=converted,
            timestamp=datetime.now(timezone.utc),
            source="external",
        )
    except Exception:
        note_metric(app, "external_writes_failed")
        emit_access_event("rejected", transaction_id, "cvt rejected")
        return
    tag.propagation_depth = depth
    _propagate(app, tag, converted, transaction_id, depth, previous)


def _previous(tag):
    try:
        return tag.get_value()
    except Exception:
        return None


def _convert(tag, value):
    try:
        return tag.value.convert_value(value=value, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
    except Exception:
        return value


def _propagate(app, tag, value, transaction_id: str, depth: int, previous) -> None:
    metrics = getattr(app, "metrics", None)
    if metrics is not None:
        metrics.propagation_depth_max = max(int(getattr(metrics, "propagation_depth_max", 0)), depth)
    transaction = new_transaction(depth=depth)
    transaction = type(transaction)(transaction_id, "external", depth, "scada")
    if depth > 3:
        note_metric(app, "multihop_loops")
        emit_access_event("loop", transaction_id, tag_name(tag))
        return
    router = FieldPropagationRouter(ClientFieldWriter(), CvtRollback(app.cvt))
    result = router.route(tag, value, transaction)
    if result.status == "skipped":
        return
    note_metric(app, "multihop_writes")
    window = getattr(app, "command_window", None)
    detector = getattr(app, "oscillation", None)
    if result.ok:
        emit_access_event("field_ok", transaction_id, tag_name(tag))
        if window is not None:
            window.open(tag_name(tag), value)
        return
    note_metric(app, "multihop_writes_failed")
    note_metric(app, "rollbacks")
    emit_access_event("field_failed", transaction_id, f"{result.status} {result.code}")
    try:
        CvtRollback(app.cvt).revert(tag, previous)
        emit_access_event("rollback", transaction_id, tag_name(tag))
    except Exception:
        return
    if detector is not None and detector.observe(tag_name(tag), value):
        note_metric(app, "oscillation_detected")
        emit_access_event("oscillation", transaction_id, tag_name(tag))
def tag_name(tag) -> str:
    name = getattr(tag, "name", "")
    return name.value if hasattr(name, "value") else str(name)
