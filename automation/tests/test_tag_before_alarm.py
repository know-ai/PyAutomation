# -*- coding: utf-8 -*-
"""Tag-before-alarm invariant (boot noise / SAF QUALITY cascade)."""
from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.utils.rate_limited_log import clear_rate_limited_log_state


class TestRateLimitedLog(unittest.TestCase):
    def setUp(self):
        clear_rate_limited_log_state()

    def test_emits_once_per_window(self):
        logger = logging.getLogger("pyautomation.test.rate")
        with self.assertLogs(logger, level="WARNING") as captured:
            from automation.utils.rate_limited_log import warning_once

            self.assertTrue(warning_once(logger, "k1", "hello %s", "a"))
            self.assertFalse(warning_once(logger, "k1", "hello %s", "b"))
        self.assertEqual(len(captured.records), 1)


class TestEnsureNamedTagInHistorian(unittest.TestCase):
    def test_missing_cvt_returns_false(self):
        app = MagicMock()
        app.cvt.get_tag_by_name.return_value = None
        app.is_db_connected.return_value = True
        with patch("automation.PyAutomation", return_value=app):
            from automation.catalog.runtime_tag import ensure_named_tag_in_historian

            self.assertFalse(ensure_named_tag_in_historian("Linea1.SYS.QUALITY.X"))

    def test_delegates_to_ensure_when_connected(self):
        tag = SimpleNamespace(name="Linea1.SYS.QUALITY.X")
        app = MagicMock()
        app.cvt.get_tag_by_name.return_value = tag
        app.is_db_connected.return_value = True
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.catalog.runtime_tag.ensure_tag_historian_catalog",
            return_value=True,
        ) as ensure:
            from automation.catalog.runtime_tag import ensure_named_tag_in_historian

            self.assertTrue(ensure_named_tag_in_historian("Linea1.SYS.QUALITY.X"))
        ensure.assert_called_once()


class TestEnsureAlarmCatalogRequiresTag(unittest.TestCase):
    def setUp(self):
        clear_rate_limited_log_state()

    def test_defers_when_historian_tag_missing(self):
        from automation.persistence import remote as remote_mod

        item = {
            "name": "Linea1.ALM.QUALITY.Supe.Linea1.TI_02",
            "area": "Linea1",
            "tag": "Linea1.SYS.QUALITY.Supe.Linea1.TI_02",
            "trigger_type": "BOOL",
            "trigger_value": True,
            "identifier": "abcd",
            "description": "q",
        }
        with patch(
            "automation.dbmodels.alarms.Alarms.read_by_name",
            return_value=None,
        ), patch(
            "automation.persistence.remote._alarm_catalog_fields",
            return_value={
                "identifier": "abcd",
                "name": item["name"],
                "tag": item["tag"],
                "trigger_type": "BOOL",
                "trigger_value": True,
                "description": "q",
                "area": "Linea1",
            },
        ), patch(
            "automation.catalog.runtime_tag.ensure_named_tag_in_historian",
            return_value=False,
        ) as ensure_tag, patch(
            "automation.dbmodels.alarms.Alarms.create",
        ) as create:
            result = remote_mod._ensure_alarm_catalog(item)

        self.assertIsNone(result)
        ensure_tag.assert_called_once()
        create.assert_not_called()

    def test_creates_after_historian_tag_ok(self):
        from automation.persistence import remote as remote_mod

        item = {
            "name": "Linea1.ALM.QUALITY.Supe.Linea1.TI_02",
            "area": "Linea1",
            "tag": "Linea1.SYS.QUALITY.Supe.Linea1.TI_02",
            "trigger_type": "BOOL",
            "trigger_value": True,
            "identifier": "abcd",
            "description": "q",
        }
        created = SimpleNamespace(id=1, name=item["name"])
        with patch(
            "automation.dbmodels.alarms.Alarms.read_by_name",
            side_effect=[None, created],
        ), patch(
            "automation.persistence.remote._alarm_catalog_fields",
            return_value={
                "identifier": "abcd",
                "name": item["name"],
                "tag": item["tag"],
                "trigger_type": "BOOL",
                "trigger_value": True,
                "description": "q",
                "area": "Linea1",
            },
        ), patch(
            "automation.catalog.runtime_tag.ensure_named_tag_in_historian",
            return_value=True,
        ), patch(
            "automation.dbmodels.alarms.Alarms.create",
            return_value=created,
        ) as create:
            result = remote_mod._ensure_alarm_catalog(item)

        self.assertIs(result, created)
        create.assert_called_once()


class TestQualityAlarmDefersWithoutHistorian(unittest.TestCase):
    def setUp(self):
        clear_rate_limited_log_state()

    def test_skips_create_alarm_when_historian_missing(self):
        from automation.utils import quality_alarms as qa

        tag = SimpleNamespace(name="Linea1.SYS.QUALITY.X", id="t1")
        app = MagicMock()
        app.cvt.get_tag_by_name.return_value = tag
        app.is_db_connected.return_value = True
        app.alarm_manager.get_alarm_by_name.return_value = None

        with patch(
            "automation.catalog.runtime_tag.ensure_tag_historian_catalog",
            return_value=False,
        ):
            qa._ensure_bool_alarm(
                app,
                tag_name=tag.name,
                alarm_name="Linea1.ALM.QUALITY.X",
                tag_description="d",
                alarm_description="d",
                display_name="d",
            )

        app.create_alarm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
