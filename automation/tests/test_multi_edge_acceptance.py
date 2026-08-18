# -*- coding: utf-8 -*-
"""Map CA-EDGE-1..8 onto focused unit checks. Full 2-edge soak is opt-in."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from ..node_scope import NodeIdentityError, NodeScope
from ..persistence.config import SafConfig
from ..persistence.orchestrator import PersistenceOrchestrator
from ..persistence.records import PersistableRecord
from ..tags.cvt import CVT
from ..tags.tag import Tag
from ..utils.db_connections import historian_application_name


def _env(node_id: str, area: str) -> dict[str, str]:
    return {
        "AUTOMATION_MULTI_EDGE_ENABLED": "true",
        "AUTOMATION_NODE_ID": node_id,
        "AUTOMATION_AREA": area,
    }


class TestAcceptanceCriteria(unittest.TestCase):
    def test_ca_edge_1_cvt_excludes_foreign_area(self):
        scope = NodeScope("edge-a", "Linea1")
        own = Tag("Linea1.FI_01", "kg/hr", "MassFlow", "float", area="Linea1", owner_node="edge-a")
        foreign = Tag("Linea2.FI_01", "kg/hr", "MassFlow", "float", area="Linea2", owner_node="edge-b")
        cvt = CVT()
        for tag in (own, foreign):
            cvt._tags[tag.id] = tag
            cvt._index_tag(tag)
        self.assertEqual(cvt.prune_not_owned(scope), ["Linea2.FI_01"])
        self.assertIs(cvt.get_tag_by_name("Linea1.FI_01"), own)
        self.assertIsNone(cvt.get_tag_by_name("Linea2.FI_01"))

    def test_ca_edge_2_foreign_opc_owner_is_rejected(self):
        scope = NodeScope("edge-a", "Linea1")
        self.assertFalse(scope.owns_node("edge-b"))
        self.assertTrue(scope.owns_node("edge-a"))

    def test_ca_edge_3_application_name_identifies_owner(self):
        with patch.dict(os.environ, _env("edge-a", "Linea1"), clear=False):
            name = historian_application_name("LoggerWorker")
        self.assertEqual(name, "PyAutomationIO:edge-a:LoggerWorker")

    def test_ca_edge_4_peer_cannot_enqueue_foreign_samples(self):
        stamp = datetime.now(timezone.utc)
        record = PersistableRecord.tag_sample(
            "Linea1.FI_01",
            1.0,
            stamp,
            area="Linea1",
            owner_node="edge-a",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, _env("edge-b", "Linea2"), clear=False
        ):
            gateway = PersistenceOrchestrator(
                config=SafConfig(journal_path=os.path.join(tmp, "edge-b.db"))
            )
            try:
                self.assertEqual(gateway.enqueue(record), 0)
            finally:
                gateway.close()

    def test_ca_edge_5_missing_identity_blocks_acquisition(self):
        scope = NodeScope.from_env(
            {"AUTOMATION_MULTI_EDGE_ENABLED": "true"}
        )
        self.assertTrue(scope.enabled)
        self.assertFalse(scope.is_valid)
        with self.assertRaises(NodeIdentityError):
            scope.validate_for_acquisition()

    def test_ca_edge_6_qualified_homologs_coexist(self):
        self.assertNotEqual("Linea1.FI_01", "Linea2.FI_01")
        scope_a = NodeScope("edge-a", "Linea1")
        scope_b = NodeScope("edge-b", "Linea2")
        tag_a = Tag("Linea1.FI_01", "kg/hr", "MassFlow", "float", area="Linea1", owner_node="edge-a")
        tag_b = Tag("Linea2.FI_01", "kg/hr", "MassFlow", "float", area="Linea2", owner_node="edge-b")
        self.assertTrue(scope_a.owns_tag(tag_a))
        self.assertFalse(scope_a.owns_tag(tag_b))
        self.assertTrue(scope_b.owns_tag(tag_b))

    def test_ca_edge_7_connection_budget_is_advertised(self):
        from ..utils.db_connections import snapshot_connection_metrics

        metrics = snapshot_connection_metrics(None)
        self.assertEqual(metrics["DB_CONNECTIONS_EXPECTED_MAX"], 4)
        self.assertIn("DB_APPLICATION_NAME", metrics)

    def test_ca_edge_8_api_hides_foreign_resources(self):
        from ..modules.tags.resources.tags import _scope_violation

        with patch.dict(os.environ, _env("edge-a", "Linea1"), clear=False):
            payload, status = _scope_violation(
                resource=Tag(
                    "Linea2.FI_01",
                    "kg/hr",
                    "MassFlow",
                    "float",
                    area="Linea2",
                    owner_node="edge-b",
                )
            )
        self.assertEqual(status, 403)


@unittest.skipUnless(
    os.environ.get("AUTOMATION_TWO_EDGE_IT") == "1",
    "opt-in two-edge integration: set AUTOMATION_TWO_EDGE_IT=1",
)
class TestTwoEdgeLive(unittest.TestCase):
    def test_placeholder_requires_external_harness(self):
        self.assertTrue(
            os.path.exists(os.environ.get("AUTOMATION_TWO_EDGE_EVIDENCE", "")),
            "Provide AUTOMATION_TWO_EDGE_EVIDENCE pointing at soak/CA evidence",
        )
