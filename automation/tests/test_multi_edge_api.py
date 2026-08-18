# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from ..modules.tags.resources.tags import _scope_violation
from ..node_scope import NodeScope
from ..tags.cvt import CVT
from ..tags.tag import Tag


class FakeTag:
    def __init__(self, area, owner_node):
        self.area = area
        self.owner_node = owner_node


class TestApiScope(unittest.TestCase):
    def test_foreign_payload_is_forbidden(self):
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-a",
            "AUTOMATION_AREA": "Area-A",
        }
        with patch.dict(os.environ, env, clear=False):
            forbidden, status = _scope_violation(
                payload={"area": "Area-B", "owner_node": "edge-b"}
            )
        self.assertEqual(status, 403)
        self.assertIn("area", forbidden["message"])

    def test_foreign_resource_is_forbidden(self):
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-a",
            "AUTOMATION_AREA": "Area-A",
        }
        with patch.dict(os.environ, env, clear=False):
            forbidden, status = _scope_violation(
                resource=FakeTag("Area-B", "edge-b")
            )
        self.assertEqual(status, 403)

    def test_missing_identity_is_unavailable(self):
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "",
            "AUTOMATION_AREA": "",
            "AUTOMATION_SEGMENT": "",
        }
        with patch.dict(os.environ, env, clear=False):
            payload, status = _scope_violation(payload={})
        self.assertEqual(status, 503)

    def test_owned_payload_is_accepted(self):
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-a",
            "AUTOMATION_AREA": "Area-A",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertIsNone(
                _scope_violation(
                    payload={"area": "Area-A", "owner_node": "edge-a"},
                    resource=FakeTag("Area-A", "edge-a"),
                )
            )


class TestOwnershipHotPath(unittest.TestCase):
    def test_set_value_ownership_check_stays_indexed(self):
        cvt = CVT()
        tag = Tag(
            "Area-A.PV",
            "C",
            "Temperature",
            "float",
            area="Area-A",
            owner_node="edge-a",
        )
        cvt._tags[tag.id] = tag
        cvt._index_tag(tag)
        stamp = datetime.now(timezone.utc)
        scope = NodeScope("edge-a", "Area-A")
        with patch("automation.tags.tag._node_scope", return_value=scope):
            started = time.perf_counter()
            for index in range(2000):
                cvt.set_value(id=tag.id, value=float(index), timestamp=stamp)
            elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertLess(elapsed_ms / 2000, 0.25)
        self.assertEqual(tag.get_value(), 1999.0)


class TestScopedMutations(unittest.TestCase):
    def test_import_rejects_foreign_runtime_before_mutation(self):
        from .. import PyAutomation

        app = PyAutomation()
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-a",
            "AUTOMATION_AREA": "Linea1",
        }
        with patch.dict(os.environ, env, clear=False):
            result = app.import_configuration(
                {
                    "data": {
                        "Tags": [
                            {
                                "name": "Linea2.FI_01",
                                "area": "Linea2",
                                "owner_node": "edge-b",
                            }
                        ]
                    }
                }
            )
        self.assertEqual(result["error"], "foreign-or-unscoped-runtime-data")
        self.assertTrue(result["violations"])

    def test_opc_client_tree_is_forbidden_for_foreign_owner(self):
        from .. import PyAutomation
        from ..modules.opcua.resources.clients import _client_scope_error

        app = PyAutomation()
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-a",
            "AUTOMATION_AREA": "Linea1",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            app, "get_opcua_clients", return_value={}
        ), patch.object(
            app, "is_db_connected", return_value=False
        ), patch.object(
            app.opcua_client_manager, "_clients", {"PLC-B": object()}
        ):
            payload, status = _client_scope_error("PLC-B")
        self.assertEqual(status, 403)
        self.assertIn("another edge", payload["message"])

    def test_alarm_mutation_is_unavailable_without_identity(self):
        from ..modules.alarms.resources.alarms import _alarm_scope_error

        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "",
            "AUTOMATION_AREA": "",
            "AUTOMATION_SEGMENT": "",
        }
        with patch.dict(os.environ, env, clear=False):
            payload, status = _alarm_scope_error(alarm_name="Linea2.ALM.1")
        self.assertEqual(status, 503)
        self.assertIn("identity", payload["message"].lower())
