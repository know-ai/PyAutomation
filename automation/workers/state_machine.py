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
        self._stop = False
        self.machine = None

    def call_soon(self, func):
        
        self._ready.append(func)

    def call_later(self, delay, func, machine):
        deadline = time.time() + delay
        heapq.heappush(self._sleeping, (deadline, func, machine))

    def stop(self):

        self._stop = True
    
    def run(self):
        
        while self._ready or self._sleeping:

            if self._stop:
                break

            if not self._ready and self._sleeping:
                deadline, func, self.machine = heapq.heappop(self._sleeping)
                self._ready.append(func)
                self._check_sleep(deadline=deadline)

            while self._ready:
                deadline = time.time()
                func = self._ready.popleft()
                func()
                time_to_finish_job = time.time()-deadline
                if self.machine:
                    
                    if time_to_finish_job > self.machine.get_interval():
                        
                        print(f"State Machine {self.machine.name} NOT Executed on time - Interval: {self.machine.get_interval()} - Time: {round(time_to_finish_job,3)}")

    def _check_sleep(self, deadline):
        r"""
        Documentation here
        """
        delta = deadline - time.time()
        if delta > 0:
            time.sleep(delta)


class SchedThread(Thread):

    def __init__(self, machine, manager):

        super(SchedThread, self).__init__()

        self.machine = machine
        self._manager = manager

    def stop(self):

        self.scheduler.stop()

    def loop_closure(self, machine, scheduler):

        def loop():
            _queue = self._manager.get_queue()
            
            while not _queue.empty():
                
                item = _queue.get()
                
                # Notify to Machine
                # print(f"ITEM: {item}")
                # for _machine, _, _ in self._manager.get_machines():

                #     _machine.notify(**item)

            machine.loop()
            local_interval = machine.get_interval()
            interval = machine.get_interval()
            interval = min(interval, local_interval)
            scheduler.call_later(interval, loop, machine)
    
        return loop
    
    def target(self, machine):
        scheduler = MachineScheduler()
        self.scheduler = scheduler
        func = self.loop_closure(machine, scheduler)
        scheduler.call_soon(func)
        return scheduler

    def run(self):
        
        scheduler = self.target(self.machine)
        thread = Thread(target=scheduler.run)
        thread.start()


class AsyncStateMachineWorker(BaseWorker):

    def __init__(self, manager):

        super(AsyncStateMachineWorker, self).__init__()
        self._machines = list()
        self._schedulers = list()
        self.jobs = list()
        self._manager = manager

    def add_machine(self, machine, interval):

        self._machines.append((machine, interval,))

    def run(self):

        for machine, _ in self._machines:

            sched = SchedThread(machine, self._manager)
            self._schedulers.append(sched)
            sched.target(machine)

        for sched in self._schedulers:

            sched.daemon = True
            sched.run()

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
        self._manager.attach_all()
        self._sync_scheduler = MachineScheduler()
        self._async_scheduler = AsyncStateMachineWorker(manager=self._manager)
        self.jobs = list()

    def loop_closure(self, machine):
        
        def loop():
            machine.loop()
            local_interval = machine.get_state_interval()
            interval = machine.get_interval()
            interval = min(interval, local_interval)
            self._sync_scheduler.call_later(interval, loop, machine)

        return loop

    def run(self):
        
        for machine, interval, mode in self._manager.get_machines():
            
            if mode == "async":
                
                self._async_scheduler.add_machine(machine, interval)
                
                
            else:
                func = self.loop_closure(machine)
                self._sync_scheduler.call_soon(func)

        self._async_scheduler.run()
        self._sync_scheduler.run()
        

    def stop(self):

        self._async_scheduler.stop()
        self._sync_scheduler.stop()
    