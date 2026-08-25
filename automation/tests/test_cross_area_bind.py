# -*- coding: utf-8 -*-
"""CA-CODE-01..05: refuse and filter cross-area tagsmachines binds."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.catalog.partition import (
    CrossAreaBindError,
    areas_compatible,
    ensure_same_partition,
)
from automation.state_machine import StateMachineCore


class TestPartitionGuard(unittest.TestCase):
    def test_ensure_same_partition_raises(self):
        with self.assertRaises(CrossAreaBindError) as caught:
            ensure_same_partition("Linea2", "Linea1", tag_name="L2.FI", machine_name="DAQ-1000")
        self.assertIn("Linea2", str(caught.exception))
        self.assertIn("Linea1", str(caught.exception))

    def test_empty_areas_compatible_single_edge(self):
        self.assertTrue(areas_compatible(None, None))
        self.assertTrue(areas_compatible("", ""))
        self.assertFalse(areas_compatible("Linea1", None))
        self.assertFalse(areas_compatible("Linea1", "Linea2"))


class TestSubscribeToCrossArea(unittest.TestCase):
    def test_subscribe_to_rejects_before_attach(self):
        """CA-CODE-02: subscribe_to returns False; API maps that to HTTP 400."""
        machine = SimpleNamespace(
            area="Linea1",
            name=SimpleNamespace(value="DAQ-1000"),
        )
        machine._register_wavelet_tag = lambda tag: tag
        machine.process_type_exists = lambda name: True
        machine.get_not_subscribed_tags = lambda: ["inlet_flow"]
        machine.inlet_flow = SimpleNamespace(tag=None)
        machine.attach = MagicMock()
        machine.restart_buffer = MagicMock()
        machine.machine_engine = MagicMock()
        machine._ensure_bind_partition = StateMachineCore._ensure_bind_partition.__get__(
            machine, StateMachineCore
        )
        machine.subscribe_to = StateMachineCore.subscribe_to.__get__(machine, StateMachineCore)
        tag = SimpleNamespace(name="Supe.Linea2.FI_02", area="Linea2")

        ok, message = machine.subscribe_to(tag, default_tag_name="inlet_flow")

        self.assertFalse(ok)
        self.assertIn("does not match", message)
        self.assertIn("cross-area", message)
        machine.attach.assert_not_called()
        machine.machine_engine.bind_tag.assert_not_called()

    def test_subscribe_api_returns_400_on_area_mismatch(self):
        """CA-CODE-02: POST /machines/<name>/subscribe → 400 with area message."""
        from automation.modules.machines.resources import machines as machines_mod

        resource = machines_mod.MachineSubscribeResource()
        machine = MagicMock()
        machine.subscribe_to.return_value = (
            False,
            "Tag area 'Linea2' does not match machine area 'Linea1'. "
            "Cannot bind Supe.Linea2.FI_02 to DAQ-1000 cross-area.",
        )
        fake_request = SimpleNamespace(
            is_json=True,
            json={"field_tag": "Supe.Linea2.FI_02", "internal_tag": "inlet_flow"},
        )
        fn = machines_mod.MachineSubscribeResource.post
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        with patch.object(machines_mod, "request", fake_request), patch.object(
            machines_mod, "_machine_scope_error", return_value=None
        ), patch.object(machines_mod, "app") as app:
            app.get_machine.return_value = machine
            app.cvt._cvt.get_tag_by_name.return_value = MagicMock()
            body, status = fn(resource, "DAQ-1000")
        self.assertEqual(status, 400)
        self.assertIn("does not match", body["message"])
        self.assertIn("cross-area", body["message"])


if __name__ == "__main__":
    unittest.main()
