# -*- coding: utf-8 -*-
"""CA-NAMING-03..05: reuse existing historian rows on unique-constraint conflicts."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from peewee import IntegrityError

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
