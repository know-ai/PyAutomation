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

    def ensure_branch(self, site: str | None, area: str | None, kind: str):
        """Return the Process/Alarms/Engines folder. Idempotent. Complexity: O(1)."""
        if kind not in _KINDS:
            raise ValueError(f"Unknown folder kind: {kind}")
        site_name = folder_token(site, "Default")
        area_name = folder_token(area, "Global")
        root = self.ensure_root()
        site_node = self._folder(f"site:{site_name}", root, site_name)
        area_node = self._folder(f"area:{site_name}:{area_name}", site_node, area_name)
        return self._folder(f"kind:{site_name}:{area_name}:{kind}", area_node, kind)

    def ensure_group(self, site: str | None, area: str | None, kind: str, group: str):
        """Folder under Process/Alarms/Engines. Complexity: O(1)."""
        label = folder_token(group, "")
        if not label:
            return self.ensure_branch(site, area, kind)
        parent = self.ensure_branch(site, area, kind)
        site_name = folder_token(site, "Default")
        area_name = folder_token(area, "Global")
        return self._folder(f"group:{site_name}:{area_name}:{kind}:{label}", parent, label)

    async def _folder_async(self, key: str, parent, browse_name: str):
        cached = self._folders.get(key)
        if cached is not None:
            return cached
        node = await parent.add_folder(_ua_node_id(key, self._idx), browse_name)
        self._folders[key] = node
        return node

    async def ensure_branch_async(self, site: str | None, area: str | None, kind: str):
        """Async folder lookup. Complexity: O(1)."""
        if kind not in _KINDS:
            raise ValueError(f"Unknown folder kind: {kind}")
        site_name = folder_token(site, "Default")
        area_name = folder_token(area, "Global")
        root = await self._folder_async("root", self._objects, "PyAutomationIO")
        site_node = await self._folder_async(f"site:{site_name}", root, site_name)
        area_node = await self._folder_async(f"area:{site_name}:{area_name}", site_node, area_name)
        return await self._folder_async(f"kind:{site_name}:{area_name}:{kind}", area_node, kind)

    async def ensure_group_async(self, site: str | None, area: str | None, kind: str, group: str):
        """Async folder under Process/Alarms/Engines. Complexity: O(1)."""
        label = folder_token(group, "")
        if not label:
            return await self.ensure_branch_async(site, area, kind)
        parent = await self.ensure_branch_async(site, area, kind)
        site_name = folder_token(site, "Default")
        area_name = folder_token(area, "Global")
        return await self._folder_async(
            f"group:{site_name}:{area_name}:{kind}:{label}",
            parent,
            label,
        )

    def reject_reserved_leaf(self, name: str) -> None:
        """Reject a leaf whose business name uses a system prefix. Complexity: O(len(name))."""
        from .identity import validate_tag_name

        validate_tag_name(name)

    def build_tree(self, site: str | None, area: str | None) -> dict:
        """Create PyAutomationIO/{Site}/{Area}/{Process,Alarms,Engines}. Complexity: O(1)."""
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
        """Complexity: O(1)."""
        return await parent.add_variable(_ua_node_id(identifier, self._idx), browse_name, initial)

    def add_property(self, parent, identifier: str, browse_name: str, value):
        """Complexity: O(1)."""
        return parent.add_property(
            _ua_node_id(identifier, self._idx),
            browse_name,
            value if value is not None else "",
        )

    async def add_property_async(self, parent, identifier: str, browse_name: str, value):
        """Complexity: O(1)."""
        return await parent.add_property(
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
