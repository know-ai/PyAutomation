# -*- coding: utf-8 -*-
"""automation/managers/alarms.py

This module implements the Alarm Manager, which is responsible for managing alarm definitions,
handling alarm events, and interacting with the Current Value Table (CVT) and Database.
"""
from datetime import datetime
import queue
from ..singleton import Singleton
from ..tags import CVTEngine, TagObserver
from ..alarms import AlarmState, Alarm
from ..dbmodels.alarms import AlarmSummary
from ..modules.users.users import User
from ..models import FloatType, StringType
from ..alarms.delays import clamp_alarm_delay, normalize_delay_units
from ..utils.decorators import set_event, logging_error_handler
from flask_socketio import SocketIO


def _normalize_tag_name(tag) -> str:
    if tag is None:
        return ""
    if isinstance(tag, str):
        return tag
    name = getattr(tag, "name", None)
    if name:
        return name
    getter = getattr(tag, "get_name", None)
    if callable(getter):
        return getter() or ""
    return str(tag)


def _scope_owns_alarm(alarm) -> bool:
    if alarm is None:
        return False
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not scope.enabled:
        return True
    tag = getattr(alarm, "tag", None)
    if isinstance(tag, str):
        tag = CVTEngine().get_tag_by_name(name=tag)
    return scope.owns_tag(tag)


class AlarmManager(Singleton):
    r"""
    Singleton class that manages all alarms in the system.

    It handles the creation, update, deletion, and retrieval of alarms.
    It also validates trigger conditions and manages communication with the frontend via SocketIO.
    """

    def __init__(self):

        self._alarms:dict = dict()
        self._by_name: dict = dict()
        self._by_tag_name: dict = dict()
        # Residual queue: TagObserver no longer consumes it (SAF gateway does).
        # Kept with maxsize=1 so a future reactivation cannot grow unbounded.
        self._tag_queue = queue.Queue(maxsize=1)
        self.tag_engine = CVTEngine()

    def _index_alarm(self, alarm: Alarm) -> None:
        if alarm is None:
            return
        self._by_name[alarm.name] = alarm
        tag_name = _normalize_tag_name(alarm.tag)
        if not tag_name:
            return
        bucket = self._by_tag_name.setdefault(tag_name, [])
        if alarm not in bucket:
            bucket.append(alarm)

    def _unindex_alarm(self, alarm: Alarm) -> None:
        if alarm is None:
            return
        if self._by_name.get(alarm.name) is alarm:
            self._by_name.pop(alarm.name, None)
        tag_name = _normalize_tag_name(alarm.tag)
        bucket = self._by_tag_name.get(tag_name)
        if not bucket:
            return
        self._by_tag_name[tag_name] = [item for item in bucket if item is not alarm]
        if not self._by_tag_name[tag_name]:
            self._by_tag_name.pop(tag_name, None)

    def alarm_count(self) -> int:
        return len(self.get_alarms())

    def prune_not_owned(self, scope) -> list[str]:
        """Remove foreign alarms from local indexes only."""
        removed = []
        for identifier, alarm in list(self._alarms.items()):
            if scope.owns_tag(getattr(alarm, "tag", None)):
                continue
            self._alarms.pop(identifier, None)
            self._unindex_alarm(alarm)
            removed.append(alarm.name)
        return removed

    def get_queue(self)->queue.Queue:
        r"""
        Retrieves the internal tag queue used for observer notifications.

        **Returns:**

        * **queue.Queue**: The queue instance.
        """
        return self._tag_queue

    @logging_error_handler
    def append_alarm(
            self,
            name:str,
            tag:str,
            type:str="BOOL",
            trigger_value:bool|float=True,
            description:str="",
            identifier:str=None,
            state:str="Normal",
            timestamp:str=None,
            ack_timestamp:str=None,
            user:User=None,
            reload:bool=False,
            sio:SocketIO|None=None,
            on_delay:float=None,
            off_delay:float=None,
            on_delay_units:str=None,
            off_delay_units:str=None,
        )->tuple[Alarm, str]:
        r"""
        Creates and registers a new alarm in the manager.

        **Parameters:**

        * **name** (str): Alarm name.
        * **tag** (str): Associated Tag name.
        * **type** (str): Alarm type (BOOL, HH, H, L, LL).
        * **trigger_value** (bool|float): Value that triggers the alarm.
        * **description** (str, optional): Alarm description.
        * **identifier** (str, optional): Unique ID.
        * **state** (str, optional): Initial state.
        * **timestamp** (str, optional): Last trigger timestamp.
        * **ack_timestamp** (str, optional): Last acknowledgment timestamp.
        * **user** (User, optional): User creating the alarm.
        * **reload** (bool, optional): If reloading from DB.
        * **sio** (SocketIO, optional): SocketIO instance for real-time updates.

        **Returns:**

        * **tuple[Alarm, str]**: The created Alarm object and a status message.
        """
        # Check alarm name duplicated
        alarm = self.get_alarm_by_name(name)
        if alarm:

            return alarm, f"Alarm {name} is already defined"

        # Check if alarm is associated to same tag with same alarm type
        trigger_value_message = self.__check_trigger_values(name=name, tag=tag, type=type, trigger_value=trigger_value)
        if trigger_value_message:

            return None, trigger_value_message

        if timestamp:

            timestamp = datetime.strptime(timestamp, self.tag_engine.DATETIME_FORMAT)

        if ack_timestamp:

            ack_timestamp = datetime.strptime(ack_timestamp, self.tag_engine.DATETIME_FORMAT)

        # Verificar que el tag existe antes de crear el alarm
        tag_obj = self.tag_engine.get_tag_by_name(name=tag)
        if tag_obj is None:
            return None, f"Tag '{tag}' not found. Cannot create alarm '{name}'."

        alarm = Alarm(
            name=name,
            tag=tag_obj,
            description=description,
            alarm_type=StringType(type),
            alarm_setpoint=FloatType(trigger_value),
            identifier=identifier,
            state=state,
            timestamp=timestamp,
            ack_timestamp=ack_timestamp,
            user=user,
            reload=reload,
            alarm_on_delay=FloatType(clamp_alarm_delay(on_delay)),
            alarm_off_delay=FloatType(clamp_alarm_delay(off_delay)),
            on_delay_units=normalize_delay_units(on_delay_units),
            off_delay_units=normalize_delay_units(off_delay_units),
        )
        alarm.set_socketio(sio=sio)
        self._alarms[alarm.identifier] = alarm
        self._index_alarm(alarm)

        return alarm, f"Alarm creation successful"

    @logging_error_handler
    def put(
            self,
            id:str,
            name:str=None,
            tag:str=None,
            description:str=None,
            alarm_type:str=None,
            trigger_value:float=None,
            user:User=None,
            on_delay:float=None,
            off_delay:float=None,
            on_delay_units:str=None,
            off_delay_units:str=None,
            )->tuple[Alarm, str]:
        r"""
        Updates an existing alarm configuration.

        **Parameters:**

        * **id** (str): Alarm identifier.
        * **name** (str, optional): New name.
        * **tag** (str, optional): New tag name.
        * **description** (str, optional): New description.
        * **alarm_type** (str, optional): New alarm type.
        * **trigger_value** (float, optional): New trigger value.
        * **user** (User, optional): User performing the update.

        **Returns:**

        * **tuple[Alarm, str]**: The updated Alarm object and a status message.
        """
        alarm = self.get_alarm(id=id)
        if name:

            if self.get_alarm_by_name(name=name):

                return f"Alarm {name} is already defined"

        # Check if alarm is associated to same tag with same alarm type
        if not tag:
            tag = alarm.tag
        tag_name = _normalize_tag_name(tag)
        if not alarm_type:
            alarm_type = alarm.alarm_setpoint.type
        else:
            # Convert string to TriggerType if needed
            from ..alarms.trigger import TriggerType
            if isinstance(alarm_type, str):
                alarm_type = TriggerType(alarm_type.upper())
            elif hasattr(alarm_type, 'value'):
                # If it's already a TriggerType, use it directly
                pass
            else:
                # If it's a StringType or similar, extract the value
                alarm_type = TriggerType(alarm_type.value.upper() if hasattr(alarm_type, 'value') else str(alarm_type).upper())
        
        if not trigger_value:
            trigger_value = alarm.alarm_setpoint.value
        elif isinstance(trigger_value, FloatType):
            trigger_value = trigger_value.value

        # Get string value for validation
        alarm_type_str = alarm_type.value if hasattr(alarm_type, 'value') else str(alarm_type)
        
        trigger_value_message = self.__check_trigger_values(
            name=alarm.name,
            tag=tag_name,
            type=alarm_type_str,
            trigger_value=trigger_value
            )
        if trigger_value_message:

            return None, trigger_value_message

        self._unindex_alarm(alarm)
        alarm, message = alarm.put(
            user=user,
            name=name,
            tag=tag,
            description=description,
            alarm_type=alarm_type,
            trigger_value=trigger_value,
            on_delay=on_delay,
            off_delay=off_delay,
            on_delay_units=on_delay_units,
            off_delay_units=off_delay_units,
            )
        self._alarms[id] = alarm
        self._index_alarm(alarm)
        return alarm, message

    @logging_error_handler
    @set_event(message="Alarm deleted", classification="Configuration", priority=3, criticity=5)
    def delete_alarm(self, id:str, user:User=None):
        r"""
        Removes an alarm from the manager and takes it out of service.

        **Parameters:**

        * **id** (str): Alarm ID.
        * **user** (User, optional): User performing the deletion.
        """
        alarm = self._alarms.pop(id, None)
        if alarm is None:
            return None, f"Alarm {id} not found"

        self._unindex_alarm(alarm)
        try:
            alarm.detach_from_tag()
        except Exception:
            pass
        queue_observer = getattr(alarm, "_queue_observer", None)
        tag_name = _normalize_tag_name(alarm.tag)
        if queue_observer is not None and tag_name:
            try:
                self.tag_engine.detach(name=tag_name, observer=queue_observer)
            except Exception:
                pass
            alarm._queue_observer = None
        alarm.remove_from_service(user=user)

        return alarm, f"Alarm: {alarm.name} - Tag: {alarm.tag}"

    @logging_error_handler
    def get_alarm(self, id:str)->Alarm:
        r"""
        Retrieves an alarm by its ID.

        **Parameters:**

        * **id** (str): Alarm ID.

        **Returns:**

        * **Alarm**: The alarm object if found.
        """

        if id in self._alarms:
            alarm = self._alarms[id]
            return alarm if _scope_owns_alarm(alarm) else None

    @logging_error_handler
    def get_alarm_by_name(self, name:str)->Alarm:
        r"""
        Retrieves an alarm by its name.

        **Parameters:**

        * **name** (str): Alarm name.

        **Returns:**

        * **Alarm**: The alarm object if found.
        """
        alarm = self.peek_alarm(name=name)
        return alarm if _scope_owns_alarm(alarm) else None

    def peek_alarm(self, id: str | None = None, name: str | None = None):
        """Lookup without applying node scope; used to distinguish 403 from 404."""
        if id is not None:
            return self._alarms.get(id)
        if name is not None:
            return self._by_name.get(name)
        return None

    # @logging_error_handler
    # def get_alarms_by_tag(self, tag:str)->dict:
    #     r"""
    #     Retrieves all alarms associated with a specific tag (by name).

    #     **Parameters:**

    #     * **tag** (str): Tag name.

    #     **Returns:**

    #     * **dict**: A dictionary of {id: Alarm} objects.
    #     """
    #     alarms = dict()
    #     for id, alarm in self._alarms.items():

    #         if tag == alarm.tag:

    #             alarms[id] = alarm

    #     return alarms

    @logging_error_handler
    def get_alarms_by_kp_range(self, kp_min:float, kp_max:float, segment:str=None)->list:
        r"""
        Returns serialized alarms whose associated tag KP is within [kp_min, kp_max].

        **Parameters:**

        * **kp_min** (float): Lower bound for KP.
        * **kp_max** (float): Upper bound for KP.
        * **segment** (str, optional): If provided, only alarms whose tag belongs to this segment are returned.

        **Returns:**

        * **list**: List of serialized alarm dictionaries.
        """
        lower = min(kp_min, kp_max)
        upper = max(kp_min, kp_max)
        result = []
        for _, alarm in self.get_alarms().items():
            tag = alarm.tag
            if not hasattr(tag, 'get_kp'):
                continue
            kp = tag.get_kp()
            if kp is None:
                continue
            if not (lower <= kp <= upper):
                continue
            if segment is not None and alarm.segment != segment:
                continue
            result.append(alarm.serialize())
        return result

    @logging_error_handler
    def get_alarm_by_tag(self, tag:str)->list[Alarm]:
        r"""
        Retrieves a list of alarms associated with a specific tag.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **list[Alarm]**: List of Alarm objects.
        """
        tag_name = _normalize_tag_name(tag)
        return [
            alarm
            for alarm in self._by_tag_name.get(tag_name, [])
            if _scope_owns_alarm(alarm)
        ]

    @logging_error_handler
    def get_alarms(self)->dict:
        r"""
        Retrieves all registered alarms.

        **Returns:**

        * **dict**: Dictionary of all Alarm objects.
        """
        return {
            identifier: alarm
            for identifier, alarm in self._alarms.items()
            if _scope_owns_alarm(alarm)
        }

    @logging_error_handler
    def get_lasts_active_alarms(self, lasts:int=None)->list:
        r"""
        Retrieves the most recent active alarms.

        **Parameters:**

        * **lasts** (int, optional): Number of alarms to retrieve.

        **Returns:**

        * **list**: List of serialized active alarms sorted by timestamp.
        """
        original_list = [alarm.serialize() for _, alarm in self.get_alarms().items()]
        filtered_list = [elem for elem in original_list if elem['state']['alarm_status'].lower()=="active"]
        sorted_list = sorted(filtered_list, key=lambda x: x['timestamp'] if x['timestamp'] else '')
        if lasts and len(sorted_list) > lasts:
            # Newest active alarms for footer / on_connection hydrate.
            sorted_list = sorted_list[-lasts:]

        return sorted_list

    @logging_error_handler
    def serialize(self)->list:
        r"""
        Serializes all alarms managed by this instance.

        **Returns:**

        * **list**: List of serialized alarm dictionaries.
        """

        return [alarm.serialize() for _, alarm in self.get_alarms().items()]

    @set_event(message="Alarms acknowledged", classification="Control", priority=2, criticity=3)
    def acknowledge_all(self, user:User=None):
        r"""
        Acknowledge every owned UNACK / RTNUN alarm in one operator action.

        State machines transition in memory first (O(N) CPU, no I/O). Persistence
        is a single logger round-trip grouped by target ISA state, then socket
        payloads are emitted after every alarm has the same ack timestamp.
        """
        from datetime import datetime, timezone
        from ..timebase import quantize_datetime_ms
        from ..logger.alarms import AlarmsLoggerEngine

        now = quantize_datetime_ms(datetime.now(timezone.utc))
        acknowledged: list[Alarm] = []
        for alarm in self.get_alarms().values():
            if alarm.state not in (AlarmState.UNACK, AlarmState.RTNUN):
                continue
            if not alarm._acknowledge_in_memory(now):
                continue
            acknowledged.append(alarm)
        if not acknowledged:
            return None

        payloads = []
        for alarm in acknowledged:
            catalog = alarm.catalog_payload()
            payloads.append(
                {
                    "id": alarm.identifier,
                    "name": alarm.name,
                    "state": alarm.state.state,
                    "ack_timestamp": now,
                    "area": catalog.get("area"),
                    "tag": catalog.get("tag"),
                }
            )
        AlarmsLoggerEngine().acknowledge_many(payloads)
        for alarm in acknowledged:
            if alarm.sio:
                alarm.sio.emit("on.alarm", data=alarm.serialize())
        return self, len(acknowledged), f"{len(acknowledged)} alarms acknowledged"

    @logging_error_handler
    def get_tag_alarms(self)->list:
        r"""
        Retrieves a list of Tags that have alarms associated with them.

        **Returns:**

        * **list**: List of Tag objects.
        """
        result = [_alarm.tag_alarm for id, _alarm in self.get_alarms().items()]

        return result

    @logging_error_handler
    def tags(self)->list:
        r"""
        Retrieves a unique list of Tag names bound to alarms.

        **Returns:**

        * **list**: List of Tag names.
        """
        result = set()
        for _alarm in self.get_alarms().values():
            tag_name = _normalize_tag_name(_alarm.tag)
            if tag_name:
                result.add(tag_name)

        return list(result)

    @logging_error_handler
    def __check_trigger_values(self, name:str, tag:str, type:str, trigger_value:float)->None|str:
        r"""
        Validates trigger values to prevent logical conflicts (e.g., Low limit > High limit).

        **Parameters:**

        * **name** (str): Name of the new/updated alarm.
        * **tag** (str): Tag name.
        * **type** (str): Alarm type.
        * **trigger_value** (float): Trigger threshold.

        **Returns:**

        * **None|str**: None if valid, or an error message string if invalid.
        """
        alarms = self.get_alarm_by_tag(tag=tag)

        if alarms:

            for alarm in alarms:

                if alarm.name!=name:

                    if type==alarm.alarm_setpoint.type.value:

                        return f"Alarm Type {type} and alarm's tag {tag} duplicated"

                    if type=="LOW-LOW":

                        if trigger_value>=alarm.alarm_setpoint.value:

                            return f"Conflict definition with {alarm.name} in trigger value {trigger_value}>={alarm.alarm_setpoint.value}"

                    if type=="LOW":

                        if alarm.alarm_setpoint.type.value=="LOW-LOW":

                            if trigger_value<=alarm.alarm_setpoint.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}>={alarm.alarm_setpoint.value}"

                        else:

                            if trigger_value>=alarm.alarm_setpoint.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}>={alarm.alarm_setpoint.value}"

                    if type=="HIGH":

                        if alarm.alarm_setpoint.type.value=="HIGH-HIGH":

                            if trigger_value>=alarm.alarm_setpoint.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}<={alarm.alarm_setpoint.value}"

                        else:

                            if trigger_value<=alarm.alarm_setpoint.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}<={alarm.alarm_setpoint.value}"

                    if type=="HIGH-HIGH":

                        if trigger_value<=alarm.alarm_setpoint.value:

                            return f"Conflict definition with {alarm.name} in trigger value {trigger_value}<={alarm.alarm_setpoint.value}"

    @logging_error_handler
    def filter_by(self, **fields):
        r"""
        Filters historical alarms via the database model.

        **Parameters:**

        * **fields**: Filtering criteria (name, state, timestamp, etc.).

        **Returns:**

        * **tuple**: (Result data, HTTP status code 200).
        """

        return AlarmSummary.filter_by(**fields), 200

    @logging_error_handler
    def get_lasts(self, lasts:int=10):
        r"""
        Retrieves the last N alarm summary records.

        **Parameters:**

        * **lasts** (int): Number of records.

        **Returns:**

        * **tuple**: (List of records, HTTP status code 200).
        """

        return AlarmSummary.read_lasts(lasts=lasts), 200

    @logging_error_handler
    def summary(self)->dict:
        r"""
        Generates a summary of the current alarm manager state.

        **Returns:**

        * **dict**: Summary including total alarms, alarm names, and associated tags.
        """
        result = dict()
        alarms = [_alarm.name for id, _alarm in self.get_alarms().items()]
        result["length"] = len(alarms)
        result["alarms"] = alarms
        result["alarm_tags"] = self.get_tag_alarms()
        result["tags"] = self.tags()

        return result

    @logging_error_handler
    def attach(self, alarm_name:str):
        r"""
        Attaches a tag observer to a specific alarm's tag.

        **Parameters:**

        * **alarm_name** (str): Name of the alarm.
        """
        alarm = self.get_alarm_by_name(name=alarm_name)
        if alarm is None:
            return
        tag_name = _normalize_tag_name(alarm.tag)
        if not tag_name:
            return
        if getattr(alarm, "_queue_observer", None) is not None:
            return
        observer = TagObserver(self._tag_queue)
        alarm._queue_observer = observer
        self.tag_engine.attach(name=tag_name, observer=observer)

    @logging_error_handler
    def execute(self, tag_name:str):
        r"""
        Evaluates alarm conditions for a given tag based on its current value.
        
        Also handles auto-unshelving of alarms if their shelved duration has expired.

        **Parameters:**

        * **tag_name** (str): Name of the tag to evaluate.
        """
        value = self.tag_engine.get_value_by_name(tag_name=tag_name)['value']
        tag_obj = self.tag_engine.get_tag_by_name(name=tag_name)
        alarms = self.get_alarm_by_tag(tag=tag_name)

        for _alarm in alarms:

            if _alarm.state == AlarmState.SHLVD:

                _now = datetime.now()

                if _alarm._shelved_until:

                    if _now >= _alarm._shelved_until:

                        current_tag_value = tag_obj.value if tag_obj else None
                        _alarm.unshelve(current_value=current_tag_value)
                        try:
                            from ..utils.system_event_audit import clip, persist_system_event

                            persist_system_event(
                                message="Alarm unshelved automatically",
                                description=clip(
                                    f"alarm={_alarm.name} tag={tag_name}",
                                    256,
                                ),
                                classification="System",
                                priority=2,
                                criticity=2,
                            )
                        except Exception:
                            pass
                        continue

                    continue

                continue

            _alarm.update(value)
