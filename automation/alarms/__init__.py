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
    r"""
    Represents an Alarm entity with state machine logic.

    Implements the standard alarm lifecycle defined in ISA 18.2, including states like
    Normal, Unacknowledged, Acknowledged, Shelved, and Suppressed.

    It monitors a `Tag` value against a `Trigger` condition and transitions states accordingly.
    """

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
        r"""
        Initializes the Alarm.

        **Parameters:**

        * **name** (str): Alarm name.
        * **tag** (Tag): The tag being monitored.
        * **alarm_type** (StringType): Trigger type (HI, LO, etc.).
        * **alarm_setpoint** (IntegerType|FloatType): The limit value.
        * **description** (str): Alarm description.
        * **state** (str, optional): Initial state.
        * **identifier** (str, optional): Unique ID.
        """
        from ..logger.alarms import AlarmsLoggerEngine
        self.alarm_engine = AlarmsLoggerEngine()
        self.tag_engine = CVTEngine()
        self.name = name
        self.tag = tag
        # Verificar que tag no sea None antes de acceder a sus atributos
        if tag is None:
            raise ValueError(f"Cannot create alarm '{name}': tag is None")
        self.segment = tag.segment if hasattr(tag, 'segment') else None
        self.manufacturer = tag.manufacturer if hasattr(tag, 'manufacturer') else None
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
        self._defer_persist = False
        super(Alarm, self).__init__()

    def catalog_payload(self) -> dict:
        r"""Fields needed to persist this alarm definition to the historian catalog."""
        tag_name = None
        area = None
        tag = self.tag
        if tag is not None:
            tag_name = getattr(tag, "name", None)
            if not tag_name:
                getter = getattr(tag, "get_name", None)
                if callable(getter):
                    tag_name = getter()
            area = getattr(tag, "area", None)
        if not area:
            from ..utils.event_scope import resolve_event_area

            area = resolve_event_area()
        trigger = self.alarm_setpoint
        trigger_type = None
        trigger_value = None
        if trigger is not None:
            trigger_value = getattr(trigger, "value", None)
            kind = getattr(trigger, "type", None)
            if kind is not None:
                trigger_type = getattr(kind, "value", None) or str(kind)
        return {
            "identifier": self.identifier,
            "tag": tag_name,
            "trigger_type": trigger_type or "BOOL",
            "trigger_value": trigger_value,
            "description": self.description or "",
            "area": area,
        }

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
        from ..timebase import quantize_datetime_ms
        stamp = getattr(self, "_Alarm__timestamp", None)
        if not isinstance(stamp, datetime):
            stamp = datetime.now(timezone.utc)
        self.timestamp = quantize_datetime_ms(stamp)
        if getattr(self, "_defer_persist", False):
            return
        catalog = self.catalog_payload()
        self.alarm_engine.create_record_on_alarm_summary(
                name=self.name, 
                state=self.state.state, 
                timestamp=self.timestamp,
                ack_timestamp=self.ack_timestamp,
                identifier=catalog.get("identifier"),
                tag=catalog.get("tag"),
                trigger_type=catalog.get("trigger_type"),
                trigger_value=catalog.get("trigger_value"),
                description=catalog.get("description"),
                area=catalog.get("area"),
            )

    @logging_error_handler
    @put_alarm_state
    def on_enter_ack_alarm(self):

        self.state = AlarmState.ACKED
        from ..timebase import quantize_datetime_ms
        stamp = getattr(self, "_Alarm__timestamp", None)
        if not isinstance(stamp, datetime):
            stamp = datetime.now(timezone.utc)
        self.ack_timestamp = quantize_datetime_ms(stamp)
        if getattr(self, "_defer_persist", False):
            return
        catalog = self.catalog_payload()
        self.alarm_engine.put_record_on_alarm_summary(
            name=self.name, 
            state=self.state.state, 
            ack_timestamp=self.ack_timestamp,
            tag=catalog.get("tag"),
            identifier=catalog.get("identifier"),
            area=catalog.get("area"),
        )
    
    @logging_error_handler
    @put_alarm_state
    def on_enter_rtn_unack(self):
        
        self.timestamp = None
        self.state = AlarmState.RTNUN
        if getattr(self, "_defer_persist", False):
            return
        catalog = self.catalog_payload()
        self.alarm_engine.put_record_on_alarm_summary(
            name=self.name, 
            state=self.state.state,
            tag=catalog.get("tag"),
            identifier=catalog.get("identifier"),
            area=catalog.get("area"),
        )
    
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
        Sets the SocketIO instance for real-time updates.

        **Parameters:**

        * **sio** (SocketIO): The SocketIO server instance.
        """
        self.sio:SocketIO = sio

    @logging_error_handler
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
        Callback triggered when the monitored Tag value changes (Observer pattern).
        
        It evaluates the new value against alarm logic and triggers state transitions.
        Process setpoints are inhibited while the PV quality is BAD (configurable
        for UNCERTAIN via ``alarm_inhibit_uncertain_quality``).

        **Parameters:**

        * **tag** (str): Tag name.
        * **value** (Quantity): The new tag value.
        * **timestamp** (datetime): Time of the value change.
        """ 
        self.__timestamp = timestamp
        if self.state not in (AlarmState.DSUPR, AlarmState.SHLVD, AlarmState.OOSRV):
            if self._quality_allows_process_evaluation():
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

                self.unshelve(current_value=value)

    def _quality_allows_process_evaluation(self) -> bool:
        """Gate process setpoints on PV quality (ISA-18.2 inhibit on Bad)."""
        from ..signal_conditioning.quality import is_process_alarm_allowed

        subject = getattr(self, "tag", None)
        quality = getattr(subject, "quality", None) if subject is not None else None
        inhibit_uncertain = False
        try:
            from ..signal_conditioning.quality import get_inhibit_uncertain_quality

            inhibit_uncertain = bool(get_inhibit_uncertain_quality())
        except Exception:
            inhibit_uncertain = False
        return is_process_alarm_allowed(quality, inhibit_uncertain=inhibit_uncertain)

    @logging_error_handler
    def abnormal_condition(self):
        r"""
        Triggers transition to an alarm state (abnormal).

        Already Unacknowledged: no-op (ISA-18.2 does not re-annunciate).
        """
        current_state = self.current_state.name.lower()
        if current_state == "unack_alarm":
            return
        transition_name = f'{current_state}_to_unack_alarm'
        self.__transition(transition_name=transition_name)

    @logging_error_handler
    def normal_condition(self):
        r"""
        Triggers transition to normal or return-to-normal states.

        RTN Unacknowledged with condition still normal: no-op. The operator
        must acknowledge to reach Normal (ISA-18.2).
        """
        current_state = self.current_state.name.lower()

        if current_state=="unack_alarm":

            transition_name = f'{current_state}_to_rtn_unack'
            self.__transition(transition_name=transition_name)

        elif current_state=="ack_alarm":

            transition_name = f'{current_state}_to_normal'
            self.__transition(transition_name=transition_name)

    def _apply_acknowledge(self, now:datetime)->bool:
        r"""
        ISA-18.2 acknowledge transition in memory only.

        Persistence, audit, and socket fan-out are owned by the caller so a
        bulk acknowledge can pay one round-trip instead of one per alarm.
        """
        current_state = self.current_state.name.lower()
        if current_state == "unack_alarm":
            transition_name = "unack_alarm_to_ack_alarm"
        elif current_state == "rtn_unack":
            transition_name = "rtn_unack_to_normal"
        else:
            return False
        self.__timestamp = now
        self.__transition(transition_name=transition_name)
        return True

    def _acknowledge_in_memory(self, now:datetime)->bool:
        r"""Acknowledge without per-alarm DB writes or socket emits."""
        self._defer_persist = True
        try:
            return self._apply_acknowledge(now)
        finally:
            self._defer_persist = False

    @logging_error_handler
    @set_event(message="Alarm acknowledged", classification="Control", priority=2, criticity=3)
    def acknowledge(self, user:User=None):
        r"""
        Acknowledges the alarm.

        **Parameters:**

        * **user** (User, optional): User performing the acknowledgment.
        """
        from ..timebase import quantize_datetime_ms

        now = quantize_datetime_ms(datetime.now(timezone.utc))
        catalog = self.catalog_payload()
        self.alarm_engine.put_record_on_alarm_summary(
            name=self.name,
            ack_timestamp=now,
            tag=catalog.get("tag"),
            identifier=catalog.get("identifier"),
            area=catalog.get("area"),
        )
        if not self._apply_acknowledge(now):
            return None
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm shelved", classification="Control", priority=2, criticity=3)
    def shelve(self, user:User=None, **options):
        r"""
        Temporarily suppresses the alarm (Shelving).

        **Parameters:**

        * **options**: Time duration arguments (days, hours, minutes, seconds).
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
    @set_event(message="Alarm unshelved", classification="Control", priority=2, criticity=3)
    def unshelve(self, user:User=None, current_value=None):
        r"""
        Manually un-shelves the alarm, returning it to service.
        After unshelving, re-evaluates the current tag value to determine the correct state.
        
        **Parameters:**
        
        * **user** (User, optional): User performing the unshelve action.
        * **current_value** (Quantity, optional): Current tag value. If not provided, will be obtained from the tag.
        """
        self.__return_to_service()
        # Re-evaluate the alarm condition with current tag value after unshelving
        if current_value is None:
            current_value = self.tag.value
        if current_value:
            self.update(current_value)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm suppressed", classification="Control", priority=2, criticity=3)
    def designed_suppression(self, user:User=None):
        r"""
        Suppresses the alarm by design (e.g., maintenance mode).
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_suppressed_by_design'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm unsuppressed", classification="Control", priority=2, criticity=3)
    def designed_unsuppression(self, user:User=None):
        r"""
        Removes designed suppression.
        """
        self.__return_to_service()
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm removed from service", classification="Control", priority=2, criticity=3)
    def remove_from_service(self, user:User=None):
        r"""
        Takes the alarm out of service entirely.
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_out_of_service'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm returned to service", classification="Control", priority=2, criticity=3)
    def return_to_service(self, user:User=None):
        r"""
        Returns the alarm to service from 'Out of Service'.
        """
        self.__return_to_service()

        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    def attach(self, machine, tag:Tag):
        observer = MachineObserver(machine)
        self._machine_observer = observer
        query = dict()
        query["action"] = "attach_observer"
        query["parameters"] = {
            "name": tag.name,
            "observer": observer,
        }
        self.tag_engine.request(query)
        self.tag_engine.response()

    @logging_error_handler
    def detach_from_tag(self):
        observer = getattr(self, "_machine_observer", None)
        tag = getattr(self, "tag", None)
        if observer is None or tag is None:
            return
        tag_name = tag.name if hasattr(tag, "name") else None
        if tag_name:
            try:
                self.tag_engine.detach(name=tag_name, observer=observer)
            except Exception:
                try:
                    tag.detach(observer)
                except Exception:
                    pass
        self._machine_observer = None

    @set_event(message="Alarm updated", classification="Configuration", priority=2, criticity=3)
    def put(
            self, 
            user:User=None,
            name:str=None,
            tag:str=None,
            description:str=None,
            alarm_type:TriggerType=None,
            trigger_value:float=None):
        r"""
        Updates the alarm configuration.

        **Parameters:**
        
        * **name** (str): Alarm name.
        * **tag** (str): Tag bound to alarm.
        * **description** (str): Alarm description.
        * **alarm_type** (TriggerType): Alarm type ['HIGH-HIGH', 'HIGH', 'LOW', 'LOW-LOW', 'BOOL'].
        * **trigger_value** (float): Alarm trigger value.

        **Returns:**

        * **tuple**: (Alarm instance, status message)
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
        Gets allowed transitions based on the current state.

        **Returns:**

        * **list**: List of available transitions.
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
        r"""
        Returns a list of available actions for the operator based on current state.

        **Returns:**

        * **dict**: Map of Action Name -> Action Method.
        """
        current_state = self.current_state.name.lower()
            
        if current_state in ("unack_alarm", "rtn_unack"):

            result = {
                "Acknowledge": "acknowledge",
                "Shelve": "shelve",
                "Designed Suppression": "designed_suppression",
                "Remove From Service": "remove_from_service"
            }

        elif current_state=="shelved":

            result = {
                "Unshelve": "unshelve"
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
        Serializes the alarm object to a JSON-compatible dictionary.

        **Returns:**

        * **dict**: Alarm data including state, setpoint, and metadata.
        """
        from ..timebase import iso_millis

        timestamp = iso_millis(self.timestamp)
        ack_timestamp = iso_millis(self.ack_timestamp)

        return {
            "identifier": self.identifier,
            "segment": self.segment,
            "manufacturer": self.manufacturer,
            "timestamp": timestamp,
            "name": self.name,
            "tag": self.tag.name,
            "state": self.state.serialize(),
            "alarm_setpoint": self.alarm_setpoint.serialize(),
            "ack_timestamp": ack_timestamp,
            "description": self.description,
            "actions": self.get_operator_actions()
        }
