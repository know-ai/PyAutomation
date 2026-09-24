"""Execute commands on the asyncio thread. One write call per batch."""

from __future__ import annotations

import logging
from pathlib import Path

from asyncua import Server, ua

from ..address_space import AddressSpaceBuilder
from ..audit import audit_failure
from .commands import (
    ApplyAccess,
    DropTag,
    ExposeEntity,
    ResetServer,
    StartEndpoint,
    StopServer,
    WriteItem,
    WriteValues,
)

_LOG = logging.getLogger("pyautomation")
BATCH_LIMIT = 200


class LoopContext:
    def __init__(self, app) -> None:
        self.app = app
        self.ua_server = None
        self.builder = None
        self.subscription = None
        self.subscription_count = 0
        self.nodes: dict[str, object] = {}


def _node_id(identifier: str, namespace_idx: int):
    return ua.NodeId(Identifier=identifier, NamespaceIndex=int(namespace_idx))


def _property_value(key: str, value):
    if key == "EURange":
        low = high = None
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            low, high = value[0], value[1]
        else:
            low = getattr(value, "Low", None) or getattr(value, "low", None) or getattr(value, "min", None)
            high = getattr(value, "High", None) or getattr(value, "high", None) or getattr(value, "max", None)
        try:
            rng = ua.Range()
            rng.Low = float(low)
            rng.High = float(high)
            return rng
        except (TypeError, ValueError):
            return str(value)
    return value if value is not None else ""


async def open_server(ctx: LoopContext, command: StartEndpoint) -> None:
    """Start asyncua. Shelf failure falls back to a cold address space. Complexity: O(1) plus library init."""
    server = Server()
    shelf = Path(command.shelf_file) if command.shelf_file else None
    try:
        await server.init(shelf)
    except Exception:
        _LOG.warning("OPC UA shelf init failed; starting without cache", exc_info=True)
        server = Server()
        await server.init()
    server.set_endpoint(f"opc.tcp://{command.host}:{command.port}/OPCUAServer/")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    server.set_identity_tokens([ua.AnonymousIdentityToken])
    index = await server.register_namespace(command.namespace_uri)
    await server.start()
    app = ctx.app
    from ..writeback.sink import ScadaWriteSink, install_write_gate

    install_write_gate(server, app)
    if getattr(app, "scada_sink", None) is None:
        app.scada_sink = ScadaWriteSink()
    app.scada_sink.start(app)
    app.server = server
    app._namespace_idx = index
    app.objects = server.get_objects_node()
    app.builder = AddressSpaceBuilder(app.objects, index)
    ctx.ua_server = server
    ctx.builder = app.builder
    await _probe_analog(ctx)


async def _probe_analog(ctx: LoopContext) -> None:
    from ..flags import analog_item_enabled

    supported = False
    if analog_item_enabled() and ctx.builder is not None and ctx.app.objects is not None:
        try:
            node = await ctx.app.objects.add_variable(
                _node_id("pyautomation:analog-item-probe", ctx.app._namespace_idx),
                "probe",
                0.0,
            )
            supported = await ctx.builder.swap_analog_item_async(node)
            await node.delete()
        except Exception:
            supported = False
    ctx.app.analog_item_supported = supported
    if ctx.builder is not None:
        ctx.builder.analog_item_supported = supported


async def expose_entity(ctx: LoopContext, command: ExposeEntity) -> None:
    """Create one leaf and its properties. Complexity: O(P)."""
    if ctx.builder is None:
        return
    if command.identifier in ctx.nodes:
        await _rename_browse(ctx.nodes[command.identifier], command.browse)
        await _refresh_properties(ctx, command)
        return
    try:
        folder = await ctx.builder.ensure_branch_async(command.site, command.area, command.folder)
        groups = tuple(getattr(command, "groups", ()) or ())
        if groups:
            folder = await ctx.builder.ensure_group_async(
                command.site, command.area, command.folder, groups[0]
            )
        node = await ctx.builder.add_variable_async(folder, command.identifier, command.browse, command.initial)
        for extra in groups[1:]:
            other = await ctx.builder.ensure_group_async(
                command.site, command.area, command.folder, extra
            )
            try:
                await other.add_reference(
                    node.nodeid,
                    ua.ObjectIds.Organizes,
                    forward=True,
                    bidirectional=False,
                )
            except Exception:
                _LOG.debug("OPC UA extra engine folder skipped for %s", extra, exc_info=True)
    except Exception:
        if await _refresh_properties(ctx, command):
            return
        raise
    ctx.nodes[command.identifier] = node
    level = _level(command.access)
    from ..access.applier import apply_level
    from ..access.level import access_label

    await apply_level(node, level)
    namespace = f"ns={ctx.app._namespace_idx};s={command.identifier}"
    ctx.app._access_policy[namespace] = level
    ctx.app._opc_names[namespace] = command.name
    _remember_limits(ctx.app, namespace, command.properties)
    rows = [{
        "name": ".".join(
            part for part in (command.folder, *(getattr(command, "groups", ()) or ())[:1], command.browse) if part
        ),
        "namespace": namespace,
        "access_level": level,
        "access_level_label": access_label(level),
        "user_access_level": level,
        "access_restrictions": 0,
    }]
    for key, value in command.properties:
        prop = await ctx.builder.add_property_async(
            node,
            f"{command.identifier}.{key}",
            key,
            _property_value(key, value),
        )
        ctx.nodes[f"{command.identifier}.{key}"] = prop
        prop_namespace = f"ns={ctx.app._namespace_idx};s={command.identifier}.{key}"
        await apply_level(prop, level)
        ctx.app._access_policy[prop_namespace] = level
        rows.append({
            "name": f"{command.folder}.{command.browse}.{key}",
            "namespace": prop_namespace,
            "access_level": level,
            "access_level_label": access_label(level),
            "user_access_level": level,
            "access_restrictions": 0,
        })
    ctx.app._ua_nodes[command.identifier] = node
    listings = getattr(ctx.app, "_node_listings", None)
    if not isinstance(listings, dict):
        listings = {}
        ctx.app._node_listings = listings
    listings[command.identifier] = rows
    ctx.app._by_namespace[rows[0]["namespace"]] = node
    ctx.app._name_to_canonical[(command.entity_type, command.name)] = command.identifier
    if command.entity_type == "t":
        ctx.app.metrics.nodes_tags += 1
    elif command.entity_type == "a":
        ctx.app.metrics.nodes_alarms += 1
    else:
        ctx.app.metrics.nodes_engines += 1
    if level & 0x02:
        await _subscribe(ctx, command.identifier, node)


async def _property_node(ctx: LoopContext, identifier: str):
    node = ctx.nodes.get(identifier)
    if node is not None:
        return node
    server = ctx.ua_server
    if server is None:
        return None
    return server.get_node(_node_id(identifier, ctx.app._namespace_idx))


async def _ensure_write_subscription(ctx: LoopContext):
    """One shared subscription for every writable node. Complexity: O(1)."""
    if ctx.subscription is None and ctx.ua_server is not None:
        handler = getattr(ctx.app, "scada_sink", None)
        ctx.subscription = await ctx.ua_server.create_subscription(100, handler)
        ctx.subscription_count = 1
    return ctx.subscription


async def _apply_access(ctx: LoopContext, command: ApplyAccess) -> None:
    """Hot update of one node. Complexity: O(P) properties of that node."""
    from ..access.applier import apply_level
    from ..observability import emit_access_event, note_metric

    namespace = command.namespace
    level = _level(command.access_level)
    ctx.app.access.remember(namespace, level)
    ctx.app._access_policy[namespace] = level
    identifier = namespace.split(";s=")[-1]
    node = ctx.nodes.get(identifier)
    if node is not None:
        await apply_level(node, level)
        if level & 0x02:
            await _subscribe(ctx, identifier, node)
    note_metric(ctx.app, "access_level_changes")
    emit_access_event("changed", namespace, str(level))


async def _subscribe(ctx: LoopContext, identifier: str, node) -> None:
    subscription = await _ensure_write_subscription(ctx)
    if subscription is None:
        return
    await subscription.subscribe_data_change(node)
    ctx.app.writeback._items[identifier] = identifier
    ctx.app.metrics.write_subscriptions = ctx.app.writeback.active


def _unit_write(ctx: LoopContext, item: WriteItem, published: dict):
    """One string write for ``<id>.unit`` when the display symbol changed. Complexity: O(1)."""
    symbol = getattr(item, "unit", None)
    if not symbol or published.get(item.identifier) == symbol:
        return None
    published[item.identifier] = symbol
    wv = ua.WriteValue()
    wv.NodeId = _node_id(f"{item.identifier}.unit", ctx.app._namespace_idx)
    wv.AttributeId = ua.AttributeIds.Value
    wv.Value = ua.DataValue(ua.Variant(str(symbol), ua.VariantType.String))
    return wv


async def write_batch(ctx: LoopContext, items: tuple[WriteItem, ...]) -> None:
    """One session write for the whole batch. Complexity: O(K)."""
    if ctx.ua_server is None or not items:
        return
    published = getattr(ctx.app, "_published_units", None)
    if not isinstance(published, dict):
        published = {}
        ctx.app._published_units = published
    values = []
    for item in items:
        refresh = getattr(item, "refresh", None)
        if refresh is not None:
            await _refresh_properties(ctx, refresh)
        if isinstance(item.data_value, ExposeEntity):
            await _refresh_properties(ctx, item.data_value)
            continue
        wv = ua.WriteValue()
        wv.NodeId = _node_id(item.identifier, ctx.app._namespace_idx)
        wv.AttributeId = ua.AttributeIds.Value
        wv.Value = item.data_value
        values.append(wv)
        unit_write = _unit_write(ctx, item, published)
        if unit_write is not None:
            values.append(unit_write)
    if not values:
        return
    params = ua.WriteParameters()
    params.NodesToWrite = values
    await ctx.ua_server.iserver.isession.write(params)


async def _rename_browse(node, browse: str) -> None:
    """Update the tree label. The NodeId stays. Complexity: O(1)."""
    if node is None or not browse:
        return
    try:
        index = int(node.nodeid.NamespaceIndex)
        await node.write_attribute(
            ua.AttributeIds.BrowseName,
            ua.DataValue(ua.QualifiedName(browse, index)),
        )
        await node.write_attribute(
            ua.AttributeIds.DisplayName,
            ua.DataValue(ua.LocalizedText(browse)),
        )
    except Exception:
        _LOG.debug("OPC UA browse rename skipped for %s", browse, exc_info=True)


async def _refresh_properties(ctx: LoopContext, command: ExposeEntity) -> int:
    """Rewrite properties of a leaf that already exists, including a shelved one. Complexity: O(P)."""
    written = 0
    for key, value in command.properties:
        node = await _property_node(ctx, f"{command.identifier}.{key}")
        if node is None:
            continue
        try:
            await node.write_value(_property_value(key, value))
        except Exception:
            continue
        written += 1
    return written


async def drop_tag(ctx: LoopContext, command: DropTag) -> None:
    """Delete one tag node so a later expose can recreate it with a new variant type."""
    identifier = _identifier_for_name(ctx, command.name)
    if identifier:
        await _delete_tree(ctx, identifier)
    if command.reexpose:
        ctx.app._expose_seen.discard(("t", command.name))
        ctx.app.enqueue_expose("t", command.name)


def _identifier_for_name(ctx: LoopContext, name: str) -> str | None:
    for namespace, stored in list(getattr(ctx.app, "_opc_names", {}).items()):
        if stored != name or ";s=" not in str(namespace):
            continue
        return str(namespace).split(";s=", 1)[1]
    return None


async def _delete_tree(ctx: LoopContext, identifier: str) -> None:
    keys = [
        key
        for key in list(ctx.nodes)
        if key == identifier or key.startswith(f"{identifier}.")
    ]
    for key in keys:
        node = ctx.nodes.pop(key, None)
        if node is None:
            continue
        delete = getattr(node, "delete", None)
        if not callable(delete):
            continue
        try:
            result = delete()
            if hasattr(result, "__await__"):
                await result
        except Exception:
            _LOG.debug("OPC UA node delete skipped for %s", key, exc_info=True)


async def close_server(ctx: LoopContext) -> None:
    server = ctx.ua_server
    ctx.subscription = None
    ctx.subscription_count = 0
    ctx.nodes.clear()
    ctx.ua_server = None
    ctx.builder = None
    if server is not None:
        try:
            await server.stop()
        except Exception:
            audit_failure("OPC UA server stop failed", "reset")


def _level(access) -> int:
    from ..access.level import parse_access_level

    try:
        return parse_access_level(access if access is not None else 1)
    except ValueError:
        return 1


def _remember_limits(app, namespace: str, properties) -> None:
    low = high = None
    for key, value in properties:
        if key != "EURange":
            continue
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            low, high = value[0], value[1]
        else:
            low = getattr(value, "Low", None) or getattr(value, "low", None)
            high = getattr(value, "High", None) or getattr(value, "high", None)
    if low is None or high is None:
        return
    try:
        app._write_limits[namespace] = (float(low), float(high), "analog")
    except (TypeError, ValueError):
        return


async def handle(ctx: LoopContext, command) -> None:
    """Dispatch one command. Complexity: O(1) plus the command."""
    if isinstance(command, StartEndpoint):
        await open_server(ctx, command)
        return
    if isinstance(command, ApplyAccess):
        await _apply_access(ctx, command)
        return
    if isinstance(command, ExposeEntity):
        try:
            await expose_entity(ctx, command)
        except Exception as exc:
            ctx.app.metrics.expose_failures += 1
            audit_failure("OPC UA expose failed", f"{command.entity_type}:{command.name}: {exc}")
        return
    if isinstance(command, WriteValues):
        await write_batch(ctx, command.items)
        return
    if isinstance(command, DropTag):
        await drop_tag(ctx, command)
        return
    if isinstance(command, (ResetServer, StopServer)):
        await close_server(ctx)
        return
    apply = getattr(command, "apply", None)
    if apply is None:
        return
    result = apply(ctx)
    if hasattr(result, "__await__"):
        await result
