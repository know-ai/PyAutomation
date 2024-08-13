# -*- coding: utf-8 -*-
"""broker/managers/state_machine.py

This module implements Function Manager.
"""
from statemachine import StateMachine
from ..tags import TagObserver, CVTEngine
import queue

class StateMachineManager:
    r"""
    Handles and manager the state machines defined in the application in a store defined by a list of tuples

    Its structure is [(machine_1, interval_1, mode_1), (machine_2, interval_2, mode_2), ... (machine_n, interval_n, mode_n)]
    """

    def __init__(self):

        self._machines = list()
        self._tag_queue = queue.Queue()

    def get_queue(self)->queue.Queue:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return self._tag_queue

    def append_machine(self, machine:StateMachine):
        r"""
        Appends machines to the store

        **Parameters**

        * **machine:** (PyHadesStateMachine) instance
        * **interval:** (float) Execution interval in seconds
        * **mode:** (str) Thread mode of the state machine, allowed mode ('sync', 'async')

        **Returns** `None`

        Usage

        ```python
        >>> manager = app.get_state_machine_manager()
        >>> manager.append_machine(machine, interval, mode)
        ```
        """
        
        self._machines.append(machine)

    def get_machines(self)->list:
        r"""
        Gets state machines

        **Returns**

        * **machines** (list of tuples)

        Usage

        ```python
        >>> manager = app.get_state_machine_manager()
        >>> machines = manager.get_machines()
        [(machine_1, interval_1, mode_1), (machine_2, interval_2, mode_2), ... (machine_n, interval_n, mode_n)]
        ```
        """
        result = self._machines
        
        return result

    def get_machine(self, name:str)->StateMachine:
        r"""
        Gets state machine by its name

        **Parameters**

        * **name:** (str) State machine name

        **Returns**

        * **machine:** (PyHadesStateMachine) instance

        Usage

        ```python
        >>> manager = app.get_state_machine_manager()
        >>> machine = manager.get_machine(state_machine_name)
        ```
        """
        for machine in self._machines:

            if name == machine.name:

                return machine

    def summary(self)->dict:
        r"""
        Get a summary of the state machine defined

        **Returns**

        * **summary:** (dict) with keys ('length' (int) - 'state_machines' (list of state machine names))
        """
        result = dict()

        machines = [machine.name for machine in self.get_machines()]

        result["length"] = len(machines)
        result["state_machines"] = machines

        return result

    def exist_machines(self)->bool:
        r"""
        Checks if exist state machines defined

        **Returns**

        * **Bool**

        Usage

        ```python
        >>> manager = app.get_state_machine_manager()
        >>> manager.exist_machines()
        ```
        """
        return len(self._machines) > 0
    
    def attach_all(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        cvt = CVTEngine()

        def attach_observers(tag):

            observer = TagObserver(self.get_queue())
            query = dict()
            query["action"] = "attach_observer"
            query["parameters"] = {
                "name": tag,
                "observer": observer,
            }
            cvt.request(query)
            cvt.response()

        tags_for_subscriptions = list()

        for machine, _, _ in self.get_machines():

            for tag in machine.get_subscribed_tags():

                if tag not in tags_for_subscriptions:

                    tags_for_subscriptions.append(tag)
        
        for tag in tags_for_subscriptions:
            
            attach_observers(tag)