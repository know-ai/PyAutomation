# -*- coding: utf-8 -*-
"""Observer lifecycle: delete_tag / unsubscribe_to detach (Operación Ciclo de Vida Perfecto)."""
from __future__ import annotations

import gc
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ..models import ProcessType
from ..state_machine import StateMachineCore
from ..tags.cvt import CVT
from ..tags.tag import MachineObserver, Tag, TagObserver
from ..utils.observer import Observer


def _tag(name: str = "P1", tag_id: str = "obs01") -> Tag:
    return Tag(
        name=name,
        unit="Pa",
        variable="Pressure",
        data_type="float",
        id=tag_id,
    )


class ProbeObserver(Observer):
    def update(self, arg=None):
        return None


class TestTagDetachAll(unittest.TestCase):
    def test_detach_all_clears_subject_and_set(self):
        tag = _tag()
        first = ProbeObserver()
        second = ProbeObserver()
        tag.attach(first)
        tag.attach(second)
        self.assertEqual(len(tag._observers), 2)
        tag.detach_all_observers()
        self.assertEqual(len(tag._observers), 0)
        self.assertIsNone(first._subject)
        self.assertIsNone(second._subject)

    def test_detach_machine_releases_only_that_machine(self):
        tag = _tag()
        machine_a = object()
        machine_b = object()
        obs_a = MachineObserver(machine_a)
        obs_b = MachineObserver(machine_b)
        tag.attach(obs_a)
        tag.attach(obs_b)
        self.assertTrue(tag.detach_machine(machine_a))
        self.assertIsNone(obs_a._subject)
        self.assertIsNone(obs_a.machine)
        self.assertIn(obs_b, tag._observers)
        self.assertIs(obs_b.machine, machine_b)
        self.assertFalse(tag.detach_machine(machine_a))


class TestDeleteTagDetachesObservers(unittest.TestCase):
    def test_delete_tag_detaches_before_pop(self):
        cvt = CVT()
        tag = _tag(tag_id="deadbeef")
        observer = ProbeObserver()
        machine = object()
        machine_obs = MachineObserver(machine)
        tag.attach(observer)
        tag.attach(machine_obs)
        cvt._tags[tag.id] = tag
        cvt._index_tag(tag)

        deleted, _ = cvt.delete_tag(id="deadbeef", user=None)
        self.assertIs(deleted, tag)
        self.assertEqual(len(tag._observers), 0)
        self.assertIsNone(observer._subject)
        self.assertIsNone(machine_obs._subject)
        self.assertIsNone(machine_obs.machine)
        self.assertIsNone(cvt.get_tag("deadbeef"))
        self.assertEqual(cvt.observer_counts()["TAG_OBSERVER_COUNT"], 0)
        self.assertEqual(cvt.observer_counts()["MACHINE_OBSERVER_COUNT"], 0)

    def test_observer_counts_sum_not_capped_by_tag_count(self):
        cvt = CVT()
        tag = _tag(tag_id="aabbccdd")
        tag.attach(ProbeObserver())
        tag.attach(MachineObserver(object()))
        cvt._tags[tag.id] = tag
        counts = cvt.observer_counts()
        self.assertEqual(counts["TAG_OBSERVER_COUNT"], 2)
        self.assertEqual(counts["MACHINE_OBSERVER_COUNT"], 1)
        self.assertGreater(counts["TAG_OBSERVER_COUNT"], len(cvt._tags))

    def test_delete_tag_allows_gc_when_no_other_roots(self):
        import weakref

        cvt = CVT()
        tag = _tag(tag_id="gcfeed")
        tag.attach(TagObserver(tag_queue=MagicMock()))
        cvt._tags[tag.id] = tag
        cvt._index_tag(tag)
        ref = weakref.ref(tag)
        cvt.delete_tag(id="gcfeed", user=None)
        del tag
        gc.collect()
        self.assertIsNone(ref())


class TestUnsubscribeDetachesMachineObserver(unittest.TestCase):
    def test_unsubscribe_to_removes_machine_observer(self):
        tag = _tag(name="FI_01", tag_id="unsub01")
        machine = SimpleNamespace(
            buffer_size=SimpleNamespace(value=10),
            buffer_roll_type=SimpleNamespace(value="backward"),
            machine_engine=MagicMock(),
            data={},
            signal_modes={},
            name=SimpleNamespace(value="m1"),
        )
        machine.flow = ProcessType(tag=tag, default=tag.value, read_only=True)
        machine.get_subscribed_tags = StateMachineCore.get_subscribed_tags.__get__(machine, StateMachineCore)
        machine.get_read_only_process_type_variables = (
            StateMachineCore.get_read_only_process_type_variables.__get__(
                machine, StateMachineCore
            )
        )
        machine._wavelet_source_tag = StateMachineCore._wavelet_source_tag.__get__(
            machine, StateMachineCore
        )
        machine._find_subscribed_process_type = (
            StateMachineCore._find_subscribed_process_type.__get__(
                machine, StateMachineCore
            )
        )
        machine._unregister_wavelet_tag = MagicMock()
        machine.restart_buffer = MagicMock()
        machine.unsubscribe_to = StateMachineCore.unsubscribe_to.__get__(machine, StateMachineCore)

        observer = MachineObserver(machine)
        tag.attach(observer)
        self.assertIn(observer, tag._observers)

        result = machine.unsubscribe_to(tag=tag)
        self.assertTrue(result)
        self.assertNotIn(observer, tag._observers)
        self.assertIsNone(observer._subject)
        self.assertIsNone(observer.machine)
        self.assertIsNone(machine.flow.tag)
        machine.machine_engine.unbind_tag.assert_called_once()
        machine.restart_buffer.assert_called_once()

    def test_unsubscribe_by_default_tag_name(self):
        tag = _tag(name="PI_01", tag_id="unsub02")
        machine = SimpleNamespace(
            buffer_size=SimpleNamespace(value=10),
            buffer_roll_type=SimpleNamespace(value="backward"),
            machine_engine=MagicMock(),
            data={},
            signal_modes={},
            name=SimpleNamespace(value="m1"),
        )
        machine.inlet_pressure = ProcessType(tag=tag, default=tag.value, read_only=True)
        machine.get_subscribed_tags = StateMachineCore.get_subscribed_tags.__get__(machine, StateMachineCore)
        machine.get_read_only_process_type_variables = (
            StateMachineCore.get_read_only_process_type_variables.__get__(
                machine, StateMachineCore
            )
        )
        machine._wavelet_source_tag = StateMachineCore._wavelet_source_tag.__get__(
            machine, StateMachineCore
        )
        machine._find_subscribed_process_type = (
            StateMachineCore._find_subscribed_process_type.__get__(
                machine, StateMachineCore
            )
        )
        machine._unregister_wavelet_tag = MagicMock()
        machine.restart_buffer = MagicMock()
        machine.unsubscribe_to = StateMachineCore.unsubscribe_to.__get__(machine, StateMachineCore)
        tag.attach(MachineObserver(machine))

        self.assertTrue(machine.unsubscribe_to(None, "inlet_pressure"))
        self.assertEqual(len(tag._observers), 0)
        self.assertIsNone(machine.inlet_pressure.tag)
