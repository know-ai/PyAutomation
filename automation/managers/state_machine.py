# -*- coding: utf-8 -*-
"""automation/managers/state_machine.py

This module implements the State Machine Manager, which acts as a registry and controller for all
state machine instances within the application.
"""
from statemachine import StateMachine
from ..models import StringType
from ..tags import Tag
from ..utils.decorators import logging_error_handler
import queue


def _is_acquisition_machine(machine) -> bool:
    try:
        return str(machine.classification.value).lower() == "data acquisition system"
    except Exception:
        return machine.__class__.__name__ == "DAQ"

class StateMachineManager:
    r"""
    Manages the lifecycle and execution configuration of State Machines.

    It maintains a registry of all active machines, their execution intervals, and threading modes (sync/async).
    """

    def __init__(self):

        self._machines = list()
        self._tag_queue = queue.Queue()

    @logging_error_handler
    def get_queue(self)->queue.Queue:
        r"""
        Retrieves the internal queue used for tag updates related to state machines.
        """
        return self._tag_queue

    @logging_error_handler
    def append_machine(self, machine:StateMachine):
        r"""
        Registers a new state machine.

        **Parameters:**

        * **machine** (StateMachine): The state machine instance.
        """
        
        self._machines.append(machine)

    @logging_error_handler
    def get_machines(self)->list:
        r"""
        Retrieves the list of all registered state machines.

        **Returns:**

        * **list**: List of tuples [(machine, interval, mode), ...].
        """
        result = self._machines
        
        return result
    
    @logging_error_handler
    def serialize_machines(self):
        r"""
        Serializes all registered machines to a list of dictionaries.

        **Returns:**

        * **list[dict]**: Serialized machine data.
        """

        return [machine.serialize() for machine, _, _ in self.get_machines()]

    @logging_error_handler
    def get_machine(self, name:StringType)->StateMachine:
        r"""
        Retrieves a state machine by its name.

        **Parameters:**

        * **name** (StringType): The name of the machine.

        **Returns:**

        * **StateMachine**: The machine instance if found.
        """
        for machine, _, _ in self._machines:

            if name.value == machine.name.value:

                return machine
            
    @logging_error_handler
    def drop(self, name:str):
        r"""
        Removes a state machine from the manager.

        **Parameters:**

        * **name** (str): The name of the machine to remove.

        **Returns:**

        * **tuple**: The removed (machine, interval, mode) tuple.
        """
        index = 0
        for machine, _, _ in self._machines:

            if name == machine.name.value:

                machine_to_revome_from_worker = self._machines.pop(index)
                break

            index += 1

        if machine_to_revome_from_worker:

            return machine_to_revome_from_worker

    @logging_error_handler
    def unsubscribe_tag(self, tag:Tag, acquisition_only: bool = False):
        r"""
        Unsubscribes a tag from state machines.

        ``acquisition_only=True`` (tag edit / OPC UA resubscribe) only
        touches DAQ machines. Leak-detection motors keep the binding.
        Full drop (``acquisition_only=False``) is for tag deletion.
        """
        machine_to_revome_from_worker = (None, None, None)
        for machine, _, _ in self._machines:

            if not hasattr(machine, "unsubscribe_to"):
                continue

            is_daq = _is_acquisition_machine(machine)
            if acquisition_only and not is_daq:
                continue

            machine.unsubscribe_to(tag=tag)

            if is_daq and not machine.get_subscribed_tags():

                machine_to_revome_from_worker = self.drop(name=machine.name.value)
                break

        return machine_to_revome_from_worker

    @logging_error_handler
    def summary(self)->dict:
        r"""
        Generates a summary of registered state machines.

        **Returns:**

        * **dict**: {length: int, state_machines: list[str]}
        """
        result = dict()
        machines = [machine.name for machine, _, _ in self.get_machines()]

        result["length"] = len(machines)
        result["state_machines"] = machines

        return result

    @logging_error_handler
    def exist_machines(self)->bool:
        r"""
        Checks if there are any registered state machines.

        **Returns:**

        * **bool**: True if at least one machine exists.
        """
        return len(self._machines) > 0