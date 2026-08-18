# -*- coding: utf-8 -*-
from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from ..persistence.records import PersistableRecord
from ..utils.event_scope import resolve_event_area


class FakeScope:
    enabled = True
    is_valid = True
    node_id = "edge-a"
    area = "Linea1"


class TestResolveEventArea(unittest.TestCase):
    def test_plant_wide_always_empty(self):
        tag = types.SimpleNamespace(area="Linea2")
        with patch("automation.utils.event_scope.node_area", return_value="Linea1"):
            self.assertIsNone(resolve_event_area(plant_wide=True, source=tag, area="Linea3"))

    def test_explicit_area_wins(self):
        tag = types.SimpleNamespace(area="Linea2")
        with patch("automation.utils.event_scope.node_area", return_value="Linea1"):
            self.assertEqual(resolve_event_area(area="Linea3", source=tag), "Linea3")

    def test_source_tag_then_node(self):
        tag = types.SimpleNamespace(area="Linea2")
        alarm = types.SimpleNamespace(area=None, tag=tag, catalog_payload=lambda: {"area": None})
        with patch("automation.utils.event_scope.node_area", return_value="Linea1"):
            self.assertEqual(resolve_event_area(source=(None, alarm)), "Linea2")
            self.assertEqual(resolve_event_area(), "Linea1")


class TestPersistableEventArea(unittest.TestCase):
    def test_line_event_inherits_node_area(self):
        with patch("automation.node_scope.get_node_scope", return_value=FakeScope()):
            record = PersistableRecord.event(message="Tag updated", username="op")
        self.assertEqual(record.payload()["area"], "Linea1")

    def test_plant_wide_event_has_no_area(self):
        with patch("automation.node_scope.get_node_scope", return_value=FakeScope()):
            record = PersistableRecord.event(
                message="User account created",
                username="admin",
                plant_wide=True,
            )
        self.assertIsNone(record.payload()["area"])
        self.assertEqual(record.payload()["owner_node"], "edge-a")


class TestEventsLoggerArea(unittest.TestCase):
    def test_create_forwards_area_to_remote_write(self):
        from ..logger.events import EventsLogger

        logger = EventsLogger()
        logger.is_history_logged = True
        user = MagicMock()
        user.username = "op"
        captured = {}

        def _journal(record, write, connected):
            captured["journal_area"] = record.payload().get("area")
            write()
            return MagicMock(), "ok"

        with patch.object(logger, "check_connectivity", return_value=True), patch(
            "automation.persistence.outbox.journal_then_remote",
            side_effect=_journal,
        ), patch(
            "automation.dbmodels.events.Events.create",
            return_value=(MagicMock(), "ok"),
        ) as create:
            logger.create(
                message="Machine switched",
                user=user,
                description="from run to wait",
                area="Linea1",
            )

        self.assertEqual(captured["journal_area"], "Linea1")
        self.assertEqual(create.call_args.kwargs["area"], "Linea1")

    def test_plant_wide_create_does_not_stamp_node_area(self):
        from ..logger.events import EventsLogger

        logger = EventsLogger()
        logger.is_history_logged = True
        user = MagicMock()
        user.username = "admin"
        captured = {}

        def _journal(record, write, connected):
            captured["journal_area"] = record.payload().get("area")
            write()
            return MagicMock(), "ok"

        with patch.object(logger, "check_connectivity", return_value=True), patch(
            "automation.node_scope.get_node_scope",
            return_value=FakeScope(),
        ), patch(
            "automation.persistence.outbox.journal_then_remote",
            side_effect=_journal,
        ), patch(
            "automation.dbmodels.events.Events.create",
            return_value=(MagicMock(), "ok"),
        ) as create:
            logger.create(
                message="User account created",
                user=user,
                plant_wide=True,
            )

        self.assertIsNone(captured["journal_area"])
        self.assertIsNone(create.call_args.kwargs["area"])
