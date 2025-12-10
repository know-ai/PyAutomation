import logging, secrets, pytz
from datetime import datetime
from opcua import Server, ua, Node
from hashlib import blake2b
from statemachine import State, StateMachine
from .workers.state_machine import StateMachineWorker
from .managers.state_machine import StateMachineManager
from .managers.opcua_client import OPCUAClientManager
from .managers.alarms import AlarmManager
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
    Volume,
    MassFlow,
    Density,
    Percentage,
    Adimentional)
from .logger.machines import MachinesLoggerEngine
from .logger.datalogger import DataLoggerEngine
from .logger.alarms import AlarmsLoggerEngine
from flask_socketio import SocketIO



class Machine(Singleton):
    r"""
    Singleton class that manages the lifecycle and execution of all state machines in the system.

    It handles the registration, starting, stopping, and configuration of state machines,
    including Data Acquisition (DAQ) machines and OPC UA Servers.
    """
    def __init__(self):

        self.machine_manager = StateMachineManager()
        self.machines_engine = MachinesLoggerEngine()
        self.logger_engine = DataLoggerEngine()
        self.db_manager = DBManager()
        self.alarm_manager = AlarmManager()
        self.alarms_engine = AlarmsLoggerEngine()
        self.state_worker = None

    def append_machine(self, machine:StateMachine, interval:FloatType=FloatType(1), mode:str='async'):
        r"""
        Registers a new state machine to be managed by the system.

        **Parameters:**

        * **machine** (StateMachine): The state machine instance.
        * **interval** (FloatType): Execution interval in seconds.
        * **mode** (str): Execution mode ('async' or 'sync'). Default is 'async'.
        """
        if isinstance(machine, DAQ):
            
            machine.name = StringType(f"DAQ-{int(interval.value * 1000)}")
        
        machine.set_interval(interval)
        self.machine_manager.append_machine((machine, interval, mode))
        on_delay = None
        if hasattr(machine, "on_delay"):
            on_delay = machine.on_delay.value
        threshold = None
        if hasattr(machine, "threshold"):
            threshold = machine.threshold.value
        
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
                priority=machine.priority.value,
                on_delay=on_delay,
                threshold=threshold
            )
            self.create_tag_internal_process_type(machine=machine)

    def drop(self, machine:StateMachine):
        r"""
        Removes a state machine from execution.

        **Parameters:**

        * **machine** (StateMachine): The machine instance to remove.
        """
        self.state_worker._async_scheduler.drop(machine=machine)

    def get_machine(self, name:str):
        r"""
        Retrieves a registered state machine by its name.

        **Parameters:**

        * **name** (str): The name of the state machine.

        **Returns:**

        * **StateMachine**: The machine instance if found, otherwise None.

        **Usage:**

        ```python
        >>> machine = app.get_machine('MyMachine')
        ```
        """

        return self.machine_manager.get_machine(name)

    def get_machines(self)->list:
        r"""
        Retrieves all registered state machines.

        **Returns:**

        * **list**: A list of tuples containing (Machine, Interval, Mode).

        **Usage:**

        ```python
        >>> machines = app.get_machines()
        ```
        """

        return self.machine_manager.get_machines()

    def get_state_machine_manager(self)->StateMachineManager:
        r"""
        Returns the internal StateMachineManager instance.

        **Returns:**

        * **StateMachineManager**: The manager instance.
        """
        return self.machine_manager

    def start(self, machines:tuple=None):
        r"""
        Initializes and starts the main StateMachineWorker.

        It loads configuration from the database (if available) or uses the provided machines list.

        **Parameters:**

        * **machines** (tuple, optional): A tuple of StateMachine instances to start immediately.
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
                        if config[machine.name.value]['on_delay']:
                            machine.on_delay.value = config[machine.name.value]['on_delay']
                        if config[machine.name.value]['threshold']:
                            threshold_value = config[machine.name.value]['threshold']
                            threshold_unit = machine.threshold.unit
                            class_name = machine.threshold.value.__class__.__name__
                            machine.threshold.value = eval(f"{class_name}({threshold_value}, unit='{threshold_unit}')")
                            if "leak detection" in machine.classification.value.lower():

                                if machine.name.value.lower() == "npw":

                                    machine.wavelet.threshold_iqr = threshold_value
                                    
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
        r"""
        Reads machine configurations from the database.
        """
        return self.machines_engine.read_config()

    def join(self, machine):
        r"""
        Adds a machine to the running scheduler safely.
        """
        self.state_worker._async_scheduler.join(machine)

    def create_tag_internal_process_type(self, machine:StateMachine):
        r"""
        Automatically creates CVT tags for internal process variables defined in the state machine.

        This allows internal variables of a state machine to be exposed as tags in the system.

        **Parameters:**

        * **machine** (StateMachine): The machine instance.
        """
        from . import SEGMENT, MANUFACTURER
        cvt = CVTEngine()
        internal_variables = machine.get_internal_process_type_variables()
        for _tag_name, value in internal_variables.items():

            for variable, units in VARIABLES.items():

                if value.unit in units.values() or value.unit in units.keys():

                    tag_name = f"{machine.name.value}.{_tag_name}"
                    cvt.set_tag(
                        name=tag_name,
                        unit=value.unit,
                        data_type="float",
                        variable=variable,
                        description=f"process type variable",
                        segment=SEGMENT,
                        manufacturer=MANUFACTURER
                    )
                    # Persist Tag on Database
                    tag = cvt.get_tag_by_name(name=tag_name)
                    attr = getattr(machine, _tag_name)
                    attr.tag = tag
                    self.logger_engine.set_tag(tag=tag)
                    self.db_manager.attach(tag_name=tag_name)
                    break

        internal_variables = machine.get_read_only_process_type_variables()
        for _tag_name, value in internal_variables.items():
            for variable, units in VARIABLES.items():

                if value.unit in units.values() or value.unit in units.keys():
                    
                    if hasattr(machine, "internal_tags_relationships"):
                        tag_name = f"{machine.internal_tags_relationships[_tag_name]['tag']}"
                        if SEGMENT:
                            tag_name = f"{SEGMENT}.{tag_name}"
                        if MANUFACTURER:
                            tag_name = f"{MANUFACTURER}.{tag_name}"
                        description = machine.internal_tags_relationships[_tag_name]['description']

                        attr = getattr(machine, _tag_name)
                        unit = attr.unit
                        tag, _ = cvt.set_tag(
                            name=tag_name,
                            unit=unit,
                            data_type="float",
                            variable=variable,
                            description=description,
                            segment=SEGMENT,
                            manufacturer=MANUFACTURER,
                            out_of_range_detection=True,
                            frozen_data_detection=True,
                            outlier_detection=True
                        )

                        if tag:
                            # Persist Tag on Database
                            tag = cvt.get_tag_by_name(name=tag_name)
                            attr = getattr(machine, _tag_name)
                            attr.tag = tag
                            self.logger_engine.set_tag(tag=tag)
                            self.db_manager.attach(tag_name=tag_name)
                            break 
            
            self.__define_iad_alarms()
             
    def create_alarm(
            self,
            name:str,
            tag:str,
            alarm_type:str="BOOL",
            trigger_value:bool|float|int=True,
            description:str="",
            identifier:str=None,
            state:str="Normal",
            timestamp:str=None,
            ack_timestamp:str=None,
            user:User=None,
            reload:bool=False
        ):
        r"""
        Creates and registers an alarm in the Alarm Manager.

        **Parameters:**

        * **name** (str): Alarm name.
        * **tag** (str): Associated tag name.
        * **alarm_type** (str): Type of alarm (e.g., 'BOOL', 'HIGH', 'LOW').
        * **trigger_value** (bool|float|int): Value that triggers the alarm.
        * **description** (str): Alarm description.
        * **reload** (bool): If True, forces reload/update.

        **Returns:**

        * **tuple**: (Alarm object, Message string).
        """
        alarm, message = self.alarm_manager.append_alarm(
            name=name,
            tag=tag,
            type=alarm_type,
            trigger_value=trigger_value,
            description=description,
            identifier=identifier,
            state=state,
            timestamp=timestamp,
            ack_timestamp=ack_timestamp,
            user=user,
            reload=reload,
        )

        if alarm:

            # Persist Tag on Database
            if not reload:
                if self.db_manager.get_db():
                    
                    alarm = self.alarm_manager.get_alarm_by_name(name=name)
                    
                    self.alarms_engine.create(
                        id=alarm.identifier,
                        name=name,
                        tag=tag,
                        trigger_type=alarm_type,
                        trigger_value=trigger_value,
                        description=description
                    )
            
            return alarm, message

        return None, message          

    def __define_iad_alarms(self):
        r"""
        Automatically defines alarms for Intelligent Anomaly Detection (IAD) features
        (frozen data, out of range, outliers) based on tag configuration.
        """
        cvt = CVTEngine()
        tags = cvt.get_tags()
        for tag in tags:
            
            if tag['frozen_data_detection'] or tag['out_of_range_detection'] or tag['outlier_detection']:

                    alarm_name = f"alarm.{tag['name']}.iad"
                    self.create_alarm(name=alarm_name, tag=tag['name'])

    @logging_error_handler
    def stop(self):
        r"""
        Safe stop of all state machine workers.
        """
        if self.state_worker:

            self.state_worker.stop()


class StateMachineCore(StateMachine):
    r"""
    Base class for all state machines in PyAutomation.
    
    It defines the standard lifecycle states:
    * **Start**: Initialization state.
    * **Wait**: Waiting for data or conditions.
    * **Run**: Main execution logic.
    * **Reset**: Resetting variables or states.
    * **Restart**: Restarting the machine cycle.
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
            identifier:str=None,
            buffer_size:int=10
        ):
        from . import SEGMENT, MANUFACTURER
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
        self.buffer_size = IntegerType(default=buffer_size)
        self.buffer_roll_type = StringType(default='backward')
        self.sio:SocketIO|None = None
        self.restart_buffer()
        self.machine_engine = MachinesLoggerEngine()
        transitions = []
        for state in self.states:
            transitions.extend(state.transitions)
        self.transitions = transitions
        self.manufacturer = MANUFACTURER
        self.segment = SEGMENT
        self.mass_flow_unit_base = "kg/sec"
        self.volumetric_flow_unit_base = "m3/sec"
        super(StateMachineCore, self).__init__()

    # State Methods
    def while_starting(self):
        r"""
        Executed every machine loop while in **Start** state.
        
        Default behavior:
        1. Initialize buffer size.
        2. Transition to **Wait** state.
        """
        # DEFINE DATA BUFFER
        self.set_buffer_size(size=self.buffer_size.value)
        # TRANSITION
        self.send('start_to_wait')

    def while_waiting(self):
        r"""
        Executed every machine loop while in **Wait** state.
        
        Default behavior:
        1. Checks if internal buffers for subscribed tags are full.
        2. If full, transitions to **Run** state.
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
        Executed every machine loop while in **Run** state.
        
        **Note:** This method should be overridden by child classes to implement custom logic.
        """
        self.criticity.value = 1

    def while_resetting(self):
        r"""
        Executed every machine loop while in **Reset** state.
        
        Default behavior: Transition to **Start** state.
        """
        self.send("reset_to_start")

    def while_restarting(self):
        r"""
        Executed every machine loop while in **Restart** state.
        
        Default behavior:
        1. Clear buffers.
        2. Transition to **Wait** state.
        """
        self.restart_buffer()
        self.send("restart_to_wait")

    # Auxiliaries Methods 
    def set_socketio(self, sio:SocketIO):

        self.sio:SocketIO = sio

    def put_attr(self, attr_name:str, value:StringType|FloatType|IntegerType|BooleanType|ProcessType, user:User=None):
        r"""
        Updates an attribute of the state machine and persists it to the database.

        **Parameters:**

        * **attr_name** (str): Attribute name.
        * **value**: New value.
        * **user** (User): User performing the action.
        """
        attr = getattr(self, attr_name)
        attr.set_value(value=value, user=user, name=attr_name)
        kwargs = {
            f"{attr_name}": value
        }

        # Update on DB
        self.machine_engine.put(name=self.name, **kwargs)

    def add_process_variable(self, name:str, tag:Tag, read_only:bool=False):
        r"""
        Registers a process variable (ProcessType) dynamically.

        **Parameters:**

        * **name** (str): Variable name.
        * **tag** (Tag): Associated tag.
        * **read_only** (bool): If True, the variable cannot be modified by the machine logic (input only).
        """
        
        props = self.__dict__
        if name not in props.items():
            process_variable = ProcessType(tag=Tag, default=tag.value, read_only=read_only)
            setattr(self, name, process_variable)
            self.machine_engine.bind_tag(tag=tag, machine=self)

    def get_process_variables(self):
        r"""
        Retrieves all ProcessType variables defined in the machine.

        **Returns:**

        * **dict**: Serialized process variables.
        """

        result = dict()
        props = self.__dict__
        
        for key, value in props.items():

            if isinstance(value, ProcessType):

                result[key] = value.serialize()

        return result

    def get_process_variable(self, name:str):
        r"""
        Retrieves a specific ProcessType variable by name.

        **Parameters:**

        * **name** (str): Variable name.

        **Returns:**

        * **dict**: Serialized process variable.
        """
        props = self.__dict__
        if name in props.items():

            value = props[name]
            if isinstance(value, ProcessType):

                return value.serialize()

    @validate_types(size=int, output=None)
    def set_buffer_size(self, size:int, user:User=None)->None:
        r"""
        Sets the size of the data buffer for input variables.

        **Parameters:**

        * **size** (int): New buffer size.
        """
        self.buffer_size.value = size
        self.restart_buffer()

    def restart_buffer(self):
        r"""
        Clears and reinitializes data buffers for all subscribed tags.
        """
        self.data = {tag_name: Buffer(size=self.buffer_size.value, roll=self.buffer_roll_type.value) for tag_name, _ in self.get_subscribed_tags().items()}

    @validate_types(output=dict)
    def get_subscribed_tags(self)->dict:
        r"""
        Returns tags that this machine is subscribed to (inputs).

        **Returns:**

        * **dict**: Dictionary of subscribed ProcessType variables.
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
        r"""
        Returns ProcessType variables that are waiting for a tag subscription.

        **Returns:**

        * **dict**: Dictionary of unsubscribed variables.
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
        Subscribes the machine to a tag.

        If `default_tag_name` is provided, it attempts to map the tag to that specific internal variable.
        Otherwise, it automatically maps to a matching variable or creates a new one.

        **Parameters:**

        * **tag** (Tag): The tag to subscribe.
        * **default_tag_name** (str, optional): Internal variable name target.

        **Returns:**

        * **tuple**: (Success bool, Message str) or True/False.
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
        r"""
        Unsubscribes the machine from a tag.

        **Parameters:**

        * **tag** (Tag, optional): The tag object to unsubscribe.
        * **default_tag_name** (str, optional): The internal variable name.
        """
        if tag:

            tags_subscribed = self.get_subscribed_tags()
            
            if tag.name in tags_subscribed:
               
                self.machine_engine.unbind_tag(tag=tag, machine=self)
                tags_subscribed[tag.name].tag = None
                self.restart_buffer()
                return True
            
        elif default_tag_name: # Default tags on leak state machine

            if default_tag_name in self.get_subscribed_tags():
                
                process_type = self.get_subscribed_tags[default_tag_name]
                tag = process_type.tag
                tags_subscribed[tag.name].tag = None
                self.restart_buffer()
                self.machine_engine.unbind_tag(tag=tag, machine=self)
                return True

    @validate_types(name=str, output=bool)
    def process_type_exists(self, name:str)->bool:
        r"""
        Checks if a ProcessType variable exists in the machine.
        """
        props = self.__dict__
        if name in props:

            if isinstance(props[name], ProcessType):

                return True
            
        return False
    
    @validate_types(output=dict)
    def get_internal_process_type_variables(self)->dict:
        r"""
        Returns ProcessType variables that are NOT read-only (internal state variables).
        """
        result = dict()
        props = self.__dict__
        
        for name, value in props.items():

            if isinstance(value, ProcessType):

                if not value.read_only:

                    result[name] = value

            # if isinstance(value, (IntegerType, StringType, FloatType)):
                
            #     result[name] = value

        return result
    
    def get_read_only_process_type_variables(self)->dict:
        r"""
        Returns ProcessType variables that ARE read-only (inputs).
        """
        result = dict()
        props = self.__dict__
        
        for name, value in props.items():

            if isinstance(value, ProcessType):

                if value.read_only:

                    result[name] = value

        return result

    @validate_types(
            tag=str, 
            value=Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow|Volume|MassFlow|Density|Percentage|Adimentional, 
            timestamp=datetime, 
            output=None)
    def notify(
        self, 
        tag:str, 
        value:Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow|Volume|MassFlow|Density|Percentage|Adimentional, 
        timestamp:datetime):
        r"""
        Callback method called by the CVT when a subscribed tag changes its value.
        
        It updates the internal variable value and timestamps.

        **Parameters:**

        * **tag** (str): Tag name.
        * **value**: New value object (Process Variable).
        * **timestamp**: Timestamp of the change.
        """
        subscribed_to = self.get_subscribed_tags()

        if tag in subscribed_to:

            process_type = subscribed_to[tag]
            if process_type.tag.variable.lower()=="massflow":
                value.change_unit(unit=self.mass_flow_unit_base)
            elif process_type.tag.variable.lower()=="volumetricflow":
                value.change_unit(unit=self.volumetric_flow_unit_base)
            else:
                value.change_unit(unit=process_type.tag.display_unit)
            process_type.value = value
            self.data_timestamp = timestamp
            if hasattr(self, "verify_inputs"):
                self.verify_inputs()

    @logging_error_handler
    def attach(self, machine, tag:Tag):
        r"""
        Attaches the machine as an observer to a tag in the CVT.
        """
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
        Executes a manual transition to a target state.

        **Parameters:**

        * **to** (str): Target state name.
        * **user** (User, optional): User requesting the transition.

        **Returns:**

        * **tuple**: (Self, Message) if successful, (None, Error) otherwise.
        """
        try:
            _from = self.current_state.name.lower()
            transition_name = f'{_from}_to_{to}'
            allowed_transitions = self._get_active_transitions()
            for _transition in allowed_transitions:
                if f"{_transition.source.name}_to_{_transition.target.name}"==transition_name:
                    self.send(transition_name)
                    return self, f"[{self.name.value}] from: {_from} to: {to}"
                
            return None, f"Transition to {to} not allowed"
            
        except Exception as err:

            logger = logging.getLogger("pyautomation")
            logger.warning(f"Transition from {_from} state to {to} state for {self.name.value} is not allowed")

    @validate_types(output=int|float)
    def get_interval(self)->int|float:
        r"""
        Gets overall state machine interval
        
        **Returns**
        
        * **(float)** execution interval in seconds.
        """
        return self.machine_interval.value

    @validate_types(interval=IntegerType|FloatType, user=User|type(None), output=None)
    def set_interval(self, interval:IntegerType|FloatType, user:User=None):
        r"""
        Sets overall machine interval

        **Parameters**

        * **interval:** (float) execution interval in seconds.
        """        
        self.machine_interval = interval

    def get_allowed_actions(self):
        r"""
        Returns a list of allowed target states for transitions from the current state.
        
        Used for UI controls.
        """
        result = set()

        current_state = self.current_state
        transitions = self.transitions

        for transition in transitions:

            if transition.source == current_state:

                if transition.target.name not in ("run", "switch", "wait", "start", "pre_alarm"):

                    result.add(transition.target.name)

                    if "confirm" in transition.target.name:

                        result.add(transition.target.name.replace("confirm", "deny"))

                if current_state.value.lower() in ("con_restart", "con_reset"):

                    result.add(current_state.value.lower().replace("con_", "confirm_"))
                    result.add(current_state.value.lower().replace("con_", "deny_"))

        return list(result)

    def _get_active_transitions(self):
        r"""
        Gets allowed transitions based on the current state.
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
        Checks transition triggers and executes them if conditions are met.
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
        Main execution loop called by the worker thread.
        
        It dynamically calls the `while_<state>` method corresponding to the current state.
        """
        method_name = f"while_{self.current_state.value}"

        if method_name in dir(self):

            method = getattr(self, method_name)
            method()            

    @validate_types(output=list)
    def get_states(self)->list[str]:
        r"""
        Gets a list of all defined state names.

        **Returns**

        * **list**: List of state names strings.
        """
        return [state.value for state in self.states]

    @validate_types(output=dict)
    def get_serialized_models(self)->dict:
        r"""
        Serializes the machine's model attributes (properties defined with PyAutomation types).
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
        Serializes the entire state machine state and configuration.

        **Returns**

        * **dict**: Serialized machine data.
        """
        result = {
            "state": self.current_state.value,
            "actions": self.get_allowed_actions(),
            "manufacturer": self.manufacturer,
            "segment": self.segment
        }
        result.update(self.get_serialized_models())
        
        return result
    
    # TRANSITIONS
    def on_start_to_wait(self):
        r"""
        Transition action: Start -> Wait.
        """
        self.last_state = "start"
        self.criticity.value = 1

    def on_wait_to_run(self):
        r"""
        Transition action: Wait -> Run.
        """
        self.last_state = "wait"
        self.criticity.value = 1

    def on_wait_to_restart(self):
        r"""
        Transition action: Wait -> Restart.
        """
        self.last_state = "wait"
        self.criticity.value = 5

    def on_wait_to_reset(self):
        r"""
        Transition action: Wait -> Reset.
        """
        self.last_state = "wait"
        self.criticity.value = 5

    def on_run_to_restart(self):
        r"""
        Transition action: Run -> Restart.
        """
        self.last_state = "run"
        self.criticity.value = 5

    def on_run_to_reset(self):
        r"""
        Transition action: Run -> Reset.
        """
        self.last_state = "run"
        self.criticity.value = 5

    def on_reset_to_start(self):
        r"""
        Transition action: Reset -> Start.
        """
        self.last_state = "reset"
        self.criticity.value = 2

    def on_restart_to_wait(self):
        r"""
        Transition action: Restart -> Wait.
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
    Data Acquisition (DAQ) State Machine.
    
    Specialized state machine for polling OPC UA tags at a specific interval.
    """    

    def __init__(
            self,
            name:str="DAQ",
            description:str="",
            classification:str="Data Acquisition System"
        ):
        
        self.cvt = CVTEngine()
        self.das = DAS()

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
        Executed in Wait state. DAQ immediately transitions to Run.
        """
        self.send('wait_to_run')

    def while_running(self):
        r"""
        Executed in Run state.
        
        Reads values from OPC UA using the client manager and updates the CVT and DAS buffers.
        """
        from . import TIMEZONE, MANUFACTURER, SEGMENT
        for tag_name, process_type in self.get_subscribed_tags().items():
            tag = process_type.tag
            namespace = tag.get_node_namespace()
            opcua_address = tag.get_opcua_address()
            values = self.opcua_client_manager.get_node_value_by_opcua_address(opcua_address=opcua_address, namespace=namespace)
            if values:
                data_value = values[0][0]["DataValue"]
                value = data_value.Value.Value
                timestamp = data_value.SourceTimestamp
                if not timestamp:
                    timestamp = datetime.now(pytz.utc)
                timestamp = timestamp.replace(tzinfo=pytz.UTC)
                val = tag.value.convert_value(value=value, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
                if tag.manufacturer==MANUFACTURER and tag.segment==SEGMENT:      
                    val = self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
                elif not MANUFACTURER and not SEGMENT:
                    val = self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
                timestamp = timestamp.astimezone(TIMEZONE)
                self.das.buffer[tag_name]["timestamp"](timestamp)
                self.das.buffer[tag_name]["values"](val)

        super().while_running()

    # Auxiliaries Methods
    def set_opcua_client_manager(self, manager:OPCUAClientManager):
        r"""
        Sets the OPC UA Client Manager reference.
        """
        self.opcua_client_manager = manager


class OPCUAServer(StateMachineCore):
    r"""
    OPC UA Server State Machine.
    
    Manages the lifecycle of an embedded OPC UA Server, exposing CVT tags, alarms, and machine states.
    """    

    def __init__(
            self,
            name:str="OPCUAServer",
            description:str="",
            classification:str="OPC UA Server"
        ):
        from . import OPCUA_SERVER_PORT
        self.cvt = CVTEngine()
        self.alarm_manager = AlarmManager()
        self.machine = Machine()
        self.my_folders = dict()
        self.port = OPCUA_SERVER_PORT

        if isinstance(name, StringType):

            name = name.value

        super(OPCUAServer, self).__init__(
            name=name,
            description=description,
            classification=classification
            )
        
    @logging_error_handler
    def while_starting(self):
        r"""
        Executed in Start state.
        
        Initializes the OPC UA Server, configures endpoints, creates namespaces, and populates the address space
        with CVT tags, Alarms, and Engines folders.
        """
        self.server = Server()
        self.server.set_endpoint(f'opc.tcp://0.0.0.0:{self.port}/OPCUAServer/')
        
        # setup our own namespace, not really necessary but should as spec
        uri = "http://examples.freeopcua.github.io"
        self.idx = self.server.register_namespace(uri)
        # get Objects node, this is where we should put our node
        self.objects = self.server.get_objects_node()
        # populating our address space
        self.my_folders['CVT'] = self.objects.add_folder(self.idx, "CVT")
        self.my_folders['Alarms'] = self.objects.add_folder(self.idx, "Alarms")
        self.my_folders['Engines'] = self.objects.add_folder(self.idx, "Engines")

        # SET
        self.server.start()
        self.__set_cvt()
        self.__set_alarms()
        self.__set_engines()
        
        logging.getLogger('opcua').setLevel(logging.ERROR)

        self.send('start_to_wait')

    def while_waiting(self):
        r"""
        Executed in Wait state. Transitions to Run.
        """
        self.send('wait_to_run')

    def while_running(self):
        r"""
        Executed in Run state.
        
        Continuously updates the values of tags, alarms, and engines in the OPC UA address space.
        """
        self.__update_tags()
        self.__update_alarms()
        self.__update_engines()

    def while_resetting(self):
        r"""
        Executed in Reset state. Transitions back to Starting to restart the server.
        """
        self.send('reset_to_starting')

    def __set_engines(self):
        r"""
        Initializes OPC UA nodes for all registered state machines (Engines).
        """
        from . import MANUFACTURER
        segment = "Engines"
        engines = self.machine.machine_manager.get_machines()

        for engine, _, _ in engines:

            engine = engine.serialize()
            engine_name = engine["name"]
            engine_description = engine["description"] or ""

            if not hasattr(self, engine_name):

                if engine["segment"]:

                    segment = engine["segment"]

                    if segment not in self.my_folders.keys():

                        self.my_folders[segment] = self.objects.add_folder(self.idx, segment)
                    
                    segment = f"{engine['segment']}.engines"
                    if segment not in self.my_folders.keys():
                        
                        self.my_folders[segment] = self.my_folders[engine['segment']].add_folder(self.idx, 'Engines')

                if segment not in self.my_folders.keys():
                            
                    self.my_folders[segment] = self.my_folders[segment]
                    
                var_name = f"{segment}.{engine_name}"

                if not hasattr(self, var_name):
                    __var_name = engine_name.replace(f"{MANUFACTURER}.", "")

                    ID = blake2b(key=f"{__var_name}".encode('utf-8')[:64], digest_size=4).hexdigest()
                    setattr(self, var_name, self.my_folders[segment].add_variable(
                        ua.NodeId(identifier=ID, namespaceidx=self.idx), 
                        engine_name, 
                        0)
                    )
                    node = getattr(self, var_name)
                    self.__load_saved_access_type(node=node, var_name=var_name)
                    description = node.get_attribute(ua.AttributeIds.Description)
                    description.Value.Value.Text = engine_description
                    browse_name = node.get_attribute(ua.AttributeIds.BrowseName)
                    browse_name.Value.Value.Name = ""

                    # Add Properties
                    keep_list = (
                        "state",
                        "manufacturer",
                        "segment",
                        "criticity",
                        "priority",
                        "classification",
                        "machine_interval",
                        "fluid",
                        "maneuver",
                        "operation"
                        )

                    for key in keep_list:
                        if key in engine:
                            ID = blake2b(key=f"{__var_name}.{key}".encode('utf-8')[:64], digest_size=4).hexdigest()
                            prop = node.add_property(ua.NodeId(identifier=ID, namespaceidx=self.idx), key, engine[key])
                            self.__load_saved_access_type(node=prop, var_name=f"{var_name}.{key}")  
                            browse_name = prop.get_attribute(ua.AttributeIds.BrowseName)
                            browse_name.Value.Value.Name = "" 

    def __set_alarms(self):
        r"""
        Initializes OPC UA nodes for all defined alarms.
        """
        from . import MANUFACTURER
        alarms = self.alarm_manager.get_alarms()
        segment = "Alarms"
        for _, alarm in alarms.items():

            alarm_name = alarm.name
            alarm_description = alarm.description or ""

            if not hasattr(self, alarm_name):

                if alarm.tag.segment:

                    segment = alarm.tag.segment

                    if segment not in self.my_folders.keys():
                        self.my_folders[segment] = self.objects.add_folder(self.idx, segment)
                    
                    segment = f"{alarm.tag.segment}.alarms"
                    if segment not in self.my_folders.keys():
                        self.my_folders[segment] = self.my_folders[alarm.tag.segment].add_folder(self.idx, 'Alarms')

                if segment not in self.my_folders.keys():
                            
                    self.my_folders[segment] = self.my_folders[segment]
                    
                var_name = f"{segment}.{alarm_name}"

                if not hasattr(self, var_name):
                    __var_name = alarm_name.replace(f"{MANUFACTURER}.", "")
                    ID = blake2b(key=f"{__var_name}".encode('utf-8')[:64], digest_size=4).hexdigest()

                    setattr(self, var_name, self.my_folders[segment].add_variable(
                        ua.NodeId(identifier=ID, namespaceidx=self.idx), 
                        alarm_name, 
                        0)
                    )
                    node = getattr(self, var_name)
                    self.__load_saved_access_type(node=node, var_name=var_name)
                    description = node.get_attribute(ua.AttributeIds.Description)
                    description.Value.Value.Text = alarm_description
                    browse_name = node.get_attribute(ua.AttributeIds.BrowseName)
                    browse_name.Value.Value.Name = ""

                    # Add State Properties
                    for state_key, state_value in alarm.state.serialize().items():
                        ID = blake2b(key=f"{__var_name}.{state_key}".encode('utf-8')[:64], digest_size=4).hexdigest()
                        prop = node.add_property(ua.NodeId(identifier=ID, namespaceidx=self.idx), state_key, state_value)
                        self.__load_saved_access_type(node=prop, var_name=f"{var_name}.{state_key}")   
                        browse_name = prop.get_attribute(ua.AttributeIds.BrowseName)
                        browse_name.Value.Value.Name = ""  

    def __set_cvt(self):
        r"""
        Initializes OPC UA nodes for all CVT tags.
        """
        from . import MANUFACTURER
        
        segment = "CVT"
        for tag in self.cvt.get_tags():
            
            if tag["segment"]:

                segment = tag["segment"]

                if segment not in self.my_folders.keys():
                    
                    self.my_folders[segment] = self.objects.add_folder(self.idx, segment)
            
            tag_name = tag['name']
            display_unit = tag["display_unit"]
            data_type = tag["data_type"]
            tag_description = tag["description"] or ""
            
            var_name = f"{segment}_{tag_name}"
            __var_name = tag_name.replace(f"{MANUFACTURER}.", "")
            identifier = blake2b(key=__var_name.encode('utf-8')[:64], digest_size=4).hexdigest()

            if not hasattr(self, var_name):
                
                if data_type.lower()=='str':
                        setattr(self, var_name, self.my_folders[f"{segment}"].add_variable(
                            ua.NodeId(identifier=identifier, namespaceidx=self.idx), 
                            tag_name, 
                            "")
                        )

                else:

                    setattr(self, var_name, self.my_folders[f"{segment}"].add_variable(
                        ua.NodeId(identifier=identifier, namespaceidx=self.idx), 
                        tag_name, 
                        0.0)
                    )

                node = getattr(self, var_name)
                self.__load_saved_access_type(node=node, var_name=var_name)
                description = node.get_attribute(ua.AttributeIds.Description)
                description.Value.Value.Text = tag_description
                browse_name = node.get_attribute(ua.AttributeIds.BrowseName)
                browse_name.Value.Value.Name = display_unit

                pop_list = (
                    "id", 
                    "value", 
                    "timestamp", 
                    "timestamps", 
                    "values", 
                    "name", 
                    "description", 
                    "opcua_address", 
                    "node_namespace", 
                    "process_filter",
                    "gaussian_filter",
                    "out_of_range_detection",
                    "frozen_data_detection",
                    "outlier_detection"
                    )
                for key in pop_list:
                    tag.pop(key)
                # Add State Properties
                for key, value in tag.items():
                    
                    ID = blake2b(key=f"{__var_name}_{key}".encode('utf-8')[:64], digest_size=4).hexdigest()
                    prop = node.add_property(ua.NodeId(identifier=ID, namespaceidx=self.idx), key, value)  
                    self.__load_saved_access_type(node=prop, var_name=f"{var_name}.{key}") 
                    browse_name = prop.get_attribute(ua.AttributeIds.BrowseName)
                    browse_name.Value.Value.Name = "" 

    def __update_tags(self):
        r"""
        Updates the values of CVT tags in the OPC UA address space.
        """
        for tag in self.cvt.get_tags():
            
            segment = "CVT"
            value = tag["value"]

            if tag['segment']:

                segment = tag['segment']

            var_name = f"{segment}_{tag['name']}"
            if hasattr(self, var_name):

                _tag = getattr(self, var_name)

                if isinstance(value, (float, int)):
                    
                    _tag.set_value(round(value, 4))

                else:

                    _tag.set_value(value)

    def __update_alarms(self):
        r"""
        Updates the state of alarms in the OPC UA address space.
        """
        alarms = self.alarm_manager.get_alarms()
        segment = "Alarms"
        for _, alarm in alarms.items():

            alarm_name = alarm.name

            if alarm.tag.segment:

                segment = alarm.tag.segment
                segment = f"{segment}.alarms"

            var_name = f"{segment}.{alarm_name}"
            if hasattr(self, var_name):
                    
                var = getattr(self, var_name)
                props = var.get_properties()

                for prop in props:
                    
                    display_name = prop.get_display_name().Text                   

                    if display_name.startswith("setpoint"):
                        display_name = display_name.replace("setpoint.", "")
                        attr = getattr(alarm.alarm_setpoint, display_name)
                        prop.set_value(attr)

                    else:
                        attr = getattr(alarm.state, display_name)
                        prop.set_value(attr)

    def __update_engines(self):
        r"""
        Updates the state of engines in the OPC UA address space.
        """
        segment = "Engines"
        engines = self.machine.machine_manager.get_machines()

        for engine, _, _ in engines:

            engine = engine.serialize()
            engine_name = engine["name"]

            if engine["segment"]:

                segment = engine["segment"]
                segment = f"{segment}.engines"

            var_name = f"{segment}.{engine_name}"
            if hasattr(self, var_name):
                    
                var = getattr(self, var_name)
                props = var.get_properties()

                for prop in props:
                    
                    display_name = prop.get_display_name().Text                
                    attr = engine[display_name]
                    prop.set_value(attr)

    def __load_saved_access_type(self, node, var_name):
        from .core import PyAutomation
        from .opcua.subscription import SubHandlerServer

        handler = SubHandlerServer()
        app = PyAutomation()
        namespace = node.nodeid.to_string()
        opcua_server_obj = app.get_opcua_server_record_by_namespace(namespace=namespace)
        access_type = "Read"
        if opcua_server_obj:
            record = opcua_server_obj.serialize()
            access_type = record['access_type']['name']
        else:
            app.create_opcua_server_record(name=var_name, namespace=namespace, access_type=access_type)

        access_type = access_type.lower()
        # Limpiar todos los bits de acceso primero
        node.unset_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
        node.unset_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
        node.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
        node.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
        
        if access_type == "write":
            # Solo escritura: deshabilitamos la lectura y habilitamos la escritura
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
            # Crea un manejador de suscripción
            sub = self.server.create_subscription(100, handler)
            sub.subscribe_data_change(node)

        elif access_type == "read":
            # Solo lectura: habilitamos la lectura y deshabilitamos la escritura
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
        elif access_type == "readwrite":
            # Lectura y escritura: habilitamos ambos
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
            # Crea un manejador de suscripción
            sub = self.server.create_subscription(100, handler)
            sub.subscribe_data_change(node)


class AutomationStateMachine(StateMachineCore):
    r"""
    Extended State Machine with additional states for testing and sleeping.
    
    States:
    * **Test**: Testing or simulation mode.
    * **Sleep**: Idle or low-power mode.
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
        Executed in Test state.
        """
        self.criticity.value = 3

    def while_sleeping(self):
        r"""
        Executed in Sleep state.
        """
        self.criticity.value = 5

    # Transitions
    def on_test_to_restart(self):
        r"""
        Transition: Test -> Restart.
        """
        self.last_state = "test"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_test_to_reset(self):
        r"""
        Transition: Test -> Reset.
        """
        self.last_state = "test"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_sleep_to_restart(self):
        r"""
        Transition: Sleep -> Restart.
        """
        self.last_state = "sleep"
        self.criticity.value = 4
        if self.sio:
            self.sio.emit("on.machine", data=self.serialize())

    def on_sleep_to_reset(self):
        r"""
        Transition: Sleep -> Reset.
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

