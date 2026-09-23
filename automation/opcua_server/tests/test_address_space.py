import unittest

from automation.opcua_server.address_space import AddressSpaceBuilder


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
        site = objects.children[0].children[0]
        area = site.children[0]
        self.assertEqual(site.name, "Default")
        self.assertEqual(area.name, "Global")

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
