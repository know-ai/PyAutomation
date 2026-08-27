# -*- coding: utf-8 -*-
"""CA-SM-01 … CA-SM-05: temporal decoupling of sampling vs execution."""
from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from ..models import ProcessType
from ..state_machine import StateMachineCore
from ..state_machine_timing import (
    MachineConfigError,
    compute_sample_buffer_maxlen,
    samples_per_execution,
    validate_temporal_config,
)
from ..tags.tag import Tag
from ..workers.state_machine import _machine_wants_sample_scheduler


def _pressure_tag(name: str = "PI_01", scan_time: int | None = 200) -> Tag:
    return Tag(
        name=name,
        unit="Pa",
        variable="Pressure",
        data_type="float",
        scan_time=scan_time,
        id=name.lower(),
    )


class ProbeMachine(StateMachineCore):
    def __init__(self, interval: float = 1.0, tag: Tag | None = None):
        super().__init__(name="probe", interval=interval, buffer_size=40)
        self._input = ProcessType(tag=tag or _pressure_tag(), default=1.0, read_only=True)
        self._input.value = 1.0
        self._input.data_timestamp = datetime.now(timezone.utc)
        self.restart_buffer()


class TestTemporalValidation(unittest.TestCase):
    def test_ca_sm_02_rejects_sample_faster_than_scan(self):
        tag = _pressure_tag(scan_time=500)
        machine = ProbeMachine(interval=1.0, tag=tag)
        with self.assertRaises(MachineConfigError) as ctx:
            validate_temporal_config(
                machine,
                new_execution=1.0,
                new_sample=0.2,
                overrides={},
            )
        self.assertIn("cannot be less than its acquisition scan_time", str(ctx.exception))
        self.assertIn("0.2s", str(ctx.exception))

    def test_rejects_execution_faster_than_sample(self):
        machine = ProbeMachine(interval=1.0)
        with self.assertRaises(MachineConfigError) as ctx:
            validate_temporal_config(
                machine,
                new_execution=0.1,
                new_sample=0.2,
                overrides={},
            )
        self.assertEqual(
            str(ctx.exception),
            "execution_interval cannot be less than sample_interval",
        )

    def test_legacy_null_sample_skips_scan_rule(self):
        tag = _pressure_tag(scan_time=500)
        machine = ProbeMachine(interval=1.0, tag=tag)
        self.assertTrue(
            validate_temporal_config(
                machine,
                new_execution=1.0,
                new_sample=None,
                overrides={},
            )
        )


class TestSamplePush(unittest.TestCase):
    def test_ca_sm_01_five_points_per_execution_window(self):
        tag = _pressure_tag(scan_time=200)
        machine = ProbeMachine(interval=1.0, tag=tag)
        machine._sample_interval = 0.2
        machine.restart_buffer()
        last = {}
        for i in range(5):
            machine._input.value = float(i)
            machine._sample_once(tick_start=i * 0.2, last_sample_time=last)
        buf = machine.data[tag.name]
        self.assertEqual(len(buf), 5)
        self.assertEqual(samples_per_execution(1.0, 0.2), 5)

    def test_skips_none_value(self):
        tag = _pressure_tag()
        machine = ProbeMachine(tag=tag)
        machine._sample_interval = 0.2
        machine.restart_buffer()
        machine._input.value = None
        last = {}
        machine._sample_once(0.0, last)
        self.assertEqual(len(machine.data[tag.name]), 0)

    def test_buffer_cap_is_at_least_two_windows(self):
        self.assertGreaterEqual(compute_sample_buffer_maxlen(1.0, 0.2, 10), 10)
        self.assertEqual(compute_sample_buffer_maxlen(1.0, 0.2, 3), 10)

    def test_ca_sm_04_legacy_is_noop_and_no_sampler(self):
        machine = ProbeMachine()
        self.assertIsNone(machine.get_sample_interval())
        self.assertIsNone(machine._legacy_sample_and_execute())
        self.assertFalse(_machine_wants_sample_scheduler(machine))
        last = {}
        before = {name: len(buf) for name, buf in machine.data.items()}
        machine._legacy_sample_and_execute()
        after = {name: len(buf) for name, buf in machine.data.items()}
        self.assertEqual(before, after)


class TestSampleLatency(unittest.TestCase):
    def test_sample_100_tags_under_1ms(self):
        machine = StateMachineCore(name="bulk", interval=1.0, buffer_size=20)
        tags = []
        for i in range(100):
            tag = _pressure_tag(name=f"T{i:03d}", scan_time=1)
            pt = ProcessType(tag=tag, default=1.0, read_only=True)
            pt.value = 1.0
            pt.data_timestamp = datetime.now(timezone.utc)
            setattr(machine, f"in_{i}", pt)
            tags.append(tag)
        machine._sample_interval = 0.001
        machine.restart_buffer()
        last = {}
        t0 = time.perf_counter()
        machine._sample_once(0.0, last)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(len(machine.data), 100)
        self.assertLess(elapsed_ms, 1.0)


class TestSampleSchedThreadStopFlag(unittest.TestCase):
    def test_does_not_overwrite_thread_stop_method(self):
        from ..workers.state_machine import SampleSchedThread

        machine = ProbeMachine(interval=2.0)
        machine._sample_interval = 1.0
        sampler = SampleSchedThread(machine)
        self.assertTrue(
            callable(sampler._stop),
            "SampleSchedThread must not replace Thread._stop with a bool",
        )
        self.assertFalse(sampler._stop_requested)
        sampler.stop()
        self.assertTrue(sampler._stop_requested)
        self.assertTrue(callable(sampler._stop))


class TestHotSampleReconfigKeepsBuffer(unittest.TestCase):
    def test_override_change_does_not_clear_existing_samples(self):
        tag = _pressure_tag(name="DI_02", scan_time=200)
        machine = ProbeMachine(interval=2.0, tag=tag)
        machine.set_sample_interval(1.0)
        last = {}
        for i in range(3):
            machine._input.value = float(i)
            machine._sample_once(tick_start=float(i + 1), last_sample_time=last)
        buf = machine.data[tag.name]
        self.assertEqual(len(buf), 3)
        machine.set_sample_overrides({tag.name: 2.0})
        self.assertEqual(len(machine.data[tag.name]), 3)
        machine._input.value = 9.0
        machine._sample_once(tick_start=5.0, last_sample_time=last)
        self.assertEqual(len(machine.data[tag.name]), 4)


class TestEnterWaitingClearsBuffer(unittest.TestCase):
    def test_on_enter_waiting_drops_samples_and_resets_clock(self):
        tag = _pressure_tag(name="FI_02", scan_time=200)
        machine = ProbeMachine(interval=4.0, tag=tag)
        machine.set_sample_interval(1.0)
        last = {}
        for i in range(8):
            machine._input.value = float(i)
            machine._sample_once(tick_start=float(i + 1), last_sample_time=last)
        self.assertEqual(len(machine.data[tag.name]), 8)
        machine.on_enter_waiting()
        buf = machine.data.get(tag.name)
        self.assertIsNotNone(buf)
        self.assertEqual(len(buf), 0)
        self.assertTrue(machine._sample_clock_reset)


class TestAsyncStateMachineDrop(unittest.TestCase):
    def test_drop_removes_from_registry(self):
        from ..workers.state_machine import AsyncStateMachineWorker

        machine = object()
        worker = AsyncStateMachineWorker()
        worker.add_machine(machine)

        class _Sched:
            def __init__(self, bound):
                self.machine = bound
                self.stopped = False

            def stop(self):
                self.stopped = True

        sched = _Sched(machine)
        worker._schedulers.append(sched)
        worker.drop(machine)
        self.assertNotIn(machine, worker._machines)
        self.assertEqual(worker._schedulers, [])
        self.assertTrue(sched.stopped)
        self.assertEqual(len(worker._machines), 0)


if __name__ == "__main__":
    unittest.main()
