# -*- coding: utf-8 -*-
"""Per-machine raw vs filtered subscription preference."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.models import ProcessType
from automation.signal_conditioning.filtered_tags import (
    filtered_tag_name,
    resolve_bind_tag,
    subscription_pair_names,
)
from automation.state_machine import StateMachineCore
from automation.tags.tag import Tag


def _tag(name: str, tag_id: str, *, filter_enabled: bool = False) -> Tag:
    tag = Tag(
        name=name,
        unit="Pa",
        variable="Pressure",
        data_type="float",
        id=tag_id,
    )
    tag.filter_enabled = filter_enabled
    return tag


def _bind_machine_helpers(machine):
    machine.get_subscribed_tags = StateMachineCore.get_subscribed_tags.__get__(
        machine, StateMachineCore
    )
    machine.get_read_only_process_type_variables = (
        StateMachineCore.get_read_only_process_type_variables.__get__(
            machine, StateMachineCore
        )
    )
    machine.get_subscribed_field_tag_names = (
        StateMachineCore.get_subscribed_field_tag_names.__get__(
            machine, StateMachineCore
        )
    )
    machine.get_available_field_tags = StateMachineCore.get_available_field_tags.__get__(
        machine, StateMachineCore
    )
    machine._wavelet_source_tag = StateMachineCore._wavelet_source_tag.__get__(
        machine, StateMachineCore
    )
    machine._find_subscribed_process_type = (
        StateMachineCore._find_subscribed_process_type.__get__(
            machine, StateMachineCore
        )
    )
    machine._process_type_attr_name = StateMachineCore._process_type_attr_name.__get__(
        machine, StateMachineCore
    )
    machine.get_signal_mode_for_tag = StateMachineCore.get_signal_mode_for_tag.__get__(
        machine, StateMachineCore
    )
    machine.set_signal_mode = StateMachineCore.set_signal_mode.__get__(
        machine, StateMachineCore
    )
    machine._register_wavelet_tag = StateMachineCore._register_wavelet_tag.__get__(
        machine, StateMachineCore
    )
    machine.restart_buffer = MagicMock()
    machine.attach = MagicMock()
    machine.get_sample_interval = MagicMock(return_value=1.0)
    machine.get_interval = MagicMock(return_value=1.0)


class TestResolveBindTag(unittest.TestCase):
    def test_filtered_default_when_filter_on(self):
        source = SimpleNamespace(name="PI_02", filter_enabled=True)
        derived = SimpleNamespace(name="PI_02.f", filter_enabled=False)
        with patch(
            "automation.signal_conditioning.filtered_tags.ensure_filtered_tag",
            return_value=derived,
        ):
            bound = resolve_bind_tag(source, "filtered")
        self.assertIs(bound, derived)

    def test_raw_mode_keeps_source(self):
        source = SimpleNamespace(name="PI_02", filter_enabled=True)
        with patch(
            "automation.signal_conditioning.filtered_tags.ensure_filtered_tag"
        ) as ensure:
            bound = resolve_bind_tag(source, "raw")
        ensure.assert_not_called()
        self.assertIs(bound, source)

    def test_no_filter_always_source(self):
        source = SimpleNamespace(name="PI_02", filter_enabled=False)
        self.assertIs(resolve_bind_tag(source, "filtered"), source)

    def test_subscription_pair_names(self):
        self.assertEqual(subscription_pair_names("PI_02"), {"PI_02", "PI_02.f"})
        self.assertEqual(subscription_pair_names("PI_02.f"), {"PI_02", "PI_02.f"})


class TestMachineSignalMode(unittest.TestCase):
    def _machine(self):
        machine = SimpleNamespace(
            buffer_size=SimpleNamespace(value=10),
            buffer_roll_type=SimpleNamespace(value="backward"),
            machine_engine=MagicMock(),
            data={},
            signal_modes={},
            sample_overrides={},
            name=SimpleNamespace(value="NPW"),
        )
        _bind_machine_helpers(machine)
        return machine

    def test_register_defaults_to_filtered(self):
        machine = self._machine()
        source = _tag("PI_02", "s1", filter_enabled=True)
        derived = _tag("PI_02.f", "f1", filter_enabled=False)
        with patch(
            "automation.workers.wavelet_worker.get_wavelet_worker",
            return_value=MagicMock(),
        ), patch(
            "automation.signal_conditioning.filtered_tags.resolve_bind_tag",
            return_value=derived,
        ) as resolve:
            bound = machine._register_wavelet_tag(source)
        self.assertIs(bound, derived)
        self.assertEqual(machine.signal_modes["PI_02"], "filtered")
        resolve.assert_called_once()
        self.assertEqual(resolve.call_args.args[1], "filtered")

    def test_register_respects_raw_preference(self):
        machine = self._machine()
        machine.signal_modes["PI_02"] = "raw"
        source = _tag("PI_02", "s2", filter_enabled=True)
        with patch(
            "automation.workers.wavelet_worker.get_wavelet_worker",
            return_value=MagicMock(),
        ), patch(
            "automation.signal_conditioning.filtered_tags.resolve_bind_tag",
            return_value=source,
        ) as resolve:
            bound = machine._register_wavelet_tag(source)
        self.assertIs(bound, source)
        resolve.assert_called_once()
        self.assertEqual(resolve.call_args.args[1], "raw")

    def test_available_field_tags_excludes_raw_when_filtered_bound(self):
        machine = self._machine()
        source = _tag("PI_02", "s3", filter_enabled=True)
        derived = _tag("PI_02.f", "f3", filter_enabled=False)
        machine.inlet = ProcessType(tag=derived, default=0, read_only=True)
        machine.signal_modes["PI_02"] = "filtered"

        available = machine.get_available_field_tags(
            ["PI_02", "PI_03", filtered_tag_name("PI_04")]
        )
        self.assertNotIn("PI_02", available)
        self.assertNotIn("PI_02.f", available)
        self.assertIn("PI_03", available)
        self.assertNotIn("PI_04.f", available)

        # Also excludes when bound to raw
        machine.inlet.tag = source
        available_raw = machine.get_available_field_tags(["PI_02", "PI_03"])
        self.assertNotIn("PI_02", available_raw)
        self.assertIn("PI_03", available_raw)

    def test_set_signal_mode_switches_to_raw(self):
        machine = self._machine()
        source = _tag("PI_02", "s4", filter_enabled=True)
        derived = _tag("PI_02.f", "f4", filter_enabled=False)
        machine.inlet_pressure = ProcessType(tag=derived, default=0, read_only=True)
        machine.signal_modes["PI_02"] = "filtered"
        machine.sample_overrides["PI_02.f"] = 2.5

        with patch(
            "automation.signal_conditioning.filtered_tags.resolve_bind_tag",
            return_value=source,
        ), patch(
            "automation.workers.wavelet_worker.get_wavelet_worker",
            return_value=MagicMock(),
        ), patch.object(
            machine, "_wavelet_source_tag", return_value=source
        ):
            machine.set_signal_mode("PI_02", "raw")

        self.assertIs(machine.inlet_pressure.tag, source)
        self.assertEqual(machine.signal_modes["PI_02"], "raw")
        self.assertEqual(machine.sample_overrides.get("PI_02"), 2.5)
        self.assertNotIn("PI_02.f", machine.sample_overrides)
        machine.attach.assert_called()
        machine.restart_buffer.assert_called()
        machine.machine_engine.unbind_tag.assert_called()
        machine.machine_engine.bind_tag.assert_called()


if __name__ == "__main__":
    unittest.main()
