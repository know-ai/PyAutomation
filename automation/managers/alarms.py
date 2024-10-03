# -*- coding: utf-8 -*-
"""pyhades/managers/alarms.py
This module implements Alarm Manager.
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


class AlarmManager(Singleton):
    r"""
    This class implements all definitions for the Alarm Management System
    """

    def __init__(self):

        self._alarms = dict()
        self._tag_queue = queue.Queue()
        self.tag_engine = CVTEngine()

    def get_queue(self)->queue.Queue:
        r"""
        Documentation here
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
            reload:bool=False
        )->tuple[Alarm, str]:
        r"""
        Append alarm to the Alarm Manager

        **Paramters**

        * **alarm**: (Alarm Object)

        **Returns**

        * **None**
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
        Updates alarm attributes

        **Parameters**

        * **id** (int).
        * **name** (str)[Optional]:
        * **tag** (str)[Optional]:
        * **description** (str)[Optional]:
        * **type** (str)[Optional]:
        * **trigger** (float)[Optional]:

        **Returns**

        * **alarm** (dict) Alarm Object jsonable
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
    def delete_alarm(self, id:str):
        r"""
        Removes alarm

        **Paramters**

        * **id** (int): Alarm ID
        """
        if id in self._alarms:

            alarm = self._alarms.pop(id)

        return alarm, f"Alarm: {alarm.name} - Tag: {alarm.tag}"

    @logging_error_handler
    def get_alarm(self, id:str)->Alarm:
        r"""
        Gets alarm from the Alarm Manager by id

        **Paramters**

        * **id**: (int) Alarm ID

        **Returns**

        * **alarm** (Alarm Object)
        """

        if id in self._alarms:

            return self._alarms[id]

    @logging_error_handler
    def get_alarm_by_name(self, name:str)->Alarm:
        r"""
        Gets alarm from the Alarm Manager by name

        **Paramters**

        * **name**: (str) Alarm name

        **Returns**

        * **alarm** (Alarm Object)
        """
        for id, alarm in self._alarms.items():

            if name == alarm.name:

                return self._alarms[str(id)]

    @logging_error_handler
    def get_alarms_by_tag(self, tag:str)->dict:
        r"""
        Gets all alarms associated to some tag

        **Parameters**

        * **tag**: (str) tag name binded to alarm

        **Returns**

        * **alarm** (dict) of alarm objects
        """
        alarms = dict()
        for id, alarm in self._alarms.items():

            if tag == alarm.tag:

                alarms[id] = alarm

        return alarms

    @logging_error_handler
    def get_alarm_by_tag(self, tag:str)->list[Alarm]:
        r"""
        Gets alarm associated to some tag

        **Parameters**

        * **tag**: (str) tag name binded to alarm

        **Returns**

        * **alarm** (list) of alarm objects
        """
        alarms = list()
        for _, alarm in self._alarms.items():

            if tag == alarm.tag:

                alarms.append(alarm)

        return alarms

    @logging_error_handler
    def get_alarms(self)->dict:
        r"""
        Gets all alarms

        **Returns**

        * **alarms**: (dict) Alarm objects
        """
        return self._alarms

    @logging_error_handler
    def get_lasts_active_alarms(self, lasts:int=None)->list:
        r"""
        Documentation here
        """
        original_list = [alarm.serialize() for _, alarm in self.get_alarms().items()]
        filtered_list = [elem for elem in original_list if elem['triggered']]
        sorted_list = sorted(filtered_list, key=lambda x: x['timestamp'] if x['timestamp'] else '')
        if lasts:

            if len(sorted_list)>lasts:

                sorted_list = sorted_list[0:lasts]

        return sorted_list

    @logging_error_handler
    def serialize(self)->list:
        r"""
        Documentation here
        """

        return [alarm.serialize() for _, alarm in self._alarms.items()]

    @logging_error_handler
    def get_tag_alarms(self)->list:
        r"""
        Gets all tag alarms defined

        **Returns**

        * **tags_alarms**: (list) alarm tags
        """
        result = [_alarm.tag_alarm for id, _alarm in self.get_alarms().items()]

        return result

    @logging_error_handler
    def tags(self)->list:
        r"""
        Gets all tags variables binded into alarms

        **Returns**

        * **tags**: (list)
        """
        result = set([_alarm.tag for id, _alarm in self.get_alarms().items()])

        return list(result)

    @logging_error_handler
    def __check_trigger_values(self, name:str, tag:str, type:str, trigger_value:float)->None|str:
        r"""
        Documentation here
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
        Documentation here
        """

        return AlarmSummary.filter_by(**fields), 200

    @logging_error_handler
    def get_lasts(self, lasts:int=10):
        r"""
        Documentation here
        """

        return AlarmSummary.read_lasts(lasts=lasts), 200

    @logging_error_handler
    def summary(self)->dict:
        r"""
        Summarizes all Alarm Manager

        **Returns**

        * **summary**: (dict)
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

        def attach_observer(entity):

            _tag = entity.tag

            observer = TagObserver(self._tag_queue)
            self.tag_engine.attach(name=_tag, observer=observer)

        alarm = self.get_alarm_by_name(name=alarm_name)
        attach_observer(alarm)

    @logging_error_handler
    def execute(self, tag_name:str):
        r"""
        Execute update state value of alarm if the value store in cvt for tag
        reach alarm threshold values

        **Paramters**

        * **tag**: (str) Tag in CVT
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
