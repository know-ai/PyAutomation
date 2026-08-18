# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from peewee import SqliteDatabase

from ..dbmodels import Nodes, OPCUA, proxy
from ..node_scope import NodeScope
from ..persistence.config import SafConfig
from ..persistence.orchestrator import PersistenceOrchestrator
from ..persistence.records import PersistableRecord
from ..tags.cvt import CVT
from ..tags.tag import Tag


class _NoScanDict(dict):
    def values(self):
        raise AssertionError("hot-path lookup performed a linear scan")


class _OfflineRemote:
    def is_reachable(self):
        return False

    def write_batch(self, domain, payloads):
        raise AssertionError("remote write is not expected")


class TestTwoEdgeCatalog(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables([Nodes, OPCUA])

    def tearDown(self):
        self.db.close()

    def test_two_edges_hydrate_only_their_owned_clients(self):
        Nodes.register("edge-a", "Area-A")
        Nodes.register("edge-b", "Area-B")
        OPCUA.create("plc-a", "10.0.0.1", 4840, owner_node="edge-a")
        OPCUA.create("plc-b", "10.0.0.2", 4840, owner_node="edge-b")

        edge_a = [
            row.client_name for row in OPCUA.scoped(owner_node="edge-a")
        ]
        edge_b = [
            row.client_name for row in OPCUA.scoped(owner_node="edge-b")
        ]

        self.assertEqual(edge_a, ["plc-a"])
        self.assertEqual(edge_b, ["plc-b"])
        self.assertTrue(set(edge_a).isdisjoint(edge_b))


class TestScopedRuntime(unittest.TestCase):
    def test_reconnect_prunes_foreign_tags_and_keeps_owned_indexes(self):
        scope = NodeScope("edge-a", "Area-A")
        own = Tag(
            "Area-A.PV",
            "C",
            "Temperature",
            "float",
            area="Area-A",
            owner_node="edge-a",
        )
        foreign = Tag(
            "Area-B.PV",
            "C",
            "Temperature",
            "float",
            area="Area-B",
            owner_node="edge-b",
        )
        cvt = CVT()
        for tag in (own, foreign):
            cvt._tags[tag.id] = tag
            cvt._index_tag(tag)

        self.assertEqual(cvt.prune_not_owned(scope), ["Area-B.PV"])
        self.assertIs(cvt.get_tag_by_name("Area-A.PV"), own)
        self.assertIsNone(cvt.get_tag_by_name("Area-B.PV"))

    def test_name_lookup_is_indexed_and_does_not_scan_values(self):
        tag = Tag(
            "Area-A.PV",
            "C",
            "Temperature",
            "float",
            area="Area-A",
            owner_node="edge-a",
        )
        cvt = CVT()
        cvt._tags = _NoScanDict({tag.id: tag})
        cvt._index_tag(tag)
        self.assertIs(cvt.get_tag_by_name(tag.name), tag)


class TestIsolatedSaf(unittest.TestCase):
    def test_default_journal_path_is_namespaced_by_node(self):
        with patch.dict(
            os.environ,
            {
                "AUTOMATION_MULTI_EDGE_ENABLED": "true",
                "AUTOMATION_NODE_ID": "edge-a",
            },
            clear=False,
        ):
            path_a = SafConfig().journal_path
        with patch.dict(
            os.environ,
            {
                "AUTOMATION_MULTI_EDGE_ENABLED": "true",
                "AUTOMATION_NODE_ID": "edge-b",
            },
            clear=False,
        ):
            path_b = SafConfig().journal_path
        self.assertNotEqual(path_a, path_b)
        self.assertIn("edge-a", path_a)
        self.assertIn("edge-b", path_b)

    def test_two_edges_use_isolated_journals_and_reject_cross_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_a = SafConfig(journal_path=os.path.join(tmp, "edge-a.db"))
            config_b = SafConfig(journal_path=os.path.join(tmp, "edge-b.db"))
            env_a = {
                "AUTOMATION_MULTI_EDGE_ENABLED": "true",
                "AUTOMATION_NODE_ID": "edge-a",
                "AUTOMATION_AREA": "Area-A",
            }
            env_b = {
                "AUTOMATION_MULTI_EDGE_ENABLED": "true",
                "AUTOMATION_NODE_ID": "edge-b",
                "AUTOMATION_AREA": "Area-B",
            }
            stamp = datetime.now(timezone.utc)
            gateway_a = gateway_b = None
            try:
                with patch.dict(os.environ, env_a, clear=False):
                    gateway_a = PersistenceOrchestrator(
                        config=config_a,
                        remote=_OfflineRemote(),
                    )
                    own_a = PersistableRecord.tag_sample(
                        "Area-A.PV",
                        1.0,
                        stamp,
                        area="Area-A",
                        owner_node="edge-a",
                    )
                    foreign_b = PersistableRecord.tag_sample(
                        "Area-B.PV",
                        2.0,
                        stamp,
                        area="Area-B",
                        owner_node="edge-b",
                    )
                    gateway_a.enqueue(own_a)
                    gateway_a.flush_sync()
                    self.assertEqual(gateway_a.pending_count(), 1)
                    self.assertEqual(gateway_a.enqueue(foreign_b), 0)
                    gateway_a.flush_sync()
                    self.assertEqual(gateway_a.pending_count(), 1)

                with patch.dict(os.environ, env_b, clear=False):
                    gateway_b = PersistenceOrchestrator(
                        config=config_b,
                        remote=_OfflineRemote(),
                    )
                    own_b = PersistableRecord.tag_sample(
                        "Area-B.PV",
                        2.0,
                        stamp,
                        area="Area-B",
                        owner_node="edge-b",
                    )
                    foreign_a = PersistableRecord.tag_sample(
                        "Area-A.PV",
                        1.0,
                        stamp,
                        area="Area-A",
                        owner_node="edge-a",
                    )
                    gateway_b.enqueue(own_b)
                    gateway_b.flush_sync()
                    self.assertEqual(gateway_b.pending_count(), 1)
                    self.assertEqual(gateway_b.enqueue(foreign_a), 0)
                    gateway_b.flush_sync()
                    self.assertEqual(gateway_b.pending_count(), 1)

                self.assertEqual(gateway_a.pending_count(), 1)
                self.assertEqual(gateway_b.pending_count(), 1)
                self.assertNotEqual(config_a.journal_path, config_b.journal_path)
            finally:
                if gateway_a is not None:
                    gateway_a.close()
                if gateway_b is not None:
                    gateway_b.close()


if __name__ == "__main__":
    unittest.main()
