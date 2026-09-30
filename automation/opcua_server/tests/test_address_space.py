import asyncio
import unittest

from asyncua import ua

from automation.opcua_server.address_space import AddressSpaceBuilder


class BadNodeIdExists(Exception):
    def __str__(self):
        return "The requested node id is already used by another node.(BadNodeIdExists)"


class _Folder:
    def __init__(self, name="root"):
        self.name = name
        self.children = []

    def add_folder(self, _idx, name):
        child = _Folder(name)
        self.children.append(child)
        return child


class TestAddressSpace(unittest.TestCase):
    def test_build_tree_shape(self):
        objects = _Folder("Objects")
        builder = AddressSpaceBuilder(objects, 2)
        built = builder.build_tree("Supe", "Linea1")
        self.assertEqual(set(built), {"Process", "Alarms", "Engines"})
        names = [child.name for child in objects.children]
        self.assertEqual(names, ["PyAutomationIO"])

    def test_empty_site_and_area(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        builder.build_tree("", "")
        root = objects.children[0]
        names = {child.name for child in root.children}
        self.assertEqual(names, {"Default", "Process", "Alarms", "Engines"})
        default = next(child for child in root.children if child.name == "Default")
        self.assertEqual({child.name for child in default.children}, {"Process", "Alarms"})

    def test_idempotent_folders(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        builder.build_tree("Supe", "Linea1")
        first = len(builder.folder_cache)
        builder.build_tree("Supe", "Linea1")
        self.assertEqual(len(builder.folder_cache), first)
        self.assertEqual(len(objects.children), 1)

    def test_ensure_folder_is_cached(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        for _ in range(100):
            builder.ensure_branch("Supe", "Linea1", "Process")
        self.assertLessEqual(len(builder.folder_cache), 10)

    def test_engine_group_nests_under_engines(self):
        objects = _Folder()
        builder = AddressSpaceBuilder(objects, 2)
        folder = builder.ensure_group("Supe", "Linea1", "Engines", "LDS")
        self.assertEqual(folder.name, "lds")
        engines = objects.children[0].children[0]
        self.assertEqual(engines.name, "Engines")
        self.assertEqual([child.name for child in engines.children], ["lds"])
        again = builder.ensure_group("Supe", "Linea1", "Engines", "LDS")
        self.assertIs(again, folder)


class _ShelfSpace:
    """Address space that already contains NodeIds, as a restarted shelf does."""

    def __init__(self):
        self.server = self
        self.nodes = {}

    def get_node(self, node_id):
        return self.nodes[node_id.Identifier]

    def _add(self, node_id):
        if node_id.Identifier in self.nodes:
            raise BadNodeIdExists()
        node = _ShelfNode(node_id, self)
        self.nodes[node_id.Identifier] = node
        return node


class _ShelfNode:
    def __init__(self, node_id, space):
        self.nodeid = node_id
        self.server = space
        self.value = None

    async def read_browse_name(self):
        return "kept"

    async def write_value(self, value):
        self.value = value

    async def add_folder(self, node_id, _browse):
        return self.server._add(node_id)

    async def add_variable(self, node_id, _browse, _initial):
        return self.server._add(node_id)

    async def add_property(self, node_id, _browse, _value):
        return self.server._add(node_id)


class TestShelfRestart(unittest.TestCase):
    def test_restart_reuses_engine_nodes(self):
        space = _ShelfSpace()
        objects = _ShelfNode(ua.NodeId("Objects", 0), space)
        for key in ("root", "engines", "engines.lds", "lds", "lds.criticity"):
            space.nodes[key] = _ShelfNode(ua.NodeId(key, 2), space)
        builder = AddressSpaceBuilder(objects, 2)

        async def _run():
            folder = await builder.ensure_group_async("Supe", "Linea1", "Engines", "LDS")
            variable = await builder.add_variable_async(folder, "lds", "LDS", 0)
            prop = await builder.add_property_async(variable, "lds.criticity", "criticity", "high")
            return folder, variable, prop

        folder, variable, prop = asyncio.run(_run())
        self.assertIs(folder, space.nodes["engines.lds"])
        self.assertIs(variable, space.nodes["lds"])
        self.assertIs(prop, space.nodes["lds.criticity"])
        self.assertEqual(prop.value, "high")
