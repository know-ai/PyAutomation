# -*- coding: utf-8 -*-
"""automation/workers/state.py

This module implements the State Machine Worker, managing the execution of state machines.
"""
import heapq
import logging
import time
from collections import deque
from threading import Thread
from .worker import BaseWorker


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


class SchedThread(Thread):
    r"""
    A thread that runs a dedicated scheduler for a single state machine.
    """

    def __init__(self, machine):

        super(SchedThread, self).__init__()

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
            machine.loop()
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
            if machine==sched.machine:

                sched_to_drop = self._schedulers.pop(index)
                break
        
        if sched_to_drop:
            sched.stop()

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
        
        self._manager = manager
        self._sync_scheduler = MachineScheduler()
        self._async_scheduler = AsyncStateMachineWorker()
        self.jobs = list()

    def loop_closure(self, machine):
        
        self._machine = machine

        def loop():
            machine.loop()
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

        self._async_scheduler.run()
        self._sync_scheduler.run()

    def stop(self):
        r"""
        Stops both sync and async schedulers.
        """
        self._async_scheduler.stop()
        self._sync_scheduler.stop()
