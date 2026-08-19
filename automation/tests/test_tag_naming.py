# -*- coding: utf-8 -*-
"""CA-TAG-01 … CA-TAG-07: HMI user-tag name qualification (multi-edge)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ..node_scope import NodeScope
from ..tag_naming import TagNameError, qualify_user_tag_name, tag_name_validation_skipped


SITE = "SiteA"
AREA = "Linea1"
NODE_ID = "edge-linea1"


class TestQualifyUserTagName(unittest.TestCase):
    def test_ca_tag_01_bare_name_is_prefixed(self):
        qualified = qualify_user_tag_name("FI_01", SITE, AREA)
        self.assertEqual(qualified.name, "SiteA.Linea1.FI_01")
        self.assertEqual(qualified.base_name, "FI_01")

    def test_ca_tag_02_two_parts_are_rejected(self):
        with self.assertRaises(TagNameError) as ctx:
            qualify_user_tag_name("Linea1.FI_01", SITE, AREA)
        self.assertIn("SiteA.Linea1.", str(ctx.exception))

    def test_ca_tag_03_matching_three_parts_kept(self):
        qualified = qualify_user_tag_name("SiteA.Linea1.FI_01", SITE, AREA)
        self.assertEqual(qualified.name, "SiteA.Linea1.FI_01")
        self.assertEqual(qualified.base_name, "FI_01")

    def test_ca_tag_04_foreign_three_parts_rejected(self):
        with self.assertRaises(TagNameError) as ctx:
            qualify_user_tag_name("SiteB.Linea2.FI_01", SITE, AREA)
        self.assertIn("SiteA.Linea1", str(ctx.exception))

    def test_more_than_three_parts_reserved(self):
        with self.assertRaises(TagNameError) as ctx:
            qualify_user_tag_name("SiteA.Linea1.LDS.leak", SITE, AREA)
        self.assertIn("reserved", str(ctx.exception).lower())

    def test_missing_scope_leaves_name_unchanged(self):
        qualified = qualify_user_tag_name("FI_01", None, AREA)
        self.assertEqual(qualified.name, "FI_01")


class TestCreateTagQualification(unittest.TestCase):
    def setUp(self):
        self.env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": NODE_ID,
            "AUTOMATION_AREA": AREA,
            "AUTOMATION_SITE": SITE,
            "AUTOMATION_SKIP_TAG_VALIDATION": "",
        }

    def _app(self):
        from .. import PyAutomation

        app = PyAutomation()
        app._refresh_node_scope()
        return app

    def test_ca_tag_01_create_tag_qualifies_and_stamps_owner(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag, msg = app.create_tag(name="FI_01", unit="m3/hr", variable="VolumetricFlow")
            self.assertIsNotNone(tag, msg)
            self.assertEqual(tag.name, "SiteA.Linea1.FI_01")
            self.assertEqual(tag.display_name, "FI_01")
            self.assertEqual(tag.area, AREA)
            self.assertEqual(tag.owner_node, NODE_ID)

    def test_ca_tag_02_create_tag_rejects_two_parts(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag, msg = app.create_tag(name="Linea1.FI_01", unit="m3/h", variable="VolumetricFlow")
            self.assertIsNone(tag)
            self.assertIn("SiteA.Linea1.", msg)

    def test_ca_tag_03_create_tag_keeps_matching_name(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag, msg = app.create_tag(
                name="SiteA.Linea1.PI_01", unit="Pa", variable="Pressure"
            )
            self.assertIsNotNone(tag, msg)
            self.assertEqual(tag.name, "SiteA.Linea1.PI_01")
            self.assertEqual(tag.display_name, "PI_01")

    def test_ca_tag_04_create_tag_rejects_foreign_site(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag, msg = app.create_tag(
                name="SiteB.Linea2.FI_01", unit="m3/h", variable="VolumetricFlow"
            )
            self.assertIsNone(tag)
            self.assertIn("mismatch", msg.lower())

    def test_ca_tag_05_field_tag_stamps_owner_node(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag, msg = app.create_tag(
                name="TI_01",
                unit="C",
                variable="Temperature",
                opcua_address="opc.tcp://localhost:4840",
                node_namespace="ns=2;s=TI_01",
            )
            self.assertIsNotNone(tag, msg)
            self.assertEqual(tag.owner_node, NODE_ID)
            self.assertEqual(tag.area, AREA)

    def test_ca_tag_06_display_name_respected_or_base(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tagged, _ = app.create_tag(
                name="DI_01",
                unit="kg/m3",
                variable="Density",
                display_name="Densidad entrada",
            )
            self.assertIsNotNone(tagged)
            self.assertEqual(tagged.display_name, "Densidad entrada")
            defaulted, _ = app.create_tag(name="DI_02", unit="kg/m3", variable="Density")
            self.assertIsNotNone(defaulted)
            self.assertEqual(defaulted.display_name, "DI_02")

    def test_ca_tag_07_skip_validation_allows_internal_four_part_name(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag, msg = app.create_tag(
                name="Test.Linea1.LDS.leak",
                unit="adim",
                variable="Adimentional",
                skip_validation=True,
            )
            self.assertIsNotNone(tag, msg)
            self.assertEqual(tag.name, "Test.Linea1.LDS.leak")
            self.assertEqual(tag.area, AREA)
            self.assertEqual(tag.owner_node, NODE_ID)

    def test_env_skip_disables_qualification(self):
        env = dict(self.env)
        env["AUTOMATION_SKIP_TAG_VALIDATION"] = "true"
        with patch.dict(os.environ, env, clear=False):
            self.assertTrue(tag_name_validation_skipped())
            app = self._app()
            tag, msg = app.create_tag(name="FI_RAW", unit="m3/hr", variable="VolumetricFlow")
            self.assertIsNotNone(tag, msg)
            self.assertEqual(tag.name, "FI_RAW")


class TestNodeScopeStillValid(unittest.TestCase):
    def test_scope_from_env_matches_fixture(self):
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": NODE_ID,
            "AUTOMATION_AREA": AREA,
            "AUTOMATION_SITE": SITE,
        }
        scope = NodeScope.from_env(env)
        self.assertTrue(scope.is_valid)
        self.assertEqual(scope.site, SITE)
        self.assertEqual(scope.area, AREA)
