"""Async handlers for the field OPC UA client. They only enqueue samples."""

from __future__ import annotations

import asyncio
import logging

from asyncua import Client as AsyncClient
from asyncua import ua
from asyncua.client.ua_client import UaClientState
from asyncua.ua.uatypes import datatype_to_varianttype

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

log = logging.getLogger("pyautomation")


def _canonical_node_id(node_id) -> str:
    """Stable NodeId text. asyncua omits ``ns=0``. Complexity: O(1)."""
    if hasattr(node_id, "to_string"):
        text = node_id.to_string()
    else:
        text = str(node_id or "")
    text = text.strip()
    if not text or text.startswith("ns="):
        return text
    return f"ns=0;{text}"

_ATTRS = (
    ua.AttributeIds.NodeClass,
    ua.AttributeIds.BrowseName,
    ua.AttributeIds.DisplayName,
    ua.AttributeIds.DataType,
    ua.AttributeIds.AccessLevel,
    ua.AttributeIds.UserAccessLevel,
    ua.AttributeIds.Description,
    ua.AttributeIds.Value,
    ua.AttributeIds.ArrayDimensions,
    ua.AttributeIds.ValueRank,
)

class LoopContext:
    def __init__(self, results, set_connected) -> None:
        self.results = results
        self.set_connected = set_connected
        self.sessions: dict[str, AsyncClient] = {}
        self.subs: dict[str, object] = {}
        self.handles: dict[str, dict[str, int]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
    def lock_for(self, name: str) -> asyncio.Lock:
        lock = self.locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[name] = lock
        return lock
    async def close(self) -> None:
        for name, client in list(self.sessions.items()):
            try:
                await client.disconnect()
            except Exception:
                log.debug("field client disconnect skipped name=%s", name, exc_info=True)
            self.set_connected(name, False)
        self.sessions.clear()
        self.subs.clear()
class DasHandler:
    """Publish callback. Enqueues the DataValue and returns."""
    def __init__(self, results) -> None:
        self.results = results
    def datachange_notification(self, node, val, data) -> None:
        namespace = _canonical_node_id(node.nodeid)
        status = None
        timestamp = None
        try:
            status = data.monitored_item.Value.StatusCode
            timestamp = data.monitored_item.Value.SourceTimestamp
        except Exception:
            status = None
        self.results.put(
            DasResult(
                namespace=namespace,
                value=val,
                status_code=status,
                source_timestamp=timestamp,
            )
        )
def _variant_value(data_value):
    try:
        return data_value.Value.Value
    except Exception:
        return None
def _text(value, fallback=""):
    text = getattr(value, "Text", None)
    if text:
        return text
    name = getattr(value, "Name", None)
    return name or fallback
async def _read_many(client: AsyncClient, node_id: str):
    nodeid = ua.NodeId.from_string(node_id)
    params = ua.ReadParameters()
    params.TimestampsToReturn = ua.TimestampsToReturn.Source
    items = []
    for attr in _ATTRS:
        item = ua.ReadValueId()
        item.NodeId = nodeid
        item.AttributeId = attr
        items.append(item)
    params.NodesToRead = items
    return await client.uaclient.read(params)
def _node_class_name(value) -> str:
    """OPC UA NodeClass is an int on the wire and an enum in the stack. Complexity: O(1)."""
    label = getattr(value, "name", None)
    if isinstance(label, str) and label:
        return label
    try:
        return ua.NodeClass(int(value)).name
    except Exception:
        return str(value or "")


def _status_text(status) -> str | None:
    if status is None:
        return None
    label = getattr(status, "name", None)
    if isinstance(label, str) and label:
        return label
    return str(status)


def _stamp_text(value):
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _attr_dict(node_id: str, values) -> dict:
    by_name = {attr.name: _variant_value(values[index]) for index, attr in enumerate(_ATTRS)}
    class_name = _node_class_name(by_name.get("NodeClass"))
    nodeid = ua.NodeId.from_string(node_id)
    data_type = by_name.get("DataType")
    type_name = None
    if data_type is not None:
        try:
            type_name = datatype_to_varianttype(data_type).name
        except Exception:
            type_name = str(data_type)
    description = _text(by_name.get("Description"), "")
    base = {
        "NamespaceIndex": nodeid.NamespaceIndex,
        "NamespaceUri": getattr(nodeid, "NamespaceUri", None),
        "Identifier": nodeid.Identifier,
        "Namespace": node_id,
        "NodeClass": class_name,
        "BrowseName": _text(by_name.get("BrowseName"), ""),
        "DisplayName": _text(by_name.get("DisplayName"), ""),
        "Description": description or None,
    }
    if class_name.lower() not in ("variable", "variabletype"):
        return base
    value_dv = values[_ATTRS.index(ua.AttributeIds.Value)]
    base.update(
        {
            "DataValue": value_dv,
            "DataType": type_name,
            "AccesLevel": by_name.get("AccessLevel"),
            "UserAccessLevel": by_name.get("UserAccessLevel"),
            "Value": _variant_value(value_dv),
            "SourceTimestamp": _stamp_text(getattr(value_dv, "SourceTimestamp", None)),
            "StatusCode": _status_text(getattr(value_dv, "StatusCode", None)),
            "ArrayDimensions": by_name.get("ArrayDimensions"),
            "ValueRank": getattr(by_name.get("ValueRank"), "name", by_name.get("ValueRank")),
        }
    )
    return base
def _is_property(ref) -> bool:
    try:
        return ref.ReferenceTypeId.Identifier == ua.ObjectIds.HasProperty
    except Exception:
        return False
async def _references(client: AsyncClient, node_ids: list[str]):
    """Forward hierarchical references. Any vendor folder layout. Complexity: O(R)."""
    if not node_ids:
        return {}
    nodes = [client.get_node(node_id) for node_id in node_ids]
    descriptions = []
    for node in nodes:
        desc = ua.BrowseDescription()
        desc.NodeId = node.nodeid
        desc.BrowseDirection = ua.BrowseDirection.Forward
        desc.ReferenceTypeId = ua.NodeId(ua.ObjectIds.HierarchicalReferences, 0)
        desc.IncludeSubtypes = True
        desc.NodeClassMask = 0
        desc.ResultMask = ua.BrowseResultMask.All
        descriptions.append(desc)
    parameters = ua.BrowseParameters()
    parameters.View = ua.ViewDescription()
    parameters.RequestedMaxReferencesPerNode = 0
    parameters.NodesToBrowse = descriptions
    results = await client.uaclient.browse(parameters)
    found: dict[str, list] = {}
    pending: list[tuple[str, object]] = []
    for node, result in zip(nodes, results):
        key = _canonical_node_id(node.nodeid)
        found[key] = list(getattr(result, "References", None) or [])
        point = getattr(result, "ContinuationPoint", None)
        if point:
            pending.append((key, point))
    while pending:
        nxt = ua.BrowseNextParameters()
        nxt.ReleaseContinuationPoints = False
        nxt.ContinuationPoints = [point for _, point in pending]
        try:
            more = await client.uaclient.browse_next(nxt)
        except Exception:
            log.debug("OPC UA browse continuation skipped", exc_info=True)
            break
        nxt_pending: list[tuple[str, object]] = []
        for (key, _), result in zip(pending, more):
            found[key].extend(list(getattr(result, "References", None) or []))
            point = getattr(result, "ContinuationPoint", None)
            if point:
                nxt_pending.append((key, point))
        pending = nxt_pending
    return found
def _ref_record(ref) -> dict:
    node_id = _canonical_node_id(ref.NodeId)
    title = _text(getattr(ref, "DisplayName", None), "") or _text(getattr(ref, "BrowseName", None), "Unnamed Node")
    node_class = getattr(getattr(ref, "NodeClass", None), "name", "Unknown")
    return {
        "title": title,
        "key": node_id,
        "NodeClass": node_class,
        "children": [],
        "has_children": False,
        "_property": _is_property(ref),
    }
async def _walk(client, node_id, depth, max_nodes, include_properties, count, visited):
    node_id = _canonical_node_id(node_id)
    if depth < 0 or count["n"] >= max_nodes:
        return []
    level = await _references(client, [node_id])
    refs = level.get(node_id, [])
    records = []
    child_ids = []
    for ref in refs:
        if count["n"] >= max_nodes:
            break
        record = _ref_record(ref)
        if record["key"] in visited:
            continue
        visited.add(record["key"])
        count["n"] += 1
        if record["_property"] and not include_properties:
            continue
        records.append(record)
        if not record["_property"]:
            child_ids.append(record["key"])
    nested = await _references(client, child_ids) if child_ids else {}
    output = []
    for record in records:
        kids = nested.get(record["key"], [])
        record["has_children"] = bool(kids)
        if depth > 0 and kids and not record["_property"] and record["NodeClass"] != "Variable":
            record["children"] = await _walk(
                client, record["key"], depth - 1, max_nodes, include_properties, count, visited
            )
        elif include_properties and record["NodeClass"] == "Variable":
            for ref in kids:
                if not _is_property(ref) or count["n"] >= max_nodes:
                    continue
                prop = _ref_record(ref)
                if prop["key"] in visited:
                    continue
                visited.add(prop["key"])
                count["n"] += 1
                record["children"].append({k: v for k, v in prop.items() if k != "_property"})
                record["has_children"] = True
        output.append({k: v for k, v in record.items() if k != "_property"})
    return output
async def _variables(client, node_id, depth, max_nodes, count, visited):
    node_id = _canonical_node_id(node_id)
    if depth < 0 or count["n"] >= max_nodes:
        return []
    found = []
    level = await _references(client, [node_id])
    for ref in level.get(node_id, []):
        if count["n"] >= max_nodes:
            break
        if _is_property(ref):
            continue
        record = _ref_record(ref)
        if record["key"] in visited:
            continue
        visited.add(record["key"])
        count["n"] += 1
        if record["NodeClass"] == "Variable":
            found.append({"namespace": record["key"], "displayName": record["title"]})
            continue
        if depth > 0:
            found.extend(await _variables(client, record["key"], depth - 1, max_nodes, count, visited))
    return found
async def handle(ctx: LoopContext, command) -> None:
    try:
        if isinstance(command, Connect):
            await _connect(ctx, command)
        elif isinstance(command, Disconnect):
            await _disconnect(ctx, command)
        elif isinstance(command, ReadBatch):
            await _read_batch(ctx, command)
        elif isinstance(command, Subscribe):
            await _subscribe(ctx, command)
        elif isinstance(command, Unsubscribe):
            await _unsubscribe(ctx, command)
        elif isinstance(command, Browse):
            await _browse(ctx, command)
        elif isinstance(command, Write):
            await _write(ctx, command)
        elif isinstance(command, Discover):
            await _discover(ctx, command)
    except Exception as exc:
        name = getattr(command, "client_name", None)
        if isinstance(exc, ConnectionError):
            client = ctx.sessions.get(name) if name else None
            if client is None or not _session_usable(client):
                if name:
                    ctx.set_connected(name, False)
            log.warning("field client command dropped type=%s client=%s error=%s", type(command).__name__, name, exc)
        else:
            log.error("field client command failed type=%s", type(command).__name__, exc_info=True)
        correlation = getattr(command, "correlation_id", None)
        if correlation and isinstance(command, ReadBatch):
            ctx.results.put(ReadBatchResult(correlation, None))
        elif correlation:
            ctx.results.put(CommandResult(correlation, False, error=f"{type(exc).__name__}: {exc}"))
async def _connect(ctx: LoopContext, command: Connect) -> None:
    async with ctx.lock_for(command.client_name):
        current = ctx.sessions.get(command.client_name)
        if current is not None:
            try:
                await current.disconnect()
            except Exception:
                pass
        client = AsyncClient(
            command.url,
            timeout=command.timeout,
            auto_reconnect=True,
            reconnect_request_timeout=min(10.0, float(command.timeout or 10)),
        )
        if command.username:
            client.set_user(command.username)
        if command.password:
            client.set_password(command.password)
        await client.connect()
        ctx.sessions[command.client_name] = client
        open_session = client.uaclient.state is UaClientState.CONNECTED
        ctx.set_connected(command.client_name, open_session)
        ctx.results.put(CommandResult(command.correlation_id, open_session))
async def _disconnect(ctx: LoopContext, command: Disconnect) -> None:
    async with ctx.lock_for(command.client_name):
        sub = ctx.subs.pop(command.client_name, None)
        if sub is not None:
            try:
                await sub.delete()
            except Exception:
                pass
        client = ctx.sessions.pop(command.client_name, None)
        if client is not None:
            await client.disconnect()
        ctx.set_connected(command.client_name, False)
        ctx.results.put(CommandResult(command.correlation_id, True))
def _session_usable(client) -> bool:
    """CONNECTED serves the request. RECONNECTING is owned by asyncua, not by the logger."""
    state = getattr(getattr(client, "uaclient", None), "state", None)
    return state is UaClientState.CONNECTED or state is UaClientState.RECONNECTING
async def _ensure_session(ctx: LoopContext, name: str):
    """One reconnect when the plant session is already down. Complexity: O(1) plus connect."""
    client = ctx.sessions.get(name)
    if client is None:
        ctx.set_connected(name, False)
        return None
    if _session_usable(client):
        return client
    try:
        await client.connect()
    except Exception:
        log.warning("field client reconnect failed name=%s", name)
        ctx.sessions.pop(name, None)
        ctx.set_connected(name, False)
        return None
    if not _session_usable(client):
        ctx.set_connected(name, False)
        return None
    ctx.set_connected(name, True)
    return client
async def _read_batch(ctx: LoopContext, command: ReadBatch) -> None:
    async with ctx.lock_for(command.client_name):
        client = ctx.sessions.get(command.client_name)
        if client is None or not _session_usable(client):
            ctx.set_connected(command.client_name, False)
            ctx.results.put(ReadBatchResult(command.correlation_id, None))
            return
        if client.uaclient.state is not UaClientState.CONNECTED:
            ctx.results.put(ReadBatchResult(command.correlation_id, None))
            return
        nodes = [client.get_node(node_id) for node_id in command.node_ids]
        values = await client.read_attributes(nodes, ua.AttributeIds.Value)
        ctx.results.put(ReadBatchResult(command.correlation_id, tuple(values)))
async def _subscribe(ctx: LoopContext, command: Subscribe) -> None:
    async with ctx.lock_for(command.client_name):
        client = ctx.sessions.get(command.client_name)
        if client is None:
            return
        sub = ctx.subs.get(command.client_name)
        if sub is None:
            sub = await client.create_subscription(command.period_ms, DasHandler(ctx.results))
            ctx.subs[command.client_name] = sub
        nodes = [client.get_node(node_id) for node_id in command.node_ids]
        if nodes:
            created = await sub.subscribe_data_change(nodes)
            if not isinstance(created, list):
                created = [created]
            bucket = ctx.handles.setdefault(command.client_name, {})
            for node_id, handle in zip(command.node_ids, created):
                if isinstance(handle, int):
                    bucket[node_id] = handle
            values = await client.read_attributes(nodes, ua.AttributeIds.Value)
            for node_id, data_value in zip(command.node_ids, values):
                ctx.results.put(
                    DasResult(
                        namespace=node_id,
                        value=_variant_value(data_value),
                        status_code=getattr(data_value, "StatusCode", None),
                        source_timestamp=getattr(data_value, "SourceTimestamp", None),
                    )
                )
async def _unsubscribe(ctx: LoopContext, command: Unsubscribe) -> None:
    async with ctx.lock_for(command.client_name):
        sub = ctx.subs.get(command.client_name)
        if sub is None:
            return
        if not command.node_ids:
            try:
                await sub.delete()
            except Exception:
                pass
            ctx.subs.pop(command.client_name, None)
            ctx.handles.pop(command.client_name, None)
            return
        bucket = ctx.handles.get(command.client_name, {})
        handles = []
        for node_id in command.node_ids:
            handle = bucket.pop(node_id, None)
            if isinstance(handle, int):
                handles.append(handle)
        if handles:
            try:
                await sub.unsubscribe(handles)
            except Exception:
                log.debug("unsubscribe skipped client=%s", command.client_name, exc_info=True)
async def _browse(ctx: LoopContext, command: Browse) -> None:
    async with ctx.lock_for(command.client_name):
        client = await _ensure_session(ctx, command.client_name)
        if client is None:
            ctx.results.put(CommandResult(command.correlation_id, False, error="not-connected"))
            return
        mode = command.mode
        if mode == "attributes":
            values = await _read_many(client, command.node_id)
            ctx.results.put(CommandResult(command.correlation_id, True, _attr_dict(command.node_id, values)))
            return
        if mode == "values":
            nodes = [client.get_node(command.node_id)]
            data_values = await client.read_attributes(nodes, ua.AttributeIds.Value)
            ctx.results.put(CommandResult(command.correlation_id, True, _variant_value(data_values[0]) if data_values else None))
            return
        if mode == "variables":
            payload = await _variables(client, command.node_id, command.depth, command.max_nodes, {"n": 0}, set())
        elif mode == "children":
            payload = await _walk(client, command.node_id, 0, command.max_nodes, command.include_properties, {"n": 0}, set())
        else:
            payload = await _walk(
                client,
                command.node_id,
                command.depth,
                command.max_nodes,
                command.include_properties,
                {"n": 0},
                set(),
            )
        ctx.results.put(CommandResult(command.correlation_id, True, payload))
async def _write(ctx: LoopContext, command: Write) -> None:
    async with ctx.lock_for(command.client_name):
        client = await _ensure_session(ctx, command.client_name)
        if client is None:
            ctx.results.put(CommandResult(command.correlation_id, False, error="not-connected"))
            return
        node = client.get_node(command.node_id)
        node_class = await node.read_node_class()
        if getattr(node_class, "name", "").lower() != "variable":
            ctx.results.put(CommandResult(command.correlation_id, False, error=f"not-variable:{getattr(node_class, 'name', node_class)}"))
            return
        await node.write_value(command.value)
        ctx.results.put(CommandResult(command.correlation_id, True, command.value))
async def _discover(ctx: LoopContext, command: Discover) -> None:
    client = AsyncClient(command.url)
    if command.kind == "endpoints":
        payload = await client.connect_and_get_server_endpoints()
    else:
        payload = await client.connect_and_find_servers()
    ctx.results.put(CommandResult(command.correlation_id, True, payload))
