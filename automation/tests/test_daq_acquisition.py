# -*- coding: utf-8 -*-
"""P0 DAQ: light OPC reads, bounded wait, never silent-empty, never browse dump."""
from __future__ import annotations

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.signal_conditioning.quality import BAD
from automation.state_machine import DAQ, StateMachineCore
from automation.tags.tag import Tag


def _field_tag() -> Tag:
    return Tag(
        name="FI_02",
        unit="adim",
        data_type="float",
        variable="Adimentional",
        id="fi02",
        node_namespace="ns=2;s=FI_02",
        scan_time=1000,
        opcua_address="opc.tcp://plc:4840",
    )


def _daq(tag: Tag, manager) -> DAQ:
    daq = object.__new__(DAQ)
    daq.opcua_client_manager = manager
    daq.cvt = MagicMock()
    daq.das = SimpleNamespace(buffer={})
    daq.get_subscribed_tags = lambda: {tag.name: SimpleNamespace(tag=tag)}
    return daq


class TestDaqAcquisition(unittest.TestCase):
    def test_daq_does_not_call_get_node_attributes(self):
        tag = _field_tag()
        manager = MagicMock()
        manager.get_node_data_value_by_opcua_address.return_value = None
        manager.get_node_attributes.side_effect = AssertionError("DAQ must not browse")
        daq = _daq(tag, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch.object(
            StateMachineCore, "while_running", return_value=None
        ):
            daq.while_running()
        manager.get_node_attributes.assert_not_called()
        manager.get_node_data_value_by_opcua_address.assert_called()
        kwargs = daq.cvt.set_value.call_args.kwargs
        self.assertEqual(kwargs.get("quality"), BAD)

    def test_empty_read_sets_bad_and_continues(self):
        tag = _field_tag()
        manager = MagicMock()
        manager.get_node_data_value_by_opcua_address.return_value = None
        daq = _daq(tag, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch.object(
            StateMachineCore, "while_running", return_value=None
        ):
            daq.while_running()
        daq.cvt.set_value.assert_called()
        self.assertEqual(daq.cvt.set_value.call_args.kwargs.get("quality"), BAD)

    def test_bounded_opc_read_does_not_hang_cycle(self):
        from automation.opcua.models import Client

        client = object.__new__(Client)
        client.name = "PLC80"
        client._io_lock = threading.Lock()
        client._io_pool = ThreadPoolExecutor(max_workers=1)
        client.is_connected = lambda: True

        def hang(_namespace):
            time.sleep(2.0)
            return "late"

        client.get_node_data_value = hang
        try:
            started = time.monotonic()
            result = client.read_data_value_bounded("ns=2;s=FI_02", timeout_s=0.2)
            elapsed = time.monotonic() - started
            self.assertIsNone(result)
            self.assertLess(elapsed, 1.0)
        finally:
            client._io_pool.shutdown(wait=False, cancel_futures=True)

    def test_contended_lock_does_not_pretend_success(self):
        from automation.opcua.models import Client

        client = object.__new__(Client)
        client.name = "PLC80"
        client._io_lock = threading.Lock()
        client._io_pool = ThreadPoolExecutor(max_workers=1)
        client.is_connected = lambda: True
        held = client._io_lock.acquire()
        self.assertTrue(held)

        def would_read(_namespace):
            raise AssertionError("must not run while lock is held")

        client.get_node_data_value = would_read
        try:
            started = time.monotonic()
            result = client.read_data_value_bounded("ns=2;s=FI_02", timeout_s=0.2)
            elapsed = time.monotonic() - started
            self.assertIsNone(result)
            self.assertLess(elapsed, 1.0)
        finally:
            client._io_lock.release()
            client._io_pool.shutdown(wait=False, cancel_futures=True)
