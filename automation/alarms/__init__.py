import secrets
from datetime import datetime, timedelta, timezone
from .states import AlarmState, AlarmAttrs
from .trigger import Trigger, TriggerType
from ..tags.tag import Tag, MachineObserver
from ..tags.cvt import CVTEngine
from ..modules.users.users import User
from ..utils.decorators import validate_types, logging_error_handler, set_event, put_alarm_state
from ..models import FloatType, IntegerType, StringType
from ..variables import *
from statemachine import State, StateMachine
from flask_socketio import SocketIO


class Alarm(StateMachine):

    # MAIN STATES
    normal = State("normal", initial=True)
    unack_alarm = State("unack_alarm")
    ack_alarm = State("ack_alarm")
    rtn_unack = State("rtn_unack")

    # OUT OF SERVICE STATES
    shelved = State("shelved")
    suppressed_by_design = State("suppressed_by_design")
    out_of_service = State("out_of_service")

    # MAIN TRANSITIONS
    normal_to_unack_alarm = normal.to(unack_alarm)
    unack_alarm_to_ack_alarm = unack_alarm.to(ack_alarm)
    ack_alarm_to_normal = ack_alarm.to(normal)
    unack_alarm_to_rtn_unack = unack_alarm.to(rtn_unack)
    rtn_unack_to_normal = rtn_unack.to(normal)
    rtn_unack_to_unack_alarm = rtn_unack.to(unack_alarm)

    # SHELVED TRANSITIONS
    normal_to_shelved = normal.to(shelved)
    unack_alarm_to_shelved = unack_alarm.to(shelved)
    ack_alarm_to_shelved = ack_alarm.to(shelved)
    rtn_unack_to_shelved = rtn_unack.to(shelved)
    shelved_to_normal = shelved.to(normal)
    shelved_to_unack_alarm = shelved.to(unack_alarm)

    # SUPPRESSED BY DESIGN TRANSITIONS
    normal_to_suppressed_by_design = normal.to(suppressed_by_design)
    unack_alarm_to_suppressed_by_design = unack_alarm.to(suppressed_by_design)
    ack_alarm_to_suppressed_by_design = ack_alarm.to(suppressed_by_design)
    rtn_unack_to_suppressed_by_design = rtn_unack.to(suppressed_by_design)
    suppressed_by_design_to_normal = suppressed_by_design.to(normal)
    suppressed_by_design_to_unack_alarm = suppressed_by_design.to(unack_alarm)


    # OUT OF SERVICE TRANSITIONS
    normal_to_out_of_service = normal.to(out_of_service)
    unack_alarm_to_out_of_service = unack_alarm.to(out_of_service)
    ack_alarm_to_out_of_service = ack_alarm.to(out_of_service)
    rtn_unack_to_out_of_service = rtn_unack.to(out_of_service)
    out_of_service_to_normal = out_of_service.to(normal)
    out_of_service_to_unack_alarm = out_of_service.to(unack_alarm)

    @logging_error_handler
    def __init__(
            self,
            name:str, 
            tag:Tag,
            alarm_type:StringType,
            alarm_setpoint:IntegerType|FloatType,
            description:str="",
            state:str=None,
            timestamp:datetime=None,
            ack_timestamp:datetime=None,
            alarm_deadband:IntegerType|FloatType=FloatType(0.0),
            alarm_on_delay:IntegerType|FloatType=FloatType(0.0),
            alarm_off_delay:IntegerType|FloatType=FloatType(0.0),
            identifier:str=None,
            user:User=None,
            reload:bool=False
        ):
        # self.events_engine = EventsLoggerEngine()
        from ..logger.alarms import AlarmsLoggerEngine
        self.alarm_engine = AlarmsLoggerEngine()
        self.tag_engine = CVTEngine()
        self.name = name
        self.tag = tag
        self.attach(machine=self, tag=tag)
        self.description = description        
        self.alarm_setpoint = Trigger()
        self.alarm_setpoint.value = alarm_setpoint.value
        self.alarm_setpoint.type = TriggerType(value=alarm_type.value.upper())
        alarm_deadband.unit = tag.get_display_unit()
        self.alarm_deadband = alarm_deadband
        self.alarm_on_delay = alarm_on_delay
        self.alarm_off_delay = alarm_off_delay
        self.timestamp = timestamp 
        self.ack_timestamp = ack_timestamp
        self.state = AlarmState.NORM
        if state:
            
            for _, attr in AlarmState.__dict__.items():
                
                if isinstance(attr, AlarmAttrs):
                    
                    if state==attr.state:
                        
                        self.state = attr
                        break
        if identifier:
            self.identifier = identifier
        else:
            self.identifier = secrets.token_hex(4)
        self._shelved_time:datetime = None
        self._shelved_until:datetime = None
        self._shelved_options_time = {
            'days': 0,
            'seconds': 0,
            'microseconds': 0,
            'milliseconds': 0,
            'minutes': 0,
            'hours': 0,
            'weeks': 0
        }
        transitions = []
        for state in self.states:
            transitions.extend(state.transitions)
        self.transitions = transitions
        self.sio:SocketIO|None = None
        super(Alarm, self).__init__()

    @logging_error_handler
    @put_alarm_state
    def on_enter_normal(self):
        self.state = AlarmState.NORM
        self.timestamp = None 
        self.ack_timestamp = None

    @logging_error_handler
    @put_alarm_state
    def on_enter_unack_alarm(self):

        self.state = AlarmState.UNACK
        self.timestamp = self.__timestamp

    @logging_error_handler
    @put_alarm_state
    def on_enter_ack_alarm(self):

        self.state = AlarmState.ACKED
        self.ack_timestamp = self.__timestamp
    
    @logging_error_handler
    @put_alarm_state
    def on_enter_rtn_unack(self):
        
        self.timestamp = None
        self.state = AlarmState.RTNUN
    
    @logging_error_handler
    @put_alarm_state
    def on_enter_shelved(self):
        
        self.state = AlarmState.SHLVD

    @logging_error_handler
    @put_alarm_state
    def on_enter_suppressed_by_design(self):
        
        self.state = AlarmState.DSUPR

    @logging_error_handler
    @put_alarm_state
    def on_enter_out_of_service(self):
        
        self.state = AlarmState.OOSRV

    def set_socketio(self, sio:SocketIO):
        r"""
        Documentation here
        """
        self.sio:SocketIO = sio

    @logging_error_handler
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
        self.__timestamp = timestamp
        if self.state not in (AlarmState.DSUPR, AlarmState.SHLVD, AlarmState.OOSRV):     
            if self.alarm_setpoint.type in (TriggerType.HH, TriggerType.H):

                if value.value > self.alarm_setpoint.value:

                    self.abnormal_condition()
                
                else: 

                    self.normal_condition()

            elif self.alarm_setpoint.type in (TriggerType.L, TriggerType.LL):

                if value.value < self.alarm_setpoint.value:

                    self.abnormal_condition()

                else:

                    self.normal_condition()

            else: # Boolean Alarm
                
                if value.value == bool(self.alarm_setpoint.value):

                    self.abnormal_condition()

                else:

                    self.normal_condition()                    

        if self.state==AlarmState.SHLVD:

            if datetime.now(timezone.utc) >= self._shelved_until:

                self.unshelve()
        
    @logging_error_handler
    def abnormal_condition(self):
        r"""
        Documentation here
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_unack_alarm'
        self.__transition(transition_name=transition_name)

    @logging_error_handler
    def normal_condition(self):
        r"""
        Documentation here
        """
        current_state = self.current_state.name.lower()

        if current_state=="unack_alarm":

            transition_name = f'{current_state}_to_rtn_unack'
            self.alarm_engine.create_record_on_alarm_summary(
                name=self.name, 
                state=self.state.state, 
                timestamp=self.timestamp,
                ack_timestamp=self.ack_timestamp
            )
            self.__transition(transition_name=transition_name)

        elif current_state=="ack_alarm":

            transition_name = f'{current_state}_to_normal'
            self.alarm_engine.create_record_on_alarm_summary(
                name=self.name, 
                state=self.state.state, 
                timestamp=self.timestamp,
                ack_timestamp=self.ack_timestamp
            )
            self.__transition(transition_name=transition_name)

    @logging_error_handler
    @set_event(message=f"Acknowledged", classification="Alarm", priority=2, criticity=3)
    def acknowledge(self, user:User=None):
        r"""
        Documentation here
        """
        current_state = self.current_state.name.lower()

        if current_state=="unack_alarm":

            transition_name = f'{current_state}_to_ack_alarm'

        elif current_state=="rtn_unack":

            transition_name = f'{current_state}_to_normal'

        tag = self.tag_engine.get_tag_by_name(name=self.tag.name)
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message=f"Shelved", classification="Alarm", priority=2, criticity=3)
    def shelve(self, user:User=None, **options):
        r"""
        Documentation here
                **Parameters**

        * **days:** (int)
        * **seconds:** (int)
        * **minutes:** (int)
        * **hours:** (int)
        * **weeks:** (int)
        """
        options_time = {key: options[key] if key in options else self._shelved_options_time[key] for key in self._shelved_options_time}
        
        if options_time!=self._shelved_options_time:
            
            self._shelved_time = datetime.now(timezone.utc)
            self._shelved_until = self._shelved_time + timedelta(**options_time)

        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_shelved'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message=f"Unshelved", classification="Alarm", priority=2, criticity=3)
    def unshelve(self, user:User=None):
        r"""
        Documentation here
        """
        self.__return_to_service()
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message=f"Designed suppression", classification="Alarm", priority=2, criticity=3)
    def designed_suppression(self, user:User=None):
        r"""
        Documentation here
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_suppressed_by_design'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message=f"Designed unsuppression", classification="Alarm", priority=2, criticity=3)
    def designed_unsuppression(self, user:User=None):
        r"""
        Documentation here
        """
        self.__return_to_service()
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message=f"Removed from service", classification="Alarm", priority=2, criticity=3)
    def remove_from_service(self, user:User=None):
        r"""
        Documentation here
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_out_of_service'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message=f"Returned to service", classification="Alarm", priority=2, criticity=3)
    def return_to_service(self, user:User=None):
        r"""
        Documentation here
        """
        self.__return_to_service()

        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    def attach(self, machine, tag:Tag):
        
        def attach_observer(machine, tag:Tag):

            observer = MachineObserver(machine)
            query = dict()
            query["action"] = "attach_observer"
            query["parameters"] = {
                "name": tag.name,
                "observer": observer,
            }
            self.tag_engine.request(query)
            self.tag_engine.response()

        attach_observer(machine, tag)

    @set_event(message=f"Updated", classification="Alarm", priority=2, criticity=3)
    def put(
            self, 
            user:User=None,
            name:str=None,
            tag:str=None,
            description:str=None,
            alarm_type:TriggerType=None,
            trigger_value:float=None):
        r"""
        Update alarm configuration

        **Parameters**
        
        * **name** (str): Alarm name
        * **tag** (str): Tag binded to alarm
        * **description** (str): Alarm description
        * **type** (str): Alarm type ['HIGH-HIGH', 'HIGH', 'LOW', 'LOW-LOW', 'BOOL']
        * **trigger_value** (float): Alarm trigger value

        """
        message = ""
        if alarm_type:

            if alarm_type.value.upper() in ["HIGH-HIGH", "HIGH", "LOW", "LOW-LOW", "BOOL"]:

                self.alarm_setpoint.type = alarm_type

                message += f" alarm_type: {alarm_type.value}"

        if trigger_value:
            
            self.alarm_setpoint.value = float(trigger_value)
            message += f" trigger value: {trigger_value}"
        
        if name:

            self._name = name
            message += f" name: {name}"

        if tag:

            self._tag = tag
            message += f" tag: {tag}"

        if description:

            self._description = description
            message += f" description: {description}"
        
        return self, message

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
    
    @logging_error_handler
    def __transition(self, transition_name:str):

        allowed_transitions = self._get_active_transitions()
        for _transition in allowed_transitions:
            
            if f"{_transition.source.name}_to_{_transition.target.name}"==transition_name:
                
                self.send(transition_name)

    @logging_error_handler
    def __return_to_service(self):

        current_state = self.current_state.name.lower()

        if self.state.alarm_status.lower()=="active":

            transition_name = f'{current_state}_to_unack_alarm'

        else:

            transition_name = f'{current_state}_to_normal'
        
        self.__transition(transition_name=transition_name)

    @logging_error_handler
    def get_operator_actions(self)->list:
        
        current_state = self.current_state.name.lower()
            
        if current_state in ("unack_alarm", "rtn_unack"):

            result = {
                "Acknowledge": "acknowledge",
                "Shelve": "shelve",
                "Designed Suppression": "designed_suppression",
                "Remove From Service": "remove_from_service"
            }

        elif current_state=="suppressed_by_design":

            result = {
                "Designed Unsuppression": "designed_unsuppression"
            }

        elif current_state=="out_of_service":

            result = {
                "Return To Service": "return_to_service"
            }

        else:

            result = {
                "Shelve": "shelve",
                "Designed Suppression": "designed_suppression",
                "Remove From Service": "remove_from_service"
            }

        return result

    def serialize(self):
        r"""
        Allows you to serialize alarm to a dict jsonable

        **Return**

        * **alarm_info**: (dict) A jsonable dictionary
        """
        timestamp = self.timestamp
        if timestamp:

            timestamp = timestamp.strftime(self.tag_engine.DATETIME_FORMAT)

        ack_timestamp = self.ack_timestamp
        if ack_timestamp:

            ack_timestamp = ack_timestamp.strftime(self.tag_engine.DATETIME_FORMAT)

        return {
            "identifier": self.identifier,
            "timestamp": timestamp,
            "name": self.name,
            "tag": self.tag.name,
            "state": self.state.serialize(),
            "alarm_setpoint": self.alarm_setpoint.serialize(),
            "ack_timestamp": ack_timestamp,
            "description": self.description,
        }


