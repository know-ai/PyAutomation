# -*- coding: utf-8 -*-
import unittest

from automation.catalog.alarms import sync_failed_description
from automation.catalog.replicator import CatalogReplicatorWorker


class TestCatalogFaultText(unittest.TestCase):
    def test_description_names_the_live_fault(self):
        self.assertEqual(sync_failed_description(""), "Catalog sync failed")
        text = sync_failed_description("tags row 12: server closed the connection")
        self.assertTrue(text.startswith("Catalog sync failed:"))
        self.assertIn("tags row 12", text)
        self.assertLessEqual(len(text), 256)

    def test_remote_fault_keeps_table_and_message(self):
        worker = CatalogReplicatorWorker.__new__(CatalogReplicatorWorker)
        worker._transient_remote_errors = 0
        worker._last_remote_fault = ""
        worker._note_remote_fault(
            ConnectionError("server closed the connection unexpectedly"),
            table="tags",
            key="42",
        )
        self.assertEqual(worker._transient_remote_errors, 1)
        self.assertIn("tags row 42", worker._last_remote_fault)
        self.assertIn("server closed the connection", worker._last_remote_fault)
