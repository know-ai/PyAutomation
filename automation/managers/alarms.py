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
from ..utils.decorators import set_event, logging_error_handler
from flask_socketio import SocketIO


class AlarmManager(Singleton):
    r"""
    Singleton class that manages all alarms in the system.

    It handles the creation, update, deletion, and retrieval of alarms.
    It also validates trigger conditions and manages communication with the frontend via SocketIO.
    """

    def __init__(self):

        self._alarms:dict[Alarm] = dict()
        self._tag_queue = queue.Queue()
        self.tag_engine = CVTEngine()

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
            sio:SocketIO|None=None
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

        alarm = Alarm(
            name=name,
            tag=self.tag_engine.get_tag_by_name(name=tag),
            description=description,
            alarm_type=StringType(type),
            alarm_setpoint=FloatType(trigger_value),
            identifier=identifier,
            state=state,
            timestamp=timestamp,
            ack_timestamp=ack_timestamp,
            user=user,
            reload=reload
        )
        alarm.set_socketio(sio=sio)
        self._alarms[alarm.identifier] = alarm

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
            user:User=None
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
        if not alarm_type:
            alarm_type = alarm.alarm_setpoint.type
        if not trigger_value:
            trigger_value = FloatType(alarm.alarm_setpoint.value)

        trigger_value_message = self.__check_trigger_values(
            name=alarm.name,
            tag=tag,
            type=alarm_type,
            trigger_value=trigger_value
            )
        if trigger_value_message:

            return None, trigger_value_message

        alarm, message = alarm.put(
            user=user,
            name=name,
            tag=tag,
            description=description,
            alarm_type=alarm_type,
            trigger_value=trigger_value
            )
        self._alarms[id] = alarm

    @logging_error_handler
    @set_event(message=f"Deleted", classification="Alarm", priority=3, criticity=5)
    def delete_alarm(self, id:str, user:User=None):
        r"""
        Removes an alarm from the manager and takes it out of service.

        **Parameters:**

        * **id** (str): Alarm ID.
        * **user** (User, optional): User performing the deletion.
        """
        if id in self._alarms:

            alarm = self._alarms.pop(id)
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

            return self._alarms[id]

    @logging_error_handler
    def get_alarm_by_name(self, name:str)->Alarm:
        r"""
        Retrieves an alarm by its name.

        **Parameters:**

        * **name** (str): Alarm name.

        **Returns:**

        * **Alarm**: The alarm object if found.
        """
        for id, alarm in self._alarms.items():

            if name == alarm.name:

                return self._alarms[str(id)]

    @logging_error_handler
    def get_alarms_by_tag(self, tag:str)->dict:
        r"""
        Retrieves all alarms associated with a specific tag (by name).

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **dict**: A dictionary of {id: Alarm} objects.
        """
        alarms = dict()
        for id, alarm in self._alarms.items():

            if tag == alarm.tag:

                alarms[id] = alarm

        return alarms

    @logging_error_handler
    def get_alarm_by_tag(self, tag:str)->list[Alarm]:
        r"""
        Retrieves a list of alarms associated with a specific tag.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **list[Alarm]**: List of Alarm objects.
        """
        alarms = list()
        for _, alarm in self._alarms.items():

            if tag == alarm.tag:

                alarms.append(alarm)

        return alarms

    @logging_error_handler
    def get_alarms(self)->dict:
        r"""
        Retrieves all registered alarms.

        **Returns:**

        * **dict**: Dictionary of all Alarm objects.
        """
        return self._alarms

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
        if lasts:

            if len(sorted_list)>lasts:

                sorted_list = sorted_list[0:lasts]

        return sorted_list

    @logging_error_handler
    def serialize(self)->list:
        r"""
        Serializes all alarms managed by this instance.

        **Returns:**

        * **list**: List of serialized alarm dictionaries.
        """

        return [alarm.serialize() for _, alarm in self._alarms.items()]

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
        result = set([_alarm.tag for id, _alarm in self.get_alarms().items()])

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
        def attach_observer(entity):

            _tag = entity.tag

            observer = TagObserver(self._tag_queue)
            self.tag_engine.attach(name=_tag, observer=observer)

        alarm = self.get_alarm_by_name(name=alarm_name)
        attach_observer(alarm)

    @logging_error_handler
    def execute(self, tag_name:str):
        r"""
        Evaluates alarm conditions for a given tag based on its current value.
        
        Also handles auto-unshelving of alarms if their shelved duration has expired.

        **Parameters:**

        * **tag_name** (str): Name of the tag to evaluate.
        """
        value = self.tag_engine.get_value_by_name(tag_name=tag_name)['value']

        for _, _alarm in self._alarms.items():

            if _alarm.state == AlarmState.SHLVD:

                _now = datetime.now()

                if _alarm._shelved_until:

                    if _now >= _alarm._shelved_until:

                        _alarm.unshelve()
                        continue

                    continue

                continue

            if tag_name==_alarm.tag:

                _alarm.update(value)
