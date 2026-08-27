# -*- coding: utf-8 -*-
"""automation/workers/state.py

This module implements the State Machine Worker, managing the execution of state machines.
"""
import heapq
import logging
import time
from collections import deque
from datetime import datetime, timezone
from threading import Thread
from .worker import BaseWorker


def stamp_machine_cycle(machine):
    """Stamp one UTC millisecond instant onto the machine before ``loop()``.

    All ``ProcessType.set_value`` calls in that cycle share this timestamp
    unless an explicit timestamp is supplied by the caller. Sub-ms noise is
    discarded so UNIQUE ``(tag_id, timestamp)`` collapses same-cycle rewrites.
    """
    from ..timebase import quantize_datetime_ms

    ts = quantize_datetime_ms(datetime.now(timezone.utc))
    if machine is not None:
        machine.cycle_timestamp = ts
    return ts


def run_machine_cycle(machine) -> None:
    """One execution tick. Historian I/O must not stop the scheduler.

    CVT / OPC UA / leak logic always run. Peewee ``OperationalError`` (outage
    gate or a missed ``is_db_connected`` check in a ``while_*``) is swallowed
    so leaking/running/starting all keep the same realtime contract.
    """
    from peewee import OperationalError

    from ..state_machine_timing import record_execution_metrics
    from ..utils.db_connections import ephemeral_historian
    from automation import PyAutomation

    if machine is not None and getattr(machine, "get_sample_interval", lambda: None)() is None:
        legacy = getattr(machine, "_legacy_sample_and_execute", None)
        if callable(legacy):
            legacy()

    stamp_machine_cycle(machine)
    app = PyAutomation()
    t0 = time.monotonic()
    try:
        if getattr(app, "_db_live", False):
            with ephemeral_historian(getattr(app, "_db", None)):
                machine.loop()
        else:
            machine.loop()
    except OperationalError:
        logging.getLogger("pyautomation").debug(
            "Acquisition cycle skipped historian I/O machine=%s",
            getattr(getattr(machine, "name", None), "value", None),
            exc_info=True,
        )
    finally:
        cycle_us = (time.monotonic() - t0) * 1_000_000.0
        try:
            name = getattr(getattr(machine, "name", None), "value", None) or "-"
            record_execution_metrics(name, cycle_us)
        except Exception:
            pass


class MachineScheduler():
    r"""
    A simple scheduler for executing tasks (state machine loops) periodically.

    It maintains a queue of ready tasks and a heap of scheduled tasks.
    """

    def __init__(self):

        self._ready = deque()
        self._sleeping = list()
        self._sequence = 0
        self.last = None
        self._stop = False

    def call_soon(self, func):
        r"""
        Schedules a function to be called as soon as possible.

        **Parameters:**

        * **func** (callable): The function to execute.
        """
        self._ready.append(func)

    def call_later(self, delay, func, machine):
        r"""
        Schedules a function to be called after a delay.

        **Parameters:**

        * **delay** (float): Delay in seconds.
        * **func** (callable): The function to execute.
        * **machine** (StateMachine): The associated state machine instance.
        """
        self._sequence += 1
        deadline = time.time() + delay
        heapq.heappush(self._sleeping, (deadline, self._sequence, func, machine))

    def stop(self):
        r"""
        Stops the scheduler loop.
        """
        self._stop = True
    
    def run(self):
        r"""
        Main scheduler loop.

        Executes tasks in the ready queue and moves scheduled tasks to the ready queue
        when their deadline is reached. Handles sleep intervals to manage CPU usage.
        """
        self.set_last()
        
        while self._ready or self._sleeping:

            if self._stop:
                break

            if not self._ready and self._sleeping:
                deadline, _, func, machine = heapq.heappop(self._sleeping)
                self.sleep_elapsed(machine)
                
                self._ready.append(func)

            while self._ready:
                func = self._ready.popleft()
                func()

    def set_last(self):
        r"""
        Updates the last execution timestamp.
        """
        self.last = time.time()

        return self.last

    def sleep_elapsed(self, machine):
        r"""
        Sleeps for the remaining time until the next scheduled task.

        **Parameters:**

        * **machine** (StateMachine): The machine associated with the next task.
        """
        elapsed = time.time() - self.last
        interval = machine.get_interval()
        
        try:
            time.sleep(interval - elapsed)
            self.set_last()
        except ValueError:
            self.set_last()
            logger = logging.getLogger("pyautomation")
            logger.warning(f"State Machine: {machine.name.value} NOT executed on time - Execution Interval: {interval} - Elapsed: {elapsed}")


def _machine_wants_sample_scheduler(machine) -> bool:
    getter = getattr(machine, "get_sample_interval", None)
    if not callable(getter) or getter() is None:
        return False
    classification = ""
    try:
        classification = str(machine.classification.value).lower()
    except Exception:
        classification = ""
    if "data acquisition" in classification:
        return False
    if machine.__class__.__name__ in {"DAQ", "OPCUAServer"}:
        return False
    return True


class SampleSchedThread(Thread):
    """Independent OS thread: fills buffers even if execution blocks (fault isolation)."""

    def __init__(self, machine):
        machine_name = "machine"
        try:
            machine_name = str(machine.name.value)
        except Exception:
            pass
        super(SampleSchedThread, self).__init__(name=f"SM-SAMP-{machine_name}"[:40])
        self.machine = machine
        # Never assign ``self._stop``: CPython/gevent Thread._stop() is a method.
        # Overwriting it with a bool makes thread teardown raise
        # ``TypeError: 'bool' object is not callable`` (Python 3.12 + gevent).
        self._stop_requested = False
        self._last_sample_time = {}
        self.daemon = True

    def stop(self):
        self._stop_requested = True

    def run(self):
        from ..state_machine_timing import coop_sleep, record_sample_metrics

        logger = logging.getLogger("pyautomation")
        while not self._stop_requested:
            interval = None
            getter = getattr(self.machine, "get_sample_interval", None)
            if callable(getter):
                interval = getter()
            if interval is None:
                break
            interval = float(interval)
            tick_start = time.monotonic()
            try:
                if getattr(self.machine, "_sample_clock_reset", False):
                    self._last_sample_time.clear()
                    self.machine._sample_clock_reset = False
                self.machine._sample_once(tick_start, self._last_sample_time)
            except Exception:
                logger.debug("Sample loop error", exc_info=True)
            elapsed = time.monotonic() - tick_start
            if elapsed > 0.10 * interval:
                logger.warning(
                    "Sample loop overloaded machine=%s elapsed=%.4fs interval=%.4fs",
                    getattr(getattr(self.machine, "name", None), "value", None),
                    elapsed,
                    interval,
                )
            lag_ms = max(0.0, (elapsed - interval) * 1000.0)
            util = 0.0
            try:
                util = self.machine.buffer_utilization_pct()
            except Exception:
                util = 0.0
            name = getattr(getattr(self.machine, "name", None), "value", None) or "-"
            record_sample_metrics(name, elapsed, lag_ms, util)
            remain = interval - elapsed
            if remain > 0 and not self._stop_requested:
                coop_sleep(remain)


class SchedThread(Thread):
    r"""
    A thread that runs a dedicated scheduler for a single state machine (execution clock).
    """

    def __init__(self, machine):
        machine_name = "machine"
        try:
            machine_name = str(machine.name.value)
        except Exception:
            pass
        super(SchedThread, self).__init__(name=f"SM-{machine_name}"[:40])
        self.machine = machine

    def stop(self):
        r"""
        Stops the scheduler running in this thread.
        """
        self.scheduler.stop()

    def loop_closure(self, machine, scheduler:MachineScheduler):
        r"""
        Creates a closure for the state machine loop function.

        **Parameters:**

        * **machine** (StateMachine): The state machine.
        * **scheduler** (MachineScheduler): The scheduler managing execution.

        **Returns:**

        * **callable**: The loop function.
        """
        def loop():
            run_machine_cycle(machine)
            interval = machine.get_interval()
            scheduler.call_later(interval, loop, machine)
    
        return loop
    
    def target(self, machine):
        r"""
        The target function for the thread. Initializes and runs the scheduler.
        """
        scheduler = MachineScheduler()
        self.scheduler = scheduler
        func = self.loop_closure(machine, scheduler)
        scheduler.call_soon(func)
        scheduler.run() 

    def run(self):
        r"""
        Starts the thread execution.
        """
        self.target(self.machine)


class AsyncStateMachineWorker(BaseWorker):
    r"""
    Worker that manages asynchronously executed state machines (each in its own thread).
    """

    def __init__(self):

        super(AsyncStateMachineWorker, self).__init__()
        self.name = "AsyncStateMachineWorker"
        self._machines = list()
        self._schedulers = list()
        self.jobs = list()

    def add_machine(self, machine):
        r"""
        Adds a machine to be managed by this worker.
        """
        self._machines.append(machine)

    def run(self):
        r"""
        Starts a separate thread (SchedThread) for each registered machine.
        """
        for machine in self._machines:

            sched = SchedThread(machine)
            self._schedulers.append(sched)

        for sched in self._schedulers:

            sched.daemon = True
            sched.start()

    def join(self, machine):
        r"""
        Adds and starts a new machine dynamically at runtime.
        """
        sched = SchedThread(machine)
        self._schedulers.append(sched)
        sched.daemon = True
        sched.start()

    def drop(self, machine):
        r"""
        Stops and removes a machine from execution.
        """
        sched_to_drop = None
        for index, sched in enumerate(self._schedulers):
            if machine == sched.machine:
                sched_to_drop = self._schedulers.pop(index)
                break

        if sched_to_drop:
            sched_to_drop.stop()

        try:
            self._machines.remove(machine)
        except ValueError:
            pass

    def stop(self):
        r"""
        Stops all managed threads.
        """
        for sched in self._schedulers:
            try:
                sched.stop()
            except Exception as e:
                message = "Error on async scheduler stop"
                logger = logging.getLogger("pyautomation")
                logger.error(f"{message} - {e}")
    

class StateMachineWorker(BaseWorker):
    r"""
    The main worker responsible for coordinating state machine execution.

    It manages two types of execution:
    1. **Sync**: Machines executed sequentially in the main worker thread (cooperative multitasking).
    2. **Async**: Machines executed in separate threads (preemptive multitasking).
    """

    def __init__(self, manager):

        super(StateMachineWorker, self).__init__()
        self.name = "StateMachineWorker"
        self._manager = manager
        self._sync_scheduler = MachineScheduler()
        self._async_scheduler = AsyncStateMachineWorker()
        self._sample_threads = {}
        self.jobs = list()

    def _machine_key(self, machine):
        try:
            return str(machine.name.value)
        except Exception:
            return id(machine)

    def reconfigure_sampling(self, machine) -> None:
        key = self._machine_key(machine)
        wanted = _machine_wants_sample_scheduler(machine)
        existing = self._sample_threads.get(key)
        alive = existing is not None and existing.is_alive()
        if wanted and alive:
            return
        if existing is not None:
            self._sample_threads.pop(key, None)
            try:
                existing.stop()
                existing.join(timeout=2.0)
            except Exception:
                pass
        if not wanted:
            return
        thread = SampleSchedThread(machine)
        self._sample_threads[key] = thread
        thread.start()

    def loop_closure(self, machine):
        
        self._machine = machine

        def loop():
            run_machine_cycle(machine)
            interval = machine.get_interval()
            self._sync_scheduler.call_later(interval, loop, machine)

        return loop

    def run(self):
        r"""
        Starts the worker.

        Iterates through registered machines and assigns them to either the sync or async scheduler
        based on their configuration.
        """
        for machine, interval, mode in self._manager.get_machines():
    
            if mode == "async":
                
                self._async_scheduler.add_machine(machine)                
                
            else:

                func = self.loop_closure(machine)
                self._sync_scheduler.call_soon(func)

        for machine, _, _ in self._manager.get_machines():
            self.reconfigure_sampling(machine)

        self._async_scheduler.run()
        self._sync_scheduler.run()

    def stop(self):
        r"""
        Stops both sync and async schedulers.
        """
        for sampler in list(self._sample_threads.values()):
            try:
                sampler.stop()
            except Exception:
                pass
        self._sample_threads.clear()
        self._async_scheduler.stop()
        self._sync_scheduler.stop()
