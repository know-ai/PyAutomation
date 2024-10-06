# -*- coding: utf-8 -*-
"""automation/workers/state.py

This module implements State Machine Worker.
"""
import heapq
import logging
import time
from collections import deque
from threading import Thread
from .worker import BaseWorker


class MachineScheduler():

    def __init__(self):

        self._ready = deque()
        self._sleeping = list()
        self._sequence = 0
        self.last = None
        self._stop = False

    def call_soon(self, func):
        
        self._ready.append(func)

    def call_later(self, delay, func, machine):
        self._sequence += 1
        deadline = time.time() + delay
        heapq.heappush(self._sleeping, (deadline, self._sequence, func, machine))

    def stop(self):

        self._stop = True
    
    def run(self):

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

        self.last = time.time()

        return self.last

    def sleep_elapsed(self, machine):
        elapsed = time.time() - self.last
        interval = machine.get_interval()
        
        try:
            time.sleep(interval - elapsed)
            self.set_last()
        except ValueError:
            self.set_last()
            logging.warning(f"State Machine: {machine.name.value} NOT executed on time - Execution Interval: {interval} - Elapsed: {elapsed}")


class SchedThread(Thread):

    def __init__(self, machine):

        super(SchedThread, self).__init__()

        self.machine = machine

    def stop(self):

        self.scheduler.stop()

    def loop_closure(self, machine, scheduler:MachineScheduler):

        def loop():
            machine.loop()
            interval = machine.get_interval()
            scheduler.call_later(interval, loop, machine)
    
        return loop
    
    def target(self, machine):
        scheduler = MachineScheduler()
        self.scheduler = scheduler
        func = self.loop_closure(machine, scheduler)
        scheduler.call_soon(func)
        scheduler.run() 

    def run(self):
        
        self.target(self.machine)


class AsyncStateMachineWorker(BaseWorker):

    def __init__(self):

        super(AsyncStateMachineWorker, self).__init__()
        self._machines = list()
        self._schedulers = list()
        self.jobs = list()

    def add_machine(self, machine):

        self._machines.append(machine)

    def run(self):

        for machine in self._machines:

            sched = SchedThread(machine)
            self._schedulers.append(sched)

        for sched in self._schedulers:

            sched.daemon = True
            sched.start()

    def join(self, machine):

        sched = SchedThread(machine)
        self._schedulers.append(sched)
        sched.daemon = True
        sched.start()

    def drop(self, machine):
        r"""
        Documentation here
        """
        sched_to_drop = None
        for index, sched in enumerate(self._schedulers):
            if machine==sched.machine:

                sched_to_drop = self._schedulers.pop(index)
                break
        
        if sched_to_drop:
            sched.stop()

    def stop(self):

        for sched in self._schedulers:
            try:
                sched.stop()
            except Exception as e:
                message = "Error on async scheduler stop"
                logging.error(f"{message} - {e}")
    

class StateMachineWorker(BaseWorker):

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
        
        for machine, interval, mode in self._manager.get_machines():
    
            if mode == "async":
                
                self._async_scheduler.add_machine(machine)                
                
            else:

                func = self.loop_closure(machine)
                self._sync_scheduler.call_soon(func)

        self._async_scheduler.run()
        self._sync_scheduler.run()

    def stop(self):
        
        self._async_scheduler.stop()
        self._sync_scheduler.stop()
    