from statemachine import StateMachine
from statemachine import State
from .workers import StateMachineWorker
from .managers import StateMachineManager
from .singleton import Singleton
import logging
from .buffer import Buffer
from .models import StringType, IntegerType, FloatType, BooleanType
from .tags import CVTEngine, Tag
from .logger.datalogger import DataLoggerEngine
from .logger.events import EventsLoggerEngine
from .managers.opcua_client import OPCUAClientManager
from .opcua.subscription import DAS
from .modules.users.users import User
from .utils.decorators import set_event, validate_types


events_engine = EventsLoggerEngine()

class Machine(Singleton):
    r"""Documentation here
    """
    def __init__(self):

        self._machine_manager = StateMachineManager()
        self.workers = list()

    def append_machine(self, machine:StateMachine, interval:float=1, mode:str='sync'):
        r"""
        Append a state machine to the state machine manager.

        **Parameters:**

        * **machine** (`PyHadesStateMachine`): a state machine object.
        * **interval** (int): Interval execution time in seconds.
        """
        if isinstance(machine, DAQ):
            
            machine.name = f"DAQ-{interval}"
        
        machine.set_interval(interval)
        self._machine_manager.append_machine((machine, interval, mode))

    def drop(self, name:str):
        r"""
        Documentation here
        """
        self._machine_manager.drop(name=name)

    def get_machine(self, name:str):
        r"""
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
        r"""
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

            self.state_worker = StateMachineWorker(state_manager)
            self.state_worker.run()

    def stop(self):
        r"""
        Safe stop workers execution
        """
        try:
            self.state_worker.stop()
        except Exception as e:
            message = f"Error on wokers stop, {e}"
            logging.error(message)


class DAQ(StateMachine):
    r"""
    Documentation here
    """

    starting = State('start', initial=True)
    running = State('run')
    resetting = State('reset')

    # Transitions
    start_to_run = starting.to(running)
    run_to_reset = running.to(resetting)
    reset_to_start = resetting.to(starting)
    

    def __init__(
            self
        ):

        super(DAQ, self).__init__()
        self.name = "DAQ"
        self.das = DAS()
        self.opcua_client_manager = None
        self.machine_interval = None
        self.criticity = IntegerType(default=2)
        self.priority = IntegerType(default=1)
        self.description = StringType(default="")
        self.classification = StringType(default="Data Acquisition System")
        self.__subscribed_to = dict()
        self.cvt = CVTEngine()
        self.logger = DataLoggerEngine()

    # State Methods
    def while_starting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        # TRANSITION
        self.send('start_to_run')

    def while_running(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        tags = list()

        for tag_name, tag in self.get_subscribed_tags().items():

            namespace = tag.get_node_namespace()
            opcua_address = tag.get_opcua_address()
            values = self.opcua_client_manager.get_node_value_by_opcua_address(opcua_address=opcua_address, namespace=namespace)
            if values:
                data_value = values[0][0]["DataValue"]
                value = data_value.Value.Value
                timestamp = data_value.SourceTimestamp
                tags.append({
                    "tag": tag_name,
                    "value": value,
                    "timestamp": timestamp
                })
                self.cvt.set_value(id=tag.id, value=value, timestamp=timestamp)
                self.das.buffer[tag_name]["timestamp"](timestamp)
                self.das.buffer[tag_name]["values"](self.cvt.get_value(id=tag.id))
                

        # INSERT MANY into database
        if tags:
            self.logger.write_tags(tags)
        self.criticity.value = 1

    def while_resetting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.send('reset_to_start')

    # Auxiliaries Methods
    def set_opcua_client_manager(self, manager:OPCUAClientManager):
        r"""
        Documentation here
        """
        self.opcua_client_manager = manager

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

    def get_subscribed_tags(self)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return self.__subscribed_to
    
    def subscribe_to(self, tag:Tag):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        tag_name = tag.get_name()

        if tag_name not in self.get_subscribed_tags():

            self.__subscribed_to[tag_name] = tag

    def notify(self, tag:str, value:str|int|bool|float):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        pass
        # if tag in self.data:
            
        #     self.data[tag](value)

    def unsubscribe_to(self, tag:Tag):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        tag_name = tag.get_name()
        if tag_name in self.get_subscribed_tags():

            self.__subscribed_to.pop(tag_name)

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
        return self.machine_interval

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
        self.machine_interval = interval

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
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
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

    def get_serialized_models(self):
        r"""
        Gets class attributes defined by [model types]()

        **Returns**

        * **(dict)**
        """
        result = dict()
        props = self.__dict__
        
        for key, value in props.items():

            if isinstance(value, (StringType, FloatType, IntegerType, BooleanType)):

                result[key] = value.value

        return result

    def serialize(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        result = {
            "name": self.name,
            "sampling_time": self.get_interval(),
            "state": self.current_state.id
        }
        result.update(self.get_serialized_models())
        return result


class AutomationStateMachine(StateMachine):
    r"""
    Documentation here
    """
    # States
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
    reset_to_start = resetting.to(starting)
    restart_to_wait = restarting.to(waiting)
    run_to_restart = running.to(restarting)
    wait_to_restart = waiting.to(restarting)
    test_to_restart = testing.to(restarting)
    sleep_to_restart = sleeping.to(restarting)
    run_to_reset = running.to(resetting)
    wait_to_reset = waiting.to(resetting)
    test_to_reset = testing.to(resetting)
    sleep_to_reset = sleeping.to(resetting)
    run_to_test = running.to(testing)
    wait_to_test = waiting.to(testing)
    run_to_sleep = running.to(sleeping)
    wait_to_sleep = waiting.to(sleeping)
    

    def __init__(
            self,
            name:str,
            description:str="",
            classification:str=""
        ):

        super(AutomationStateMachine, self).__init__()
        self.criticity = IntegerType(default=2)
        self.priority = IntegerType(default=1)
        self.description = StringType(default=description)
        self.classification = StringType(default=classification)
        self.name = StringType(default=name)
        self.machine_interval = FloatType(default=None)
        self.buffer_size = IntegerType(default=10)
        self.buffer_roll_type = StringType(default='backward')
        self.__subscribed_to = dict()

    # State Methods
    def while_starting(self):
        r"""
        This method is executed every machine loop when it is on Start state

        Configure your state machine here
        """
        # DEFINE DATA BUFFER
        self.set_buffer_size(size=self.buffer_size.value)
        # TRANSITION
        self.send('start_to_wait')

    def while_waiting(self):
        r"""
        This method is executed every machine loop when it is on Wait state

        It was designed to check your buffer data in self.data, if your buffer is full, so they pass to run state
        """
        ready_to_run = True
        for _, value in self.data.items():

            if len(value) < value.max_length:
                ready_to_run=False
                break

        if ready_to_run:

            self.send('wait_to_run')

    def while_running(self):
        r"""
        This method is executed every machine loop when it is on Run state

        Depending on you state machine goal, write your script here
        """
        self.criticity.value = 1

    def while_testing(self):
        r"""
        This method is executed every machine loop when it is on Test state
        """
        self.criticity.value = 3

    def while_sleeping(self):
        r"""
        This method is executed every machine loop when it is on Sleep state
        """
        self.criticity.value = 5

    def while_resetting(self):
        r"""
        This method is executed every machine loop when it is on Reset state
        """
        self.send("reset_to_start")

    def while_restarting(self):
        r"""
        This method is executed every machine loop when it is on Restart state
        """
        self.restart_buffer()
        self.send("restart_to_wait")

    # Transitions
    def on_start_to_wait(self):
        r"""
        It's executed one time before enter to Wait state from Sleep state 
        """
        self.last_state = "start"
        self.criticity.value = 1

    def on_wait_to_run(self):
        r"""
        It's executed one time before enter to Run state from Wait state 
        """
        self.last_state = "wait"
        self.criticity.value = 1

    def on_wait_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Wait state 
        """
        self.last_state = "wait"
        self.criticity.value = 5

    def on_wait_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Wait state 
        """
        self.last_state = "wait"
        self.criticity.value = 5

    def on_run_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Run state 
        """
        self.last_state = "run"
        self.criticity.value = 5

    def on_run_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Run state 
        """
        self.last_state = "run"
        self.criticity.value = 5

    def on_test_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Test state 
        """
        self.last_state = "test"
        self.criticity.value = 4

    def on_test_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Test state 
        """
        self.last_state = "test"
        self.criticity.value = 4

    def on_sleep_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Sleep state 
        """
        self.last_state = "sleep"
        self.criticity.value = 4

    def on_sleep_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Sleep state 
        """
        self.last_state = "sleep"
        self.criticity.value = 4

    def on_reset_to_start(self):
        r"""
        It's executed one time before enter to Start state from Reset state 
        """
        self.last_state = "reset"
        self.criticity.value = 2

    def on_restart_to_wait(self):
        r"""
        It's executed one time before enter to Wait state from Restart state 
        """
        self.last_state = "restart"
        self.criticity.value = 2

    # Auxiliaries Methods
    @validate_types(size=int, output=None)
    def set_buffer_size(self, size:int)->None:
        r"""
        Set data buffer size

        # Parameters

        - *size:* [int] buffer size
        """
        self.buffer_size.value = int(size)
        self.restart_buffer()

    def restart_buffer(self):
        r"""
        Restart Buffer
        """
        self.data = {tag_name: Buffer(length=self.buffer_size.value, roll=self.buffer_roll_type.value) for tag_name, tag in self.get_subscribed_tags().items()}

    @validate_types(output=dict)
    def get_subscribed_tags(self)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return self.__subscribed_to
    
    def subscribe_to(self, *tags:Tag):
        r"""

        # Parameters

        - *tags:* [list] 
        """
        for tag in tags:

            if tag not in self.get_subscribed_tags():

                self.__subscribed_to[tag.name] = tag

    @validate_types(tag=Tag, value=int|float|bool, output=None)
    def notify(self, tag:Tag, value:str|int|bool|float):
        r"""
        This method provide an interface to CVT to notify if tag value has change
        
        # Parameters

        - *tag:* [Tag] tag Object
        - *value:* [int|float|bool] tag value
        """
        if tag.name in self.get_subscribed_tags():
            print(f"{self.name.value}: {tag.name}: {value}")
            self.data[tag.name](value)

    @set_event(message=f"Switched", classification="State Machine", priority=2, criticity=3)
    @validate_types(to=str, user=User, output=None)
    def transition(self, to:str, user:User=None):
        r"""
        Documentation here
        """
        try:
            _from = self.current_state.name.lower()
            transition_name = f'{_from}_to_{to}'
            self.send(transition_name)
            return self, f"from: {_from} to: {to}"
            
        except Exception as err:

            logging.WARNING(f"Transition from {_from} state to {to} state for {self.name.value} is not allowed")

    @validate_types(size=int, output=None)
    def unsubscribe_to(self, tag:Tag):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if tag.name in self.__subscribed_to:

            self.__subscribed_to.pop(tag.name)

    @validate_types(output=int|float)
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
        return self.machine_interval.value

    @validate_types(interval=int|float, output=None)
    def set_interval(self, interval:int|float):
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
        self.machine_interval.value = interval

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
        This method is executed by state machine worker every state machine interval to execute the correct method according its state
        """
        method_name = f"while_{self.current_state.value}"

        if method_name in dir(self):

            method = getattr(self, method_name)
            method()            

    @validate_types(output=list)
    def get_states(self)->list[str]:
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

    @validate_types(output=dict)
    def get_serialized_models(self)->dict:
        r"""
        Gets class attributes defined by [model types]()

        **Returns**

        * **(dict)**
        """
        result = dict()
        props = self.__dict__
        
        for key, value in props.items():

            if isinstance(value, (StringType, FloatType, IntegerType, BooleanType)):

                result[key] = value.value

        return result

    @validate_types(output=dict)
    def serialize(self)->dict:
        r"""
        It provides the values of attributes defined with PyAutomation Models

        # Returns

        - dict: Serialized state machine
        """
        result = {
            "state": self.current_state.value
        }
        result.update(self.get_serialized_models())
        return result
    

class IAD(AutomationStateMachine):
    r"""Documentation here
    """
    def __init__(
            self,
            name="IAD",
            description:str="Instrument Anomaly Detection",
            classification:str="Service"
        ):

        super(IAD, self).__init__(
            name=name,
            description=description,
            classification=classification
            )
        
    def while_waiting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        super(IAD, self).while_waiting()

    def while_running(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        super(IAD, self).while_running()


class Filter(AutomationStateMachine):
    r"""Documentation here
    """
    def __init__(
            self,
            name="Filter",
            description:str="Gaussian an Process Filter",
            classification:str="Service"
        ):

        super(Filter, self).__init__(
            name=name,
            description=description,
            classification=classification
            )
        
    def while_waiting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        super(Filter, self).while_waiting()

    def while_running(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        super(Filter, self).while_running()
        pass


class LeakStateMachine(AutomationStateMachine):
    r"""Documentation here
    """

    pre_alarming = State('pre_alarm')  
    leaking = State('leak')
    switching = State('switch')
    not_available = State('not_available')
    con_restart = State('confirm_restart')
    con_reset = State('confirm_reset')

    #Transitions
    run_to_pre_alarm = AutomationStateMachine.running.to(pre_alarming)
    pre_alarm_to_run = pre_alarming.to(AutomationStateMachine.running)
    pre_alarm_to_leak = pre_alarming.to(leaking)
    leak_to_restart = leaking.to(AutomationStateMachine.restarting)
    leak_to_reset = leaking.to(AutomationStateMachine.resetting)

    reset_to_confirm_reset = AutomationStateMachine.resetting.to(con_reset)
    restart_to_confirm_restart = AutomationStateMachine.restarting.to(con_restart)
    confirm_restart_to_wait = con_restart.to(AutomationStateMachine.waiting)
    confirm_reset_to_start = con_reset.to(AutomationStateMachine.starting)
    confirm_restart_to_run = con_restart.to(AutomationStateMachine.running)
    confirm_restart_to_sleep = con_restart.to(AutomationStateMachine.sleeping)
    confirm_restart_to_test = con_restart.to(AutomationStateMachine.testing)
    confirm_reset_to_run = con_reset.to(AutomationStateMachine.running)
    confirm_reset_to_wait = con_reset.to(AutomationStateMachine.waiting)
    confirm_reset_to_sleep = con_reset.to(AutomationStateMachine.sleeping)
    confirm_reset_to_test = con_reset.to(AutomationStateMachine.testing)

    start_to_switch = AutomationStateMachine.starting.to(switching)
    wait_to_switch = AutomationStateMachine.waiting.to(switching)
    run_to_switch = AutomationStateMachine.running.to(switching)
    switch_to_not_available = switching.to(not_available)
    switch_to_restart = switching.to(AutomationStateMachine.restarting)
    switch_to_reset = switching.to(AutomationStateMachine.resetting)
    not_available_to_restart = not_available.to(AutomationStateMachine.restarting)
    not_available_to_reset = not_available.to(AutomationStateMachine.resetting)
    
    def __init__(
            self,
            name:str,
            description:str="",
            classification:str=""
        ):

        super(LeakStateMachine, self).__init__(
            name=name,
            description=description,
            classification=classification
            )
        
    def while_waiting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        super(LeakStateMachine, self).while_waiting()
        ready_to_run = True
        for _, value in self.data.items():

            if len(value)!=value.max_length:
                ready_to_run=False
                break

        if ready_to_run:

            self.send('wait_to_run')

    def while_running(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        super(LeakStateMachine, self).while_running()

    def while_pre_alarming(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2

    def while_leaking(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 3

    def while_resetting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 3
        self.send('reset_to_confirm_reset')

    def while_restarting(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 3
        self.send('restart_to_confirm_restart')

    def while_con_reset(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 4

    def while_con_restart(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 5

    def while_switching(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2

    def while_not_available(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 5

    # Transitions methods
    def on_run_to_pre_alarm(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2

    def on_pre_alarm_to_run(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 1

    def on_pre_alarm_to_leak(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 5

    def on_leak_to_restart(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 4

    def on_leak_to_reset(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 4

    def on_start_to_switch(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 3

    def on_wait_to_switch(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 3

    def on_run_to_switch(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 3

    def on_switch_to_not_available(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 4

    def on_switch_to_restart(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2

    def on_switch_to_reset(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2

    def on_not_available_to_restart(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2

    def on_not_available_to_reset(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.criticity.value = 2