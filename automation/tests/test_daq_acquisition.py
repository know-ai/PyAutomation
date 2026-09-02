# -*- coding: utf-8 -*-
"""P0 DAQ: light OPC reads, bounded wait, never silent-empty, never browse dump."""
from __future__ import annotations

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.opcua.models import daq_bad_after_misses, daq_read_timeout_s
from automation.signal_conditioning.quality import BAD
from automation.state_machine import DAQ, StateMachineCore
from automation.tags.tag import Tag


def _field_tag(name="FI_02", namespace="ns=2;s=FI_02", address="opc.tcp://plc:4840") -> Tag:
    return Tag(
        name=name,
        unit="adim",
        data_type="float",
        variable="Adimentional",
        id=name.lower(),
        node_namespace=namespace,
        scan_time=1000,
        opcua_address=address,
    )


def _daq(tags, manager) -> DAQ:
    if not isinstance(tags, (list, tuple)):
        tags = [tags]
    daq = object.__new__(DAQ)
    daq.opcua_client_manager = manager
    daq.cvt = MagicMock()
    daq.das = SimpleNamespace(buffer={})
    daq.get_subscribed_tags = lambda: {tag.name: SimpleNamespace(tag=tag) for tag in tags}
    return daq


def _sample(value, timestamp):
    return SimpleNamespace(Value=SimpleNamespace(Value=value), SourceTimestamp=timestamp)


class TestDaqReadTimeoutEnv(unittest.TestCase):
    def test_default_is_500ms(self):
        self.assertEqual(daq_read_timeout_s({}), 0.5)

    def test_clamp(self):
        self.assertEqual(daq_read_timeout_s({"AUTOMATION_DAQ_READ_TIMEOUT_S": "0.01"}), 0.05)
        self.assertEqual(daq_read_timeout_s({"AUTOMATION_DAQ_READ_TIMEOUT_S": "9"}), 5.0)
        self.assertEqual(daq_read_timeout_s({"AUTOMATION_DAQ_READ_TIMEOUT_S": "0.8"}), 0.8)

    def test_invalid_falls_back(self):
        self.assertEqual(daq_read_timeout_s({"AUTOMATION_DAQ_READ_TIMEOUT_S": "nope"}), 0.5)

    def test_bad_after_misses_default_and_clamp(self):
        self.assertEqual(daq_bad_after_misses({}), 3)
        self.assertEqual(daq_bad_after_misses({"AUTOMATION_DAQ_BAD_AFTER_MISSES": "1"}), 1)
        self.assertEqual(daq_bad_after_misses({"AUTOMATION_DAQ_BAD_AFTER_MISSES": "99"}), 20)
        self.assertEqual(daq_bad_after_misses({"AUTOMATION_DAQ_BAD_AFTER_MISSES": "nope"}), 3)


class TestDaqAcquisition(unittest.TestCase):
    def test_daq_does_not_call_get_node_attributes(self):
        tag = _field_tag()
        manager = MagicMock()
        manager.get_node_data_values_by_opcua_address.return_value = {tag.get_node_namespace(): None}
        manager.get_node_attributes.side_effect = AssertionError("DAQ must not browse")
        daq = _daq(tag, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch(
            "automation.opcua.models.daq_bad_after_misses", return_value=1
        ), patch.object(StateMachineCore, "while_running", return_value=None):
            daq.while_running()
        manager.get_node_attributes.assert_not_called()
        manager.get_node_data_values_by_opcua_address.assert_called_once()
        manager.get_node_data_value_by_opcua_address.assert_not_called()
        kwargs = daq.cvt.set_value.call_args.kwargs
        self.assertEqual(kwargs.get("quality"), BAD)

    def test_empty_read_sets_bad_and_continues(self):
        tag = _field_tag()
        manager = MagicMock()
        manager.get_node_data_values_by_opcua_address.return_value = {tag.get_node_namespace(): None}
        daq = _daq(tag, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch(
            "automation.opcua.models.daq_bad_after_misses", return_value=1
        ), patch.object(StateMachineCore, "while_running", return_value=None):
            daq.while_running()
        daq.cvt.set_value.assert_called()
        self.assertEqual(daq.cvt.set_value.call_args.kwargs.get("quality"), BAD)

    def test_single_empty_read_does_not_mark_bad(self):
        tag = _field_tag()
        manager = MagicMock()
        manager.get_node_data_values_by_opcua_address.return_value = {tag.get_node_namespace(): None}
        daq = _daq(tag, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch(
            "automation.opcua.models.daq_bad_after_misses", return_value=3
        ), patch.object(StateMachineCore, "while_running", return_value=None):
            daq.while_running()
        daq.cvt.set_value.assert_not_called()

    def test_inflight_batch_does_not_mark_bad(self):
        tag = _field_tag()
        manager = MagicMock()
        manager.get_node_data_values_by_opcua_address.return_value = None
        daq = _daq(tag, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch.object(
            StateMachineCore, "while_running", return_value=None
        ):
            daq.while_running()
        daq.cvt.set_value.assert_not_called()

    def test_one_batch_read_for_all_tags_of_this_daq(self):
        tags = [
            _field_tag("FI_02", "ns=2;i=2"),
            _field_tag("PI_02", "ns=2;i=3"),
            _field_tag("DI_02", "ns=2;i=4"),
        ]
        manager = MagicMock()
        manager.get_node_data_values_by_opcua_address.return_value = {
            "ns=2;i=2": _sample(1.1, None),
            "ns=2;i=3": _sample(2.2, None),
            "ns=2;i=4": _sample(3.3, None),
        }
        daq = _daq(tags, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch.object(
            StateMachineCore, "while_running", return_value=None
        ):
            daq.while_running()
        manager.get_node_data_values_by_opcua_address.assert_called_once()
        kwargs = manager.get_node_data_values_by_opcua_address.call_args.kwargs
        self.assertEqual(kwargs["opcua_address"], "opc.tcp://plc:4840")
        self.assertEqual(sorted(kwargs["namespaces"]), ["ns=2;i=2", "ns=2;i=3", "ns=2;i=4"])
        self.assertEqual(daq.cvt.set_value.call_count, 3)
        manager.get_node_data_value_by_opcua_address.assert_not_called()

    def test_daq1000_and_daq500_batch_only_their_own_tags(self):
        slow = [_field_tag("FI_02", "ns=2;i=2"), _field_tag("PI_02", "ns=2;i=3")]
        fast = [_field_tag("DI_02", "ns=2;i=4")]
        manager = MagicMock()
        manager.get_node_data_values_by_opcua_address.return_value = {}
        daq_1000 = _daq(slow, manager)
        daq_500 = _daq(fast, manager)
        with patch("automation.state_machine._scope_owns_tag", return_value=True), patch.object(
            StateMachineCore, "while_running", return_value=None
        ):
            daq_1000.while_running()
            daq_500.while_running()
        calls = manager.get_node_data_values_by_opcua_address.call_args_list
        self.assertEqual(len(calls), 2)
        first = sorted(calls[0].kwargs["namespaces"])
        second = sorted(calls[1].kwargs["namespaces"])
        self.assertEqual(first, ["ns=2;i=2", "ns=2;i=3"])
        self.assertEqual(second, ["ns=2;i=4"])

    def test_bounded_opc_read_does_not_hang_cycle(self):
        from automation.opcua.models import Client

        client = object.__new__(Client)
        client.name = "PLC80"
        client._io_lock = threading.Lock()
        client._io_pool = ThreadPoolExecutor(max_workers=1)
        client.is_connected = lambda: True
        client.uaclient = None

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

    def test_inflight_timeout_applies_on_next_cycle(self):
        from automation.opcua.models import Client

        client = object.__new__(Client)
        client.name = "PLC80"
        client._io_lock = threading.Lock()
        client._io_pool = ThreadPoolExecutor(max_workers=1)
        client.is_connected = lambda: True
        client.uaclient = None

        def hang(_namespace):
            time.sleep(0.35)
            return "late"

        client.get_node_data_value = hang
        try:
            first = client.read_data_value_bounded("ns=2;s=FI_02", timeout_s=0.1)
            self.assertIsNone(first)
            time.sleep(0.4)
            second = client.read_data_value_bounded("ns=2;s=FI_02", timeout_s=0.1)
            self.assertEqual(second, "late")
        finally:
            client._io_pool.shutdown(wait=False, cancel_futures=True)

    def test_batch_read_uses_one_attribute_call(self):
        from automation.opcua.models import Client

        client = object.__new__(Client)
        client.name = "PLC80"
        client._io_lock = threading.Lock()
        client._io_pool = ThreadPoolExecutor(max_workers=1)
        client.is_connected = lambda: True
        dv_a = _sample(10, None)
        dv_b = _sample(20, None)
        client.uaclient = SimpleNamespace(get_attributes=MagicMock(return_value=[dv_a, dv_b]))
        try:
            out = client.read_data_values_bounded(["ns=2;i=2", "ns=2;i=3"], timeout_s=0.5)
        finally:
            client._io_pool.shutdown(wait=False, cancel_futures=True)
        client.uaclient.get_attributes.assert_called_once()
        self.assertEqual(out["ns=2;i=2"].Value.Value, 10)
        self.assertEqual(out["ns=2;i=3"].Value.Value, 20)

    def test_contended_lock_does_not_pretend_success(self):
        from automation.opcua.models import Client

        client = object.__new__(Client)
        client.name = "PLC80"
        client._io_lock = threading.Lock()
        client._io_pool = ThreadPoolExecutor(max_workers=1)
        client.is_connected = lambda: True
        client.uaclient = None
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


if __name__ == "__main__":
    unittest.main()
