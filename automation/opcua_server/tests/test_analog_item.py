"""AnalogItem probe, single fallback audit, and the health counter."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from automation.opcua_server.analog_item.fallback import apply_analog_fallback
from automation.opcua_server.analog_item.probe import AnalogItemProbe
from automation.opcua_server.metrics import OpcUaServerMetrics


class _Node:
    def __init__(self):
        self.deleted = False

    def delete(self):
        self.deleted = True

    def delete_reference(self, *args, **kwargs):
        return None

    def add_reference(self, *args, **kwargs):
        return None


class TestAnalogItem(unittest.TestCase):
    def test_probe_false_when_flag_disabled(self):
        server = SimpleNamespace(objects=SimpleNamespace(add_variable=lambda *args: _Node()), _namespace_idx=2)
        probe = AnalogItemProbe(server)
        with patch("automation.opcua_server.analog_item.probe.analog_item_enabled", return_value=False):
            self.assertFalse(probe.probe())
        self.assertIs(probe.cached(), False)
        self.assertFalse(probe.probe())

    def test_probe_caches_stack_result(self):
        node = _Node()
        server = SimpleNamespace(objects=SimpleNamespace(add_variable=lambda *args: node), _namespace_idx=2)
        probe = AnalogItemProbe(server)
        with patch("automation.opcua_server.analog_item.probe.analog_item_enabled", return_value=True):
            with patch(
                "automation.opcua_server.analog_item.probe.AddressSpaceBuilder.swap_analog_item",
                return_value=True,
            ):
                started = __import__("time").perf_counter()
                self.assertTrue(probe.probe())
                elapsed_ms = (__import__("time").perf_counter() - started) * 1000.0
        self.assertLess(elapsed_ms, 10.0)
        self.assertTrue(node.deleted)
        self.assertIs(probe.cached(), True)

    def test_fallback_is_audited_once_and_metric_is_one(self):
        metrics = OpcUaServerMetrics()
        server = SimpleNamespace(
            builder=SimpleNamespace(analog_item_supported=None),
            metrics=metrics,
            _analog_fallback_audited=False,
            analog_item_supported=None,
        )
        with patch("automation.opcua_server.audit.capability_fallback") as audited:
            apply_analog_fallback(server, False)
            apply_analog_fallback(server, False)
        self.assertEqual(audited.call_count, 1)
        self.assertEqual(metrics.analog_item_fallbacks, 1)
        self.assertFalse(server.builder.analog_item_supported)
        payload = metrics.as_dict(ready=True, namespace_idx=2, structures={})
        self.assertEqual(payload["OPCUA_ANALOG_ITEM_FALLBACKS_TOTAL"], 1)

    def test_supported_probe_does_not_audit(self):
        metrics = OpcUaServerMetrics()
        server = SimpleNamespace(
            builder=SimpleNamespace(analog_item_supported=None),
            metrics=metrics,
            _analog_fallback_audited=False,
        )
        with patch("automation.opcua_server.audit.capability_fallback") as audited:
            apply_analog_fallback(server, True)
        self.assertEqual(audited.call_count, 0)
        self.assertEqual(metrics.analog_item_fallbacks, 0)
