from statemachine import StateMachine
from statemachine import State
from .workers import StateMachineWorker
from .managers import StateMachineManager
from .singleton import Singleton
import logging

class Machine(Singleton):
    r"""
    """
    def __init__(self):

        self._machine_manager = StateMachineManager()
        self.workers = list()

    def append_machine(self, machine, interval:float=1, mode:str='sync'):
        """
        Append a state machine to the state machine manager.

        **Parameters:**

        * **machine** (`PyHadesStateMachine`): a state machine object.
        * **interval** (int): Interval execution time in seconds.
        """
        machine.set_interval(interval)
        self._machine_manager.append_machine((machine, interval, mode))

    def get_machine(self, name:str):
        """
        Returns a PyHades State Machine defined by its name.

        **Parameters:**

        * **name** (str): a pyhades state machine name.

        Usage

        ```python
        >>> state_machine = app.get_machine('state_machine_name')
        ```
        """

        return self._machine_manager.get_machine(name)

    def get_machines(self)->list:
        """
        Returns all defined PyHades state machines.

        **Returns** (list)

        Usage

        ```python
        >>> state_machines = app.get_machines()
        ```
        """

        return self._machine_manager.get_machines()

    def get_state_machine_manager(self)->StateMachineManager:
        r"""
        Gets state machine Manager

        **Returns:** StateMachineManager instance

        ```python
        >>> state_manager = app.get_state_machine_manager()
        ```
        """
        return self._machine_manager

    def start(self):
        r"""
        Starts statemachine worker
        """
        # StateMachine Worker
        state_manager = self.get_state_machine_manager()
        if state_manager.exist_machines():

            state_worker = StateMachineWorker(state_manager)
            self.workers.append(state_worker)

        for worker in self.workers:
            worker.daemon = True
            worker.run()

    def stop(self):
        r"""
        Safe stop workers execution
        """
        for worker in self.workers:
            try:
                worker.stop()
            except Exception as e:
                message = f"Error on wokers stop, {e}"
                logging.error(message)


class AutomationStateMachine(StateMachine):

    starting = State('start', initial=True)
    waiting = State('wait')
    running = State('run')
    testing = State('test')
    sleeping = State('sleep')
    resetting = State('reset')
    restarting = State('restart')

    # Transitions
    start_to_wait = starting.to(waiting)
    wait_to_run = waiting.to(running)

    #
    wait_to_restart = waiting.to(restarting)
    wait_to_reset = waiting.to(resetting)
    run_to_restart = running.to(restarting)
    run_to_reset = running.to(resetting)
    test_to_restart = testing.to(restarting)
    test_to_reset = testing.to(resetting)
    sleep_to_restart = sleeping.to(restarting)
    sleep_to_reset = sleeping.to(resetting)

    #
    reset_to_start = resetting.to(starting)
    restart_to_wait = restarting.to(waiting)

    #
    run_to_test = running.to(testing)
    wait_to_test = waiting.to(testing)

    #
    run_to_sleep = running.to(sleeping)
    wait_to_sleep = waiting.to(sleeping)

    def __init__(self, name:str):

        super(AutomationStateMachine, self).__init__()
        self.name = name

    # State Methods
    def while_starting(self):

        print(f"{self.name}: [Starting]")
        self.send('start_to_wait')

    def while_waiting(self):

        print(f"{self.name}: [Waiting]")
        self.send('wait_to_run')

    def while_running(self):

        print(f"{self.name}: [Running]")
        self.send('run_to_reset')

    def while_testing(self):

        print(f"{self.name}: [Testing]")

    def while_sleeping(self):

        print(f"{self.name}: [Sleeping]")

    def while_resetting(self):

        print(f"{self.name}: [Resetting]")
        self.send('reset_to_start')

    def while_restarting(self):

        print(f"{self.name}: [Restarting]")

    # Transitions
    def on_start_to_wait(self):

        print(f"[start_to_wait]")

    def on_wait_to_run(self):

        print(f"[wait_to_run]")

    def on_wait_to_restart(self):

        print(f"[wait_to_restart]")

    def on_wait_to_reset(self):

        print(f"[wait_to_reset]")

    def on_run_to_restart(self):

        print(f"[run_to_restart]")

    def on_run_to_reset(self):

        print(f"[run_to_reset]")

    def on_test_to_restart(self):

        print(f"[test_to_restart]")

    def on_test_to_reset(self):

        print(f"[test_to_reset]")

    def on_sleep_to_restart(self):

        print(f"[sleep_to_restart]")

    def on_sleep_to_reset(self):

        print(f"[leep_to_reset]")

    def on_reset_to_start(self):

        print(f"[reset_to_start]")

    def on_restart_to_wait(self):

        print(f"[restart_to_wait]")

    # Auxiliaries Methods

    def get_state_interval(self)->float:
        r"""
        Gets current state interval

        **Returns**

        * **(float)**

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> current_interval = machine.get_state_interval()
        ```

        """
        return self.get_interval()

    def get_interval(self)->float:
        r"""
        Gets overall state machine interval

        **Returns**

        * **(float)**

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> interval = machine.get_interval()
        ```
        """
        return self._machine_interval

    def set_interval(self, interval):
        r"""
        Sets overall machine interval

        **Parameters**

        * **interval:** (float) overal machine interval in seconds

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> machine.set_interval(0.5)
        ```
        """
        self._machine_interval = interval

    def _get_active_transitions(self):
        r"""
        Gets allowed transitions based on the current state

        **Returns**

        * **(list)**
        """
        result = list()

        current_state = self.current_state

        transitions = self.transitions

        for transition in transitions:

            if transition.source == current_state:

                result.append(transition)

        return result

    def _activate_triggers(self):
        r"""
        Allows to execute the on_ method in transitions when it's necesary

        """
        transitions = self._get_active_transitions()

        for transition in transitions:
            method_name = transition.identifier
            method = getattr(self, method_name)

            try:
                source = transition.source
                if not source._trigger:
                    continue
                if source._trigger.evaluate():
                    method()
            except Exception as e:
                error = str(e)
                logging.error(f"Machine - {self.name}:{error}")

    def loop(self):
        r"""
        Documentation in construction
        """
        state_name = self.current_state.value
        method_name = "while_" + state_name

        if method_name in dir(self):

            method = getattr(self, method_name)
            method()            

    def info(self)->str:
        r"""
        Gets general information of the state machine

        **Returns**

        * **(str)**

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> info = machine.info()
        ```
        """
        return f'''\nState Machine: {self.name} - Interval: {self.get_interval()} seconds - States: {self.get_states()}'''

    def get_states(self)->list:
        r"""
        Gets a list of state machine's names

        **Returns**

        * **(list)**

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> states = machine.get_states()
        ```
        """

        return [state.value for state in self.states]


    def serialize(self):

        return {
            "name": self.name,
            "state": self.current_state.value,
            "host": self.host,
            "port": self.port,
            "exchange": self.exchange,
            "is_producer_connected": self.producer.connection.is_open if hasattr(self, 'producer') else False,
            "is_consumer_connected": self.consumer.connection.is_open if hasattr(self, 'consumer') else False
        }


class LeakStateMachine(AutomationStateMachine):

    pre_alarming = State('pre_alarm')  
    leaking = State('leak')
    switching = State('switch')
    not_available = State('not_available')

    #Transitions
    run_to_pre_alarm = AutomationStateMachine.running.to(pre_alarming)
    pre_alarm_to_run = pre_alarming.to(AutomationStateMachine.running)
    pre_alarm_to_leak = pre_alarming.to(leaking)
    leak_to_restart = leaking.to(AutomationStateMachine.restarting)
    leak_to_reset = leaking.to(AutomationStateMachine.resetting)

    start_to_switch = AutomationStateMachine.starting.to(switching)
    wait_to_switch = AutomationStateMachine.waiting.to(switching)
    run_to_switch = AutomationStateMachine.running.to(switching)
    switch_to_not_available = switching.to(not_available)
    switch_to_restart = switching.to(AutomationStateMachine.restarting)
    switch_to_reset = switching.to(AutomationStateMachine.resetting)
    not_available_to_restart = not_available.to(AutomationStateMachine.restarting)
    not_available_to_reset = not_available.to(AutomationStateMachine.resetting)
    
    def __init__(self, name:str):

        super(LeakStateMachine, self).__init__(name=name)

    def while_running(self):
        r"""
        Documentation here
        """
        print(f"{self.name} Running")

    def while_pre_alarming(self):
        r"""
        Documentation here
        """
        print(f"{self.name} Pre Alarming")

    def while_leaking(self):
        r"""
        Documentation here
        """
        print(f"{self.name} Leaking")

    def while_switching(self):
        r"""
        Documentation here
        """
        print(f"{self.name} Switching")

    def while_not_available(self):
        r"""
        Documentation here
        """
        print(f"{self.name} Not available")

    # Transitions methods
    def on_run_to_pre_alarm(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_pre_alarm_to_run(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_pre_alarm_to_leak(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_leak_to_restart(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_leak_to_reset(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_start_to_switch(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_wait_to_switch(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_run_to_switch(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_switch_to_not_available(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_switch_to_restart(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_switch_to_reset(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_not_available_to_restart(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")

    def on_not_available_to_reset(self):
        r"""
        Documentation here
        """
        print(f"{self.name}: Transition")