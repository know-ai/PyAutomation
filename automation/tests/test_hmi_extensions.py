# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from automation.utils import hmi_extensions


class TestHmiExtensions(unittest.TestCase):
    def setUp(self):
        hmi_extensions.clear_menu_items()

    def tearDown(self):
        hmi_extensions.clear_menu_items()

    def test_register_and_list_sorted(self):
        hmi_extensions.register_menu_item(
            {"id": "b", "path": "/b", "label_key": "nav.b", "priority": 20}
        )
        hmi_extensions.register_menu_item(
            {"id": "a", "path": "a", "label_key": "nav.a", "icon": "bi bi-x", "priority": 10}
        )
        items = hmi_extensions.list_menu_items()
        self.assertEqual([row["id"] for row in items], ["a", "b"])
        self.assertEqual(items[0]["path"], "/a")
        self.assertEqual(items[0]["icon"], "bi bi-x")

    def test_requires_id_and_path(self):
        with self.assertRaises(ValueError):
            hmi_extensions.register_menu_item({"id": "x"})


if __name__ == "__main__":
    unittest.main()
