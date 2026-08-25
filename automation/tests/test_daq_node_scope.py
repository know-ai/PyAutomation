# -*- coding: utf-8 -*-
"""CA-DAQ-01: one DAQ poller per (area, scan_time); names never collide across edges."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.catalog.partition import daq_machine_name
from automation.models import StringType, FloatType
from automation.state_machine import Machine


class TestDaqMachineName(unittest.TestCase):
    def test_scoped_name_includes_area(self):
        self.assertEqual(daq_machine_name(1000, "Linea1"), "Linea1.DAQ-1000")
        self.assertEqual(daq_machine_name(1000, "Linea2"), "Linea2.DAQ-1000")
        self.assertNotEqual(daq_machine_name(1000, "Linea1"), daq_machine_name(1000, "Linea2"))

    def test_same_area_different_scan_times(self):
        self.assertEqual(daq_machine_name(200, "Linea1"), "Linea1.DAQ-200")
        self.assertEqual(daq_machine_name(1000, "Linea1"), "Linea1.DAQ-1000")

    def test_single_edge_keeps_legacy_name(self):
        self.assertEqual(daq_machine_name(1000, None), "DAQ-1000")
        self.assertEqual(daq_machine_name(1000, ""), "DAQ-1000")

    def test_float_interval_roundtrip_does_not_truncate_ms(self):
        reconstructed = (333 / 1000) * 1000
        self.assertEqual(daq_machine_name(reconstructed, "Linea1"), "Linea1.DAQ-333")
        self.assertEqual(daq_machine_name(333.4, "Linea2"), "Linea2.DAQ-333")


class TestAppendMachineScopesDaq(unittest.TestCase):
    def test_append_rewrites_daq_name_with_node_area(self):
        host = Machine.__new__(Machine)
        host.machine_manager = MagicMock()
        host.machines_engine = MagicMock()
        host.machines_engine.get_db.return_value = None
        host.create_tag_internal_process_type = MagicMock()
        daq = SimpleNamespace(
            name=StringType("DAQ"),
            identifier=StringType("id-daq"),
            description=StringType("acq"),
            classification=StringType("Data Acquisition System"),
            buffer_size=SimpleNamespace(value=10),
            buffer_roll_type=SimpleNamespace(value="backward"),
            criticity=SimpleNamespace(value=1),
            priority=SimpleNamespace(value=1),
            set_interval=MagicMock(),
        )
        scope = SimpleNamespace(area="Linea2", enabled=True, is_valid=True)
        with patch("automation.node_scope.get_node_scope", return_value=scope), patch(
            "automation.PyAutomation"
        ) as app_cls:
            app_cls.return_value.is_db_connected.return_value = False
            host.append_machine(daq, interval=FloatType(1.0), mode="async")
        self.assertEqual(daq.name.value, "Linea2.DAQ-1000")
        self.assertEqual(daq.area, "Linea2")
        host.machine_manager.append_machine.assert_called_once()
