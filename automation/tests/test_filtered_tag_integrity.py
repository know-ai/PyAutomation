# -*- coding: utf-8 -*-
"""CA-NAMING-03..05: reuse existing historian rows on unique-constraint conflicts."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from peewee import IntegrityError

from automation.dbmodels.machines import Machines
from automation.logger.datalogger import DataLogger
from automation.logger.machines import MachinesLogger


class TestDataLoggerSetTagIntegrity(unittest.TestCase):
    def test_set_tag_updates_existing_by_name(self):
        logger = DataLogger.__new__(DataLogger)
        logger.check_connectivity = lambda: True
        existing = MagicMock(id=7)
        with patch("automation.logger.datalogger.Tags") as tags, patch(
            "automation.logger.datalogger._mirror_historian_tag_row"
        ) as mirror:
            tags.get_or_none.return_value = existing
            result = logger.set_tag(
                id="id-1",
                name="Linea1.FI_02.f",
                unit="adim",
                data_type="float",
                display_name="Linea1.FI_02.f",
            )
        self.assertIs(result, existing)
        tags.create.assert_not_called()
        tags.put.assert_called_once()
        mirror.assert_called_once()

    def test_set_tag_recovers_from_integrity_error(self):
        logger = DataLogger.__new__(DataLogger)
        logger.check_connectivity = lambda: True
        logger._db = MagicMock()
        existing = MagicMock(id=9)
        lookups = {"n": 0}

        def get_or_none(*_a, **_k):
            lookups["n"] += 1
            return None if lookups["n"] <= 2 else existing

        with patch("automation.logger.datalogger.Tags") as tags, patch(
            "automation.logger.datalogger._mirror_historian_tag_row"
        ):
            tags.get_or_none.side_effect = get_or_none
            tags.create.side_effect = IntegrityError("duplicate key value violates unique constraint")
            result = logger.set_tag(
                id="id-2",
                name="Linea1.FI_02.f",
                unit="adim",
                data_type="float",
                display_name="Linea1.FI_02.f",
            )
        self.assertIs(result, existing)
        logger._db.connection.return_value.rollback.assert_called()
        tags.put.assert_called_once()

    def test_set_tag_integrity_error_does_not_raise_and_allows_next_tag(self):
        """CA-ISOLATION-03: FK/IntegrityError on one tag must not stop the batch."""
        logger = DataLogger.__new__(DataLogger)
        logger.check_connectivity = lambda: True
        logger._db = MagicMock()
        with patch("automation.logger.datalogger.Tags") as tags, patch(
            "automation.logger.datalogger._mirror_historian_tag_row"
        ):
            tags.get_or_none.return_value = None
            tags.create.side_effect = [
                IntegrityError("FOREIGN KEY constraint failed"),
                None,
            ]
            first = logger.set_tag(
                id="bad",
                name="orphan.tag",
                unit="adim",
                data_type="float",
            )
            second = logger.set_tag(
                id="good",
                name="healthy.tag",
                unit="adim",
                data_type="float",
            )
        self.assertIsNone(first)
        self.assertEqual(tags.create.call_count, 2)
        self.assertIsNone(second)


class TestMachinesBindTagIntegrity(unittest.TestCase):
    def test_bind_tag_skips_when_tag_missing(self):
        logger = MachinesLogger.__new__(MachinesLogger)
        logger.check_connectivity = lambda: True
        tag = SimpleNamespace(name="Linea1.FI_02.f")
        machine = SimpleNamespace(name=SimpleNamespace(value="M1"))
        with patch("automation.logger.machines.Tags") as tags, patch(
            "automation.logger.machines.Machines"
        ) as machines, patch("automation.logger.machines.TagsMachines") as binds:
            tags.get_or_none.return_value = None
            machines.get_or_none.return_value = MagicMock()
            result = logger.bind_tag(tag, machine, default_tag_name="PV")
        self.assertIsNone(result)
        binds.create.assert_not_called()

    def test_bind_tag_reuses_existing_row(self):
        logger = MachinesLogger.__new__(MachinesLogger)
        logger.check_connectivity = lambda: True
        tag = SimpleNamespace(name="Linea1.FI_02.f")
        machine = SimpleNamespace(name=SimpleNamespace(value="M1"))
        tag_row = MagicMock()
        machine_row = MagicMock()
        bind_row = MagicMock(default_tag_name="PV")
        with patch("automation.logger.machines.Tags") as tags, patch(
            "automation.logger.machines.Machines"
        ) as machines, patch("automation.logger.machines.TagsMachines") as binds, patch(
            "automation.catalog.mutations.persist_tagsmachines_bind"
        ):
            tags.get_or_none.return_value = tag_row
            machines.get_or_none.return_value = machine_row
            binds.get_or_none.return_value = bind_row
            logger.bind_tag(tag, machine, default_tag_name="PV")
        binds.create.assert_not_called()

    def test_bind_tag_recovers_from_integrity_error(self):
        logger = MachinesLogger.__new__(MachinesLogger)
        logger.check_connectivity = lambda: True
        logger._db = MagicMock()
        tag = SimpleNamespace(name="Linea1.FI_02.f")
        machine = SimpleNamespace(name=SimpleNamespace(value="M1"))
        tag_row = MagicMock()
        machine_row = MagicMock()
        bind_row = MagicMock(default_tag_name=None)
        with patch("automation.logger.machines.Tags") as tags, patch(
            "automation.logger.machines.Machines"
        ) as machines, patch("automation.logger.machines.TagsMachines") as binds, patch(
            "automation.catalog.mutations.persist_tagsmachines_bind"
        ):
            tags.get_or_none.return_value = tag_row
            machines.get_or_none.return_value = machine_row
            binds.get_or_none.side_effect = [None, bind_row]
            binds.create.side_effect = IntegrityError("duplicate key")
            logger.bind_tag(tag, machine)
        logger._db.connection.return_value.rollback.assert_called()
        binds.create.assert_called_once()

    def test_bind_tag_integrity_error_does_not_raise_and_allows_next_bind(self):
        """CA-ISOLATION-04: FK missing on one bind must not stop the rest."""
        logger = MachinesLogger.__new__(MachinesLogger)
        logger.check_connectivity = lambda: True
        logger._db = MagicMock()
        tag_a = SimpleNamespace(name="orphan.tag")
        tag_b = SimpleNamespace(name="healthy.tag")
        machine = SimpleNamespace(name=SimpleNamespace(value="M1"))
        with patch("automation.logger.machines.Tags") as tags, patch(
            "automation.logger.machines.Machines"
        ) as machines, patch("automation.logger.machines.TagsMachines") as binds, patch(
            "automation.catalog.mutations.persist_tagsmachines_bind"
        ):
            tags.get_or_none.return_value = MagicMock()
            machines.get_or_none.return_value = MagicMock()
            binds.get_or_none.return_value = None
            binds.create.side_effect = [
                IntegrityError("FOREIGN KEY constraint failed"),
                MagicMock(),
            ]
            first = logger.bind_tag(tag_a, machine)
            second = logger.bind_tag(tag_b, machine)
        self.assertIsNone(first)
        self.assertEqual(binds.create.call_count, 2)
        self.assertIsNone(second)

    def test_bind_tag_rejects_cross_area(self):
        """CA-CODE-01: tag.area != machine.area raises CrossAreaBindError."""
        from automation.catalog.partition import CrossAreaBindError

        logger = MachinesLogger.__new__(MachinesLogger)
        logger.check_connectivity = lambda: True
        tag = SimpleNamespace(name="Supe.Linea2.FI_02", area="Linea2")
        machine = SimpleNamespace(name=SimpleNamespace(value="DAQ-1000"), area="Linea1")
        tag_row = SimpleNamespace(area="Linea2", name="Supe.Linea2.FI_02")
        machine_row = SimpleNamespace(area="Linea1", name="DAQ-1000")
        with patch("automation.logger.machines.Tags") as tags, patch(
            "automation.logger.machines.Machines"
        ) as machines, patch("automation.logger.machines.TagsMachines") as binds:
            tags.get_or_none.return_value = tag_row
            machines.get_or_none.return_value = machine_row
            with self.assertRaises(CrossAreaBindError) as caught:
                logger.bind_tag(tag, machine, default_tag_name="inlet_flow")
        self.assertIn("does not match", str(caught.exception))
        self.assertIn("cross-area", str(caught.exception))
        binds.create.assert_not_called()


_MACHINE_CREATE_KW = dict(
    identifier="b7136118",
    name="DAQ-1000",
    interval=1,
    description="",
    classification="DAQ",
    buffer_size=10,
    buffer_roll_type="fifo",
    criticity=1,
    priority=1,
    area="Linea2",
)


class TestMachinesCreateIdentifierIdempotent(unittest.TestCase):
    def test_create_returns_existing_when_identifier_present(self):
        existing = MagicMock()
        existing.name = "DAQ-1000"
        existing.area = "Linea1"
        existing.serialize.return_value = {"identifier": "b7136118", "name": "DAQ-1000"}
        with patch.object(Machines, "get_or_none", return_value=existing):
            result = Machines.create(**_MACHINE_CREATE_KW)
        self.assertIn("already exists", result["message"])
        existing.save.assert_not_called()

    def test_create_fills_blank_area_on_existing_identifier(self):
        existing = MagicMock()
        existing.name = "DAQ-1000"
        existing.area = None
        existing.serialize.return_value = {
            "identifier": "b7136118",
            "name": "DAQ-1000",
            "area": "Linea2",
        }
        with patch.object(Machines, "get_or_none", return_value=existing):
            Machines.create(**_MACHINE_CREATE_KW)
        self.assertEqual(existing.area, "Linea2")
        existing.save.assert_called_once()

    def test_logger_create_swallows_duplicate_identifier(self):
        logger = MachinesLogger.__new__(MachinesLogger)
        logger.check_connectivity = lambda: True
        logger._db = MagicMock()
        existing = MagicMock()
        with patch("automation.logger.machines.Machines") as machines, patch(
            "automation.catalog.bootstrap.mirror_historian_row"
        ) as mirror:
            machines.create.side_effect = IntegrityError(
                'duplicate key value violates unique constraint "machines_identifier"'
            )
            machines.get_or_none.return_value = existing
            logger.create(**_MACHINE_CREATE_KW)
        logger._db.connection.return_value.rollback.assert_called()
        machines.create.assert_called_once()
        mirror.assert_called_once_with(existing)
