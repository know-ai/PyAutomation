import logging, secrets
from datetime import datetime
from statemachine import State, StateMachine
from .workers.state_machine import StateMachineWorker
from .managers.state_machine import StateMachineManager
from .managers.opcua_client import OPCUAClientManager
from .managers.db import DBManager
from .singleton import Singleton
from .buffer import Buffer
from .models import StringType, IntegerType, FloatType, BooleanType, ProcessType
from .tags.cvt import CVTEngine, Tag
from .tags.tag import MachineObserver
from .opcua.subscription import DAS
from .modules.users.users import User
from .utils.decorators import set_event, validate_types, logging_error_handler
from .variables import VARIABLES
from .variables import (
    Temperature,
    Length,
    Current,
    Time,
    Pressure,
    Mass,
    Force,
    Power,
    VolumetricFlow,
    MassFlow,
    Density,
    Percentage,
    Adimentional)
from .logger.machines import MachinesLoggerEngine
from .logger.datalogger import DataLoggerEngine
from flask_socketio import SocketIO



class Machine(Singleton):
    r"""Documentation here
    """
    def __init__(self):

        self.machine_manager = StateMachineManager()
        self.machines_engine = MachinesLoggerEngine()
        self.logger_engine = DataLoggerEngine()
        self.db_manager = DBManager()
        self.state_worker = None

    def append_machine(self, machine:StateMachine, interval:FloatType=FloatType(1), mode:str='async'):
        r"""
        Append a state machine to the state machine manager.

        **Parameters:**

        * **machine** (`PyHadesStateMachine`): a state machine object.
        * **interval** (int): Interval execution time in seconds.
        """
        if isinstance(machine, DAQ):
            
            machine.name = StringType(f"DAQ-{int(interval.value * 1000)}")
        
        machine.set_interval(interval)
        self.machine_manager.append_machine((machine, interval, mode))
        
        if self.machines_engine.get_db():
            self.machines_engine.create(
                identifier=machine.identifier.value,
                name=machine.name.value,
                interval=interval.value,
                description=machine.description.value,
                classification=machine.classification.value,
                buffer_size=machine.buffer_size.value,
                buffer_roll_type=machine.buffer_roll_type.value,
                criticity=machine.criticity.value,
                priority=machine.priority.value
            )
            self.create_tag_internal_process_type(machine=machine)

    def drop(self, machine:StateMachine):
        r"""
        Documentation here
        """
        self.state_worker._async_scheduler.drop(machine=machine)

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

        return self.machine_manager.get_machine(name)

    def get_machines(self)->list:
        r"""
        Returns all defined PyHades state machines.

        **Returns** (list)

        Usage

        ```python
        >>> state_machines = app.get_machines()
        ```
        """

        return self.machine_manager.get_machines()

    def get_state_machine_manager(self)->StateMachineManager:
        r"""
        Gets state machine Manager

        **Returns:** StateMachineManager instance

        ```python
        >>> state_manager = app.get_state_machine_manager()
        ```
        """
        return self.machine_manager

    def start(self, machines:tuple=None):
        r"""
        Starts statemachine worker
        """
        # StateMachine Worker
        config = None
        if self.machines_engine.get_db():
            config = self.load_db_machines_config()

        if config:

            if machines:

                for machine in machines:

                    if machine.name.value in config:

                        machine.description.value = config[machine.name.value]["description"]
                        machine.classification.value = config[machine.name.value]["classification"]
                        machine.buffer_size.value = config[machine.name.value]["buffer_size"]
                        machine.buffer_roll_type.value = config[machine.name.value]["buffer_roll_type"]
                        machine.criticity.value = config[machine.name.value]["criticity"]
                        machine.priority.value = config[machine.name.value]["priority"]
                        machine.identifier.value = config[machine.name.value]['identifier']
                        self.append_machine(machine=machine, interval=FloatType(config[machine.name.value]["interval"]))
                    
                    else:
                        
                        self.append_machine(machine=machine, interval=FloatType(machine.get_interval()))

        else:

            if machines:
                
                for machine in machines:

                    self.append_machine(machine=machine, interval=FloatType(machine.get_interval()))

        state_manager = self.get_state_machine_manager()
        
        if state_manager.exist_machines():
            
            self.state_worker = StateMachineWorker(state_manager)
            self.state_worker.daemon = True
            self.state_worker.start()

    def load_db_machines_config(self):

        return self.machines_engine.read_config()

    def join(self, machine):

        self.state_worker._async_scheduler.join(machine)

    def create_tag_internal_process_type(self, machine:StateMachine):
        r"""
        Documentation here
        """
        cvt = CVTEngine()
        internal_variables = machine.get_internal_process_type_variables()
        for _tag_name, value in internal_variables.items():

            for variable, units in VARIABLES.items():

                if value.unit in units.values() or value.unit in units.keys():

                    tag_name = f"{_tag_name}_{machine.name.value}"
                    cvt.set_tag(
                        name=tag_name,
                        unit=value.unit,
                        data_type="float",
                        variable=variable,
                        description=f"process type variable"
                    )
                    # Persist Tag on Database
                    tag = cvt.get_tag_by_name(name=tag_name)
                    attr = getattr(machine, _tag_name)
                    attr.tag = tag
                    self.logger_engine.set_tag(tag=tag)
                    self.db_manager.attach(tag_name=tag_name)
                    break

    def create_process_variable_into_db_bound_field_data(self, machine:StateMachine):
        r"""
        Documentation here
        """
        pass

    @logging_error_handler
    def stop(self):
        r"""
        Safe stop workers execution
        """
        if self.state_worker:

            self.state_worker.stop()


class StateMachineCore(StateMachine):
    r"""
    Documentation here
    """

    starting = State('start', initial=True)
    waiting = State('wait')
    running = State('run')
    restarting = State("restart")
    resetting = State('reset')

    # Transitions
    start_to_wait = starting.to(waiting)
    wait_to_run = waiting.to(running)
    run_to_reset = running.to(resetting)
    reset_to_start = resetting.to(starting)
    run_to_restart = running.to(restarting)
    restart_to_wait = restarting.to(waiting)
    wait_to_reset = waiting.to(resetting)
    wait_to_restart = waiting.to(restarting)

    def __init__(
            self,
            name:str,
            description:str="",
            classification:str="",
            interval:float=1.0,
            identifier:str=None
        ):
        _identifier = secrets.token_hex(4)
        
        if identifier:

            _identifier = identifier

        self.identifier = StringType(default=_identifier)
        self.criticity = IntegerType(default=2)
        self.priority = IntegerType(default=1)
        self.description = StringType(default=description)
        self.classification = StringType(default=classification)
        self.name = StringType(default=name)
        self.machine_interval = FloatType(default=interval)
        self.buffer_size = IntegerType(default=10)
        self.buffer_roll_type = StringType(default='backward')
        self.sio:SocketIO|None = None
        self.restart_buffer()
        self.machine_engine = MachinesLoggerEngine()
        transitions = []
        for state in self.states:
            transitions.extend(state.transitions)
        self.transitions = transitions
        super(StateMachineCore, self).__init__()

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

        if self.data:

            for _, value in self.data.items():

                if len(value) < value.size:
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

    # Auxiliaries Methods 
    def set_socketio(self, sio:SocketIO):

        self.sio:SocketIO = sio

    def put_attr(self, attr_name:str, value:StringType|FloatType|IntegerType|BooleanType|ProcessType, user:User=None):
        
        attr = getattr(self, attr_name)
        attr.set_value(value=value, user=user, name=attr_name)
        kwargs = {
            f"{attr_name}": value
        }

        # Update on DB
        self.machine_engine.put(name=self.name, **kwargs)

    def add_process_variable(self, name:str, tag:Tag, read_only:bool=False):
        r"""
        Documentation here
        """
        
        props = self.__dict__
        if name not in props.items():
            process_variable = ProcessType(tag=Tag, default=tag.value, read_only=read_only)
            setattr(self, name, process_variable)
            self.machine_engine.bind_tag(tag=tag, machine=self)

    def get_process_variables(self):
        r"""
        Documentation here
        """

        result = dict()
        props = self.__dict__
        
        for key, value in props.items():

            if isinstance(value, ProcessType):

                result[key] = value.serialize()

        return result

    def get_process_variable(self, name:str):
        r"""
        Documentation here
        """
        props = self.__dict__
        if name in props.items():

            value = props[name]
            if isinstance(value, ProcessType):

                return value.serialize()

    @validate_types(size=int, output=None)
    def set_buffer_size(self, size:int, user:User=None)->None:
        r"""
        Set data buffer size

        # Parameters

        - *size:* [int] buffer size
        """
        self.buffer_size.value = size
        self.restart_buffer()

    def restart_buffer(self):
        r"""
        Restart Buffer
        """
        self.data = {tag_name: Buffer(size=self.buffer_size.value, roll=self.buffer_roll_type.value) for tag_name, _ in self.get_subscribed_tags().items()}

    @validate_types(output=dict)
    def get_subscribed_tags(self)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        result = dict()
        props = self.__dict__
        
        for name, value in props.items():

            if isinstance(value, ProcessType):

                if value.read_only and value.tag:

                    result[value.tag.name] = value

        return result
    
    @validate_types(output=dict)
    def get_not_subscribed_tags(self)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        result = dict()
        props = self.__dict__
        
        for name, value in props.items():

            if isinstance(value, ProcessType):
                
                if value.read_only and not value.tag:

                    result[name] = value

        return result
    
    def subscribe_to(self, tag:Tag, default_tag_name:str=None):
        r"""

        # Parameters

        - *tags:* [list] 
        """
        if default_tag_name and tag:    # Designed to default tags into State Machine

            if self.process_type_exists(name=default_tag_name):
                
                if default_tag_name in self.get_not_subscribed_tags():

                    process_type = getattr(self, default_tag_name)

                    if not process_type.tag:

                        process_type.tag = tag
                        self.attach(machine=self, tag=tag)
                        self.restart_buffer()
                        self.machine_engine.bind_tag(tag=tag, machine=self, default_tag_name=default_tag_name)
                        return True, f"successful subscription"
                    
                    return False, f"{default_tag_name} already has a subscription"
                
                return False, f"{default_tag_name} already has a subscription"
        
            return False, f"{default_tag_name} is not a Process Type Variable"

        elif tag and not default_tag_name:
            
            tag_name = tag.get_name()
            
            if tag_name not in self.get_subscribed_tags():

                if not self.process_type_exists(name=tag_name):

                    setattr(self, tag_name, ProcessType(tag=tag, default=tag.value, read_only=True))
                    self.attach(machine=self, tag=tag)
                    self.restart_buffer()
                    self.machine_engine.bind_tag(tag=tag, machine=self)
                    return True
                
                else:

                    process_type = getattr(self, tag_name)

                    if not process_type.tag:

                        process_type.tag = tag
                        self.machine_engine.bind_tag(tag=tag, machine=self)
                        return True

    @validate_types(tag=Tag, output=None|bool)
    def unsubscribe_to(self, tag:Tag=None, default_tag_name:str=None):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if tag:
            tags_subscribed = self.get_subscribed_tags()
            if tag.name in tags_subscribed:
                self.machine_engine.unbind_tag(tag=tag, machine=self)
                tags_subscribed[tag.name].tag = None
                self.restart_buffer()
                return True
            
        # elif default_tag_name: # Default tags on leak state machine

        #     if default_tag_name in self.get_subscribed_tags():
        #         process_type = self.get_subscribed_tags[default_tag_name]
        #         tag = process_type.tag
        #         tags_subscribed[tag.name].tag
        #         self.restart_buffer()
        #         self.machine_engine.unbind_tag(tag=tag, machine=self)
        #         return True

    @validate_types(name=str, output=bool)
    def process_type_exists(self, name:str)->bool:

        props = self.__dict__
        if name in props:

            if isinstance(props[name], ProcessType):

                return True
            
        return False
    
    @validate_types(output=dict)
    def get_internal_process_type_variables(self)->dict:

        result = dict()
        props = self.__dict__
        
        for name, value in props.items():

            if isinstance(value, ProcessType):

                if not value.read_only:

                    result[name] = value

        return result

    @validate_types(
            tag=str, 
            value=Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow|MassFlow|Density|Percentage|Adimentional, 
            timestamp=datetime, 
            output=None)
    def notify(
        self, 
        tag:str, 
        value:Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow|MassFlow|Density|Percentage|Adimentional, 
        timestamp:datetime):
        r"""
        This method provide an interface to CVT to notify if tag value has change
        
        # Parameters

        - *tag:* [Tag] tag Object
        - *value:* [int|float|bool] tag value
        """
        subscribed_to = self.get_subscribed_tags()

        if tag in subscribed_to:
            process_type = subscribed_to[tag]
            # attr = getattr(self, tag.name)
            value = value.convert(to_unit=process_type.tag.get_display_unit())
            # attr.value = value
            # IMPORTANTE A CAMBIAR SEGUN LA UNIDAD QUE NECESITEN LOS MODELOS
            self.data[tag](value)

    @logging_error_handler
    def attach(self, machine, tag:Tag):
        cvt = CVTEngine()
        def attach_observer(machine, tag:Tag):

            observer = MachineObserver(machine)
            query = dict()
            query["action"] = "attach_observer"
            query["parameters"] = {
                "name": tag.name,
                "observer": observer,
            }
            cvt.request(query)
            cvt.response()

        attach_observer(machine, tag)

    @set_event(message=f"Switched", classification="State Machine", priority=2, criticity=3)
    @validate_types(to=str, user=User|type(None), output=tuple)
    def transition(self, to:str, user:User=None):
        r"""
        Documentation here
        """
        try:
            _from = self.current_state.name.lower()
            transition_name = f'{_from}_to_{to}'
            allowed_transitions = self._get_active_transitions()
            for _transition in allowed_transitions:
                if f"{_transition.source.name}_to_{_transition.target.name}"==transition_name:
                    self.send(transition_name)
                    return self, f"from: {_from} to: {to}"
                
            return None, f"Transition to {to} not allowed"
            
        except Exception as err:

            logger = logging.getLogger("pyautomation")
            logger.warning(f"Transition from {_from} state to {to} state for {self.name.value} is not allowed")

    @validate_types(output=int|float)
    def get_interval(self)->int|float:
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

    @validate_types(interval=IntegerType|FloatType, user=User|type(None), output=None)
    def set_interval(self, interval:IntegerType|FloatType, user:User=None):
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

    def get_allowed_actions(self):
        r"""Documentation here
        """
        result = list()

        current_state = self.current_state
        transitions = self.transitions

        for transition in transitions:

            if transition.source == current_state:
                if transition.target.name not in ("run", "switch", "wait", "start"):
                    result.append(transition.target.name)
                    if "confirm" in transition.target.name:

                        result.append(transition.target.name.replace("confirm", "deny"))

                    # if current_state.value.lower() in ("con_restart", "con_reset"):

                    #     result.append(current_state.value.lower().replace("con_", "confirm_"))
                    #     result.append(current_state.value.lower().replace("con_", "deny_"))

        return result

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
                logging.error(f"Machine - {self.name.value}:{error}")

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

            if isinstance(value, (StringType, FloatType, IntegerType, BooleanType, ProcessType)):

                if isinstance(value, ProcessType):

                    result[key] = value.serialize()

                else:

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
            "state": self.current_state.value,
            "actions": self.get_allowed_actions()
        }
        result.update(self.get_serialized_models())
        
        return result
    
    # TRANSITIONS
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

    # ON ENTER TRANSITION
    def on_enter_starting(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())

    def on_enter_waiting(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())

    def on_enter_running(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())

    def on_enter_restarting(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())

    def on_enter_resetting(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())


class DAQ(StateMachineCore):
    r"""
    Documentation here
    """    

    def __init__(
            self,
            name:str="DAQ",
            description:str="",
            classification:str="Data Acquisition System"
        ):

        self.das = DAS()
        self.cvt = CVTEngine()

        if isinstance(name, StringType):

            name = name.value

        super(DAQ, self).__init__(
            name=name,
            description=description,
            classification=classification
            )
        
    # State Methods
    def while_waiting(self):
        r"""
        This method is executed every machine loop when it is on Wait state

        It was designed to check your buffer data in self.data, if your buffer is full, so they pass to run state
        """
        self.send('wait_to_run')

    def while_running(self):
        from . import SEGMENT, MANUFACTURER
        for tag_name, process_type in self.get_subscribed_tags().items():
            tag = process_type.tag
            namespace = tag.get_node_namespace()
            opcua_address = tag.get_opcua_address()
            values = self.opcua_client_manager.get_node_value_by_opcua_address(opcua_address=opcua_address, namespace=namespace)
            if values:
                data_value = values[0][0]["DataValue"]
                value = data_value.Value.Value
                timestamp = data_value.SourceTimestamp
                val = tag.value.convert_value(value=value, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
                tag.value.set_value(value=val, unit=tag.get_display_unit()) 
                if tag.manufacturer==MANUFACTURER and tag.segment==SEGMENT:      
                    self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
                elif not MANUFACTURER and not SEGMENT:
                    self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
                # self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
                self.das.buffer[tag_name]["timestamp"](timestamp)
                self.das.buffer[tag_name]["values"](val)

        super().while_running()

    # Auxiliaries Methods
    def set_opcua_client_manager(self, manager:OPCUAClientManager):
        r"""
        Documentation here
        """
        self.opcua_client_manager = manager
    

class AutomationStateMachine(StateMachineCore):
    r"""
    Documentation here
    """
    # States
    testing = State('test')
    sleeping = State('sleep')

    # Transitions
    test_to_restart = testing.to(StateMachineCore.restarting)
    sleep_to_restart = sleeping.to(StateMachineCore.restarting)
    test_to_reset = testing.to(StateMachineCore.resetting)
    sleep_to_reset = sleeping.to(StateMachineCore.resetting)
    run_to_test = StateMachineCore.running.to(testing)
    wait_to_test = StateMachineCore.waiting.to(testing)
    run_to_sleep = StateMachineCore.running.to(sleeping)
    wait_to_sleep = StateMachineCore.waiting.to(sleeping)
    

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

    # Transitions
    def on_test_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Test state 
        """
        self.last_state = "test"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_test_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Test state 
        """
        self.last_state = "test"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_sleep_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Sleep state 
        """
        self.last_state = "sleep"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_sleep_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Sleep state 
        """
        self.last_state = "sleep"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_enter_sleeping(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())

    def on_enter_testing(self):

        if self.sio:

            self.sio.emit("on.machine", data=self.serialize())


