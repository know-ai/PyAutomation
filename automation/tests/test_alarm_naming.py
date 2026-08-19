# -*- coding: utf-8 -*-
"""CA-ALM-01 … CA-ALM-07: HMI user-alarm name qualification (multi-edge)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ..alarm_naming import AlarmNameError, alarm_name_validation_skipped, qualify_user_alarm_name
from ..node_scope import NodeScope


SITE = "SiteA"
AREA = "Linea1"
NODE_ID = "edge-linea1"


class TestQualifyUserAlarmName(unittest.TestCase):
    def test_ca_alm_01_bare_name_is_prefixed(self):
        qualified = qualify_user_alarm_name("HighPressure", SITE, AREA)
        self.assertEqual(qualified.name, "alarm.SiteA.Linea1.HighPressure")
        self.assertEqual(qualified.base_name, "HighPressure")

    def test_ca_alm_02_two_parts_are_rejected(self):
        with self.assertRaises(AlarmNameError) as ctx:
            qualify_user_alarm_name("Linea1.HighPressure", SITE, AREA)
        self.assertIn("alarm.SiteA.Linea1.HighPressure", str(ctx.exception))

    def test_ca_alm_03_matching_four_parts_kept(self):
        qualified = qualify_user_alarm_name("alarm.SiteA.Linea1.HighPressure", SITE, AREA)
        self.assertEqual(qualified.name, "alarm.SiteA.Linea1.HighPressure")
        self.assertEqual(qualified.base_name, "HighPressure")

    def test_ca_alm_04_foreign_four_parts_rejected(self):
        with self.assertRaises(AlarmNameError) as ctx:
            qualify_user_alarm_name("alarm.SiteB.Linea2.HighPressure", SITE, AREA)
        self.assertIn("Site/Area mismatch", str(ctx.exception))
        self.assertIn("alarm.SiteA.Linea1.HighPressure", str(ctx.exception))

    def test_ca_alm_area_only_mismatch(self):
        with self.assertRaises(AlarmNameError) as ctx:
            qualify_user_alarm_name("alarm.SiteA.Linea2.HighPressure", SITE, AREA)
        self.assertIn("Area mismatch", str(ctx.exception))

    def test_more_than_four_parts_reserved(self):
        with self.assertRaises(AlarmNameError) as ctx:
            qualify_user_alarm_name("alarm.Test.Linea1.LDS.leak", SITE, AREA)
        self.assertIn("reserved", str(ctx.exception).lower())

    def test_missing_scope_leaves_name_unchanged(self):
        qualified = qualify_user_alarm_name("HighPressure", None, AREA)
        self.assertEqual(qualified.name, "HighPressure")


class TestCreateAlarmQualification(unittest.TestCase):
    def setUp(self):
        self.env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": NODE_ID,
            "AUTOMATION_AREA": AREA,
            "AUTOMATION_SITE": SITE,
            "AUTOMATION_SKIP_ALARM_VALIDATION": "",
            "AUTOMATION_SKIP_TAG_VALIDATION": "",
        }

    def _app(self):
        from .. import PyAutomation

        app = PyAutomation()
        app._refresh_node_scope()
        return app

    def _local_tag(self, app, name: str):
        tag, msg = app.create_tag(name=name, unit="Pa", variable="Pressure")
        self.assertIsNotNone(tag, msg)
        return tag

    def test_ca_alm_01_create_alarm_qualifies_and_stamps_owner(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_01")
            alarm, msg = app.create_alarm(name="HighPressure", tag=tag.name)
            self.assertIsNotNone(alarm, msg)
            self.assertEqual(alarm.name, "alarm.SiteA.Linea1.HighPressure")
            self.assertEqual(alarm.display_name, "HighPressure")
            self.assertEqual(alarm.area, AREA)
            self.assertEqual(alarm.owner_node, NODE_ID)

    def test_ca_alm_02_create_alarm_rejects_two_parts(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_02")
            alarm, msg = app.create_alarm(name="Linea1.HighPressure", tag=tag.name)
            self.assertIsNone(alarm)
            self.assertIn("alarm.SiteA.Linea1.HighPressure", msg)

    def test_ca_alm_03_create_alarm_keeps_matching_name(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_03")
            alarm, msg = app.create_alarm(
                name="alarm.SiteA.Linea1.HighPressureKeep",
                tag=tag.name,
            )
            self.assertIsNotNone(alarm, msg)
            self.assertEqual(alarm.name, "alarm.SiteA.Linea1.HighPressureKeep")
            self.assertEqual(alarm.display_name, "HighPressureKeep")

    def test_ca_alm_04_create_alarm_rejects_foreign_site(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_04")
            alarm, msg = app.create_alarm(
                name="alarm.SiteB.Linea2.HighPressure",
                tag=tag.name,
            )
            self.assertIsNone(alarm)
            self.assertIn("mismatch", msg.lower())

    def test_ca_alm_05_foreign_tag_area_rejected(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_05")
            tag.area = "Linea2"
            alarm, msg = app.create_alarm(name="HighPressureForeignTag", tag=tag.name)
            self.assertIsNone(alarm)
            self.assertIn("belongs to area", msg)

    def test_ca_alm_06_display_name_respected_or_base(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_06A")
            custom, msg = app.create_alarm(
                name="HighPressureCustom",
                tag=tag.name,
                display_name="Alta presión",
            )
            self.assertIsNotNone(custom, msg)
            self.assertEqual(custom.display_name, "Alta presión")
            tag2 = self._local_tag(app, "PT_ALM_06B")
            defaulted, msg = app.create_alarm(name="HighPressureDefault", tag=tag2.name)
            self.assertIsNotNone(defaulted, msg)
            self.assertEqual(defaulted.display_name, "HighPressureDefault")

    def test_ca_alm_07_skip_validation_allows_internal_name(self):
        with patch.dict(os.environ, self.env, clear=False):
            app = self._app()
            leak_tag, msg = app.create_tag(
                name="Test.Linea1.LDS.leak",
                unit="adim",
                variable="Adimentional",
                skip_validation=True,
            )
            self.assertIsNotNone(leak_tag, msg)
            alarm, msg = app.create_alarm_internal(
                name="alarm.Test.Linea1.LDS.leak",
                tag=leak_tag.name,
            )
            self.assertIsNotNone(alarm, msg)
            self.assertEqual(alarm.name, "alarm.Test.Linea1.LDS.leak")
            self.assertEqual(alarm.area, AREA)
            self.assertEqual(alarm.owner_node, NODE_ID)

    def test_env_skip_disables_qualification(self):
        env = dict(self.env)
        env["AUTOMATION_SKIP_ALARM_VALIDATION"] = "true"
        with patch.dict(os.environ, env, clear=False):
            self.assertTrue(alarm_name_validation_skipped())
            app = self._app()
            tag = self._local_tag(app, "PT_ALM_SKIP")
            alarm, msg = app.create_alarm(name="ALM_RAW", tag=tag.name)
            self.assertIsNotNone(alarm, msg)
            self.assertEqual(alarm.name, "ALM_RAW")


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
