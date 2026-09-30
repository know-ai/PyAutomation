"""Folder cache for the canonical address space. Lookups are O(1)."""

from __future__ import annotations

from asyncua import ua

from .identity import folder_token

_KINDS = ("Process", "Alarms", "Engines")


class AddressSpaceBuilder:
    def __init__(self, objects_node, namespace_idx: int) -> None:
        self._objects = objects_node
        self._idx = namespace_idx
        self._folders: dict[str, object] = {}
        self._root = None
        self.analog_item_supported: bool | None = None

    @property
    def folder_cache(self) -> dict:
        return self._folders

    def _folder(self, key: str, parent, browse_name: str):
        cached = self._folders.get(key)
        if cached is not None:
            return cached
        node = parent.add_folder(self._idx, browse_name)
        self._folders[key] = node
        return node

    def ensure_root(self):
        """Complexity: O(1)."""
        if self._root is None:
            self._root = self._folder("root", self._objects, "PyAutomationIO")
        return self._root

    def ensure_branch(self, site: str | None, area: str | None, kind: str, *, under_default: bool = False):
        """Process/Alarms/Engines at the root, or Process/Alarms inside Default. Complexity: O(1)."""
        del site, area
        if kind not in _KINDS:
            raise ValueError(f"Unknown folder kind: {kind}")
        root = self.ensure_root()
        if under_default and kind != "Engines":
            default_node = self._folder("default", root, "Default")
            return self._folder(f"default.{kind.lower()}", default_node, kind)
        return self._folder(kind.lower(), root, kind)

    def ensure_group(self, site: str | None, area: str | None, kind: str, group: str, *, under_default: bool = False):
        """Folder under Process/Alarms/Engines. Complexity: O(1)."""
        label = folder_token(group, "")
        if not label:
            return self.ensure_branch(site, area, kind, under_default=under_default)
        parent = self.ensure_branch(site, area, kind, under_default=under_default)
        prefix = f"default.{kind.lower()}" if under_default and kind != "Engines" else kind.lower()
        return self._folder(f"{prefix}.{label}", parent, label)

    async def _folder_async(self, key: str, parent, browse_name: str):
        cached = self._folders.get(key)
        if cached is not None:
            return cached
        node_id = _ua_node_id(key, self._idx)
        node = await _add_or_adopt(parent, "add_folder", node_id, browse_name)
        self._folders[key] = node
        return node

    async def ensure_branch_async(self, site: str | None, area: str | None, kind: str, *, under_default: bool = False):
        """Async folder lookup. Site and area are ignored. Complexity: O(1)."""
        del site, area
        if kind not in _KINDS:
            raise ValueError(f"Unknown folder kind: {kind}")
        root = await self._folder_async("root", self._objects, "PyAutomationIO")
        if under_default and kind != "Engines":
            default_node = await self._folder_async("default", root, "Default")
            return await self._folder_async(f"default.{kind.lower()}", default_node, kind)
        return await self._folder_async(kind.lower(), root, kind)

    async def ensure_group_async(
        self, site: str | None, area: str | None, kind: str, group: str, *, under_default: bool = False
    ):
        """Async folder under Process/Alarms/Engines. Complexity: O(1)."""
        label = folder_token(group, "")
        if not label:
            return await self.ensure_branch_async(site, area, kind, under_default=under_default)
        parent = await self.ensure_branch_async(site, area, kind, under_default=under_default)
        prefix = f"default.{kind.lower()}" if under_default and kind != "Engines" else kind.lower()
        return await self._folder_async(f"{prefix}.{label}", parent, label)

    def reject_reserved_leaf(self, name: str) -> None:
        """Reject a leaf whose business name uses a system prefix. Complexity: O(len(name))."""
        from .identity import validate_tag_name

        validate_tag_name(name)

    def build_tree(self, site: str | None, area: str | None) -> dict:
        """Create Default/Process, Default/Alarms and the root Process, Engines, Alarms folders."""
        self.ensure_branch(site, area, "Process", under_default=True)
        self.ensure_branch(site, area, "Alarms", under_default=True)
        return {kind: self.ensure_branch(site, area, kind) for kind in _KINDS}

    def add_variable(self, parent, identifier: str, browse_name: str, initial):
        """Complexity: O(1)."""
        node = parent.add_variable(
            _ua_node_id(identifier, self._idx),
            browse_name,
            initial,
        )
        return node

    async def add_variable_async(self, parent, identifier: str, browse_name: str, initial):
        """Create the leaf, or reuse it when a restarted shelf already holds that NodeId."""
        return await _add_or_adopt(
            parent,
            "add_variable",
            _ua_node_id(identifier, self._idx),
            browse_name,
            initial,
        )

    def add_property(self, parent, identifier: str, browse_name: str, value):
        """Complexity: O(1)."""
        return parent.add_property(
            _ua_node_id(identifier, self._idx),
            browse_name,
            value if value is not None else "",
        )

    async def add_property_async(self, parent, identifier: str, browse_name: str, value):
        """Create the property, or reuse it when a restarted shelf already holds that NodeId."""
        return await _add_or_adopt(
            parent,
            "add_property",
            _ua_node_id(identifier, self._idx),
            browse_name,
            value if value is not None else "",
        )

    def try_analog_item(self, node) -> bool:
        """Point HasTypeDefinition at AnalogItemType when the startup probe passed. Complexity: O(1)."""
        from .flags import analog_item_enabled

        if self.analog_item_supported is False or not analog_item_enabled():
            return False
        return self.swap_analog_item(node)

    @staticmethod
    def swap_analog_item(node) -> bool:
        """Swap the typedef. False when this stack refuses AnalogItemType. Complexity: O(1)."""
        try:
            node.delete_reference(
                ua.ObjectIds.BaseDataVariableType,
                ua.ObjectIds.HasTypeDefinition,
                forward=True,
                bidirectional=False,
            )
            node.add_reference(
                ua.NodeId(ua.ObjectIds.AnalogItemType),
                ua.ObjectIds.HasTypeDefinition,
                forward=True,
                bidirectional=False,
            )
            return True
        except Exception:
            return False

    async def swap_analog_item_async(self, node) -> bool:
        """Async typedef swap. Complexity: O(1)."""
        try:
            await node.delete_reference(
                ua.ObjectIds.BaseDataVariableType,
                ua.ObjectIds.HasTypeDefinition,
                forward=True,
                bidirectional=False,
            )
            await node.add_reference(
                ua.NodeId(ua.ObjectIds.AnalogItemType),
                ua.ObjectIds.HasTypeDefinition,
                forward=True,
                bidirectional=False,
            )
            return True
        except Exception:
            return False


def _ua_node_id(identifier: str, namespace_idx: int):
    return ua.NodeId(Identifier=identifier, NamespaceIndex=int(namespace_idx))


def _id_in_use(exc: BaseException) -> bool:
    return type(exc).__name__ == "BadNodeIdExists" or "BadNodeIdExists" in str(exc)


async def _adopt_existing(parent, node_id):
    """Return the node the shelf restored for this NodeId. Complexity: O(1).

    asyncua nodes keep the session on ``parent.session``. A missing attribute
    here used to re-raise BadNodeIdExists on every restart.
    """
    session = getattr(parent, "session", None)
    if session is not None:
        from asyncua import Node

        node = Node(session, node_id)
        await node.read_browse_name()
        return node
    server = getattr(parent, "server", None)
    if server is None or not hasattr(server, "get_node"):
        raise LookupError("OPC UA parent has no session")
    node = server.get_node(node_id)
    read = getattr(node, "read_browse_name", None)
    if callable(read):
        result = read()
        if hasattr(result, "__await__"):
            await result
    return node


async def _write_adopted(node, value) -> None:
    write = getattr(node, "write_value", None)
    if not callable(write):
        return
    try:
        result = write(value)
        if hasattr(result, "__await__"):
            await result
    except Exception:
        return


async def _add_or_adopt(parent, method: str, node_id, *args):
    """Add a node, or bind the one already stored under that NodeId."""
    try:
        return await getattr(parent, method)(node_id, *args)
    except Exception as exc:
        if not _id_in_use(exc):
            raise
        try:
            node = await _adopt_existing(parent, node_id)
        except Exception:
            raise exc
        if method == "add_property" and args:
            await _write_adopted(node, args[-1])
        return node
