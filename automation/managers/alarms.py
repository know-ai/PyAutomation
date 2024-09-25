# -*- coding: utf-8 -*-
"""pyhades/managers/alarms.py
This module implements Alarm Manager.
"""
from datetime import datetime
import queue
from automation.singleton import Singleton
from ..tags import CVTEngine, TagObserver
from ..alarms import AlarmState
from ..alarms.alarms import Alarm, AlarmState
from ..dbmodels.alarms import AlarmSummary, AlarmStates, Alarms
from ..dbmodels.tags import Tags

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


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
    
    def append_alarm(
            self, 
            name:str, 
            tag:str, 
            type:str="BOOL", 
            trigger_value:bool|float=True, 
            description:str="",
            identifier:str=None,
            tag_alarm:str=None,
            state:str="Normal",
            timestamp:str=None,
            acknowledged_timestamp:str=None
        )->dict:
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
            
            return f"Alarm {name} is already defined"

        # Check if alarm is associated to same tag with same alarm type
        trigger_value_message = self.__check_trigger_values(name=name, tag=tag, type=type, trigger_value=trigger_value)
        if trigger_value_message:

            return trigger_value_message
                
        alarm = Alarm(
            name=name, 
            tag=tag, 
            description=description, 
            identifier=identifier, 
            tag_alarm=tag_alarm, 
            state=state,
            timestamp=timestamp,
            acknowledged_timestamp=acknowledged_timestamp)
        alarm.set_trigger(value=trigger_value, _type=type)
        self._alarms[alarm._id] = alarm
        self.attach_all()

    def update_alarm(self, id:str, **kwargs):
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
        if "name" in kwargs:
            
            if self.get_alarm_by_name(kwargs["name"]):
                
                return f"Alarm {kwargs['name']} is already defined"
            
        # Check if alarm is associated to same tag with same alarm type
        tag = alarm.tag
        if "tag" in kwargs:
            tag = kwargs["tag"]
        type = alarm._trigger.type.value
        if "type" in kwargs:
            type = kwargs["type"]
        trigger_value = alarm._trigger.value
        if "trigger_value" in kwargs:
            trigger_value = float(kwargs["trigger_value"])
        
        trigger_value_message = self.__check_trigger_values(name=alarm.name, tag=tag, type=type, trigger_value=trigger_value)
        if trigger_value_message:

            return trigger_value_message
        
        alarm = alarm.update_alarm_definition(**kwargs)
        self._alarms[id] = alarm

    def delete_alarm(self, id:str):
        r"""
        Removes alarm

        **Paramters**

        * **id** (int): Alarm ID
        """
        if id in self._alarms: 
                
            self._alarms.pop(id)

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

    def get_alarm_by_tag(self, tag:str)->list[Alarm]:
        r"""
        Gets alarm associated to some tag

        **Parameters**

        * **tag**: (str) tag name binded to alarm

        **Returns**

        * **alarm** (list) of alarm objects
        """
        alarms = list()
        for id, alarm in self._alarms.items():
            
            if tag == alarm.tag:
                
                alarms.append(alarm)

        return alarms

    def get_alarms(self)->dict:
        r"""
        Gets all alarms

        **Returns**

        * **alarms**: (dict) Alarm objects
        """
        return self._alarms
    
    def serialize(self)->list:
        r"""
        Documentation here
        """

        return [alarm.serialize() for _, alarm in self._alarms.items()]

    def get_tag_alarms(self)->list:
        r"""
        Gets all tag alarms defined

        **Returns**

        * **tags_alarms**: (list) alarm tags
        """
        result = [_alarm.tag_alarm for id, _alarm in self.get_alarms().items()]

        return result

    def tags(self)->list:
        r"""
        Gets all tags variables binded into alarms

        **Returns**

        * **tags**: (list)
        """
        result = set([_alarm.tag for id, _alarm in self.get_alarms().items()])

        return list(result)

    def __check_trigger_values(self, name:str, tag:str, type:str, trigger_value:float)->None|str:
        r"""
        Documentation here
        """
        alarms = self.get_alarm_by_tag(tag=tag)

        if alarms:

            for alarm in alarms:

                if alarm.name!=name:
                    
                    if type==alarm._trigger.type.value:

                        return f"Alarm Type {type} and alarm's tag {tag} duplicated"
                    
                    if type=="LOW-LOW":

                        if trigger_value>=alarm._trigger.value:

                            return f"Conflict definition with {alarm.name} in trigger value {trigger_value}>={alarm._trigger.value}"

                    if type=="LOW":

                        if alarm._trigger.type.value=="LOW-LOW":

                            if trigger_value<=alarm._trigger.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}>={alarm._trigger.value}"

                        else:

                            if trigger_value>=alarm._trigger.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}>={alarm._trigger.value}"

                    if type=="HIGH":

                        if alarm._trigger.type.value=="HIGH-HIGH":

                            if trigger_value>=alarm._trigger.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}<={alarm._trigger.value}"

                        else:

                            if trigger_value<=alarm._trigger.value:

                                return f"Conflict definition with {alarm.name} in trigger value {trigger_value}<={alarm._trigger.value}"

                    if type=="HIGH-HIGH":

                        if trigger_value<=alarm._trigger.value:

                            return f"Conflict definition with {alarm.name} in trigger value {trigger_value}<={alarm._trigger.value}"
                        
    def filter_by(self, **fields):
        r"""
        Documentation here
        """
        payload = fields
        
        _query = ''

        # State
        if 'states' in payload.keys():
            
            states = payload["states"]
            subquery = AlarmStates.select(AlarmStates.id).where(AlarmStates.name.in_(states))
            _query = AlarmSummary.select().join(AlarmStates).where(AlarmStates.id.in_(subquery)).order_by(AlarmSummary.id.desc())

        if 'names' in payload.keys():
            
            names = payload["names"]
            subquery = Alarms.select(Alarms.id).where(Alarms.name.in_(names))

            if _query:

                _query = _query.select().join(Alarms).where(Alarms.id.in_(subquery)).order_by(AlarmSummary.id.desc())

            else:
                _query = AlarmSummary.select().join(Alarms).where(Alarms.id.in_(subquery)).order_by(AlarmSummary.id.desc())

        if 'tags' in payload.keys():
            
            tags = payload["tags"]
            subquery = Tags.select(Tags.id).where(Tags.name.in_(tags))
            subquery = Alarms.select(Alarms.id).join(Tags).where(Tags.id.in_(subquery))

            if _query:
    
                _query = _query.select().join(Alarms).where(Alarms.id.in_(subquery)).order_by(AlarmSummary.id.desc())

            else:
                
                _query = AlarmSummary.select().join(Alarms).where(Alarms.id.in_(subquery)).order_by(AlarmSummary.id.desc())

        separator = '.'
        # GREATER THAN TIMESTAMP
        if 'greater_than_timestamp' in payload.keys():

            greater_than_timestamp = payload.pop('greater_than_timestamp')
            greater_than_timestamp = datetime.strptime(greater_than_timestamp.replace("T", " ").split(separator, 1)[0], "%Y-%m-%d %H:%M:%S")
            
            if _query:

                _query = _query.select().where(AlarmSummary.alarm_time > greater_than_timestamp).order_by(AlarmSummary.id.desc())

            else:

                _query = AlarmSummary.select().where(AlarmSummary.alarm_time > greater_than_timestamp).order_by(AlarmSummary.id.desc())

        # LESS THAN TIMESTAMP
        if 'less_than_timestamp' in payload.keys():

            less_than_timestamp = payload.pop('less_than_timestamp')
            less_than_timestamp = datetime.strptime(less_than_timestamp.replace("T", " ").split(separator, 1)[0], "%Y-%m-%d %H:%M:%S")
            
            if _query:

                _query = _query.select().where(AlarmSummary.alarm_time < less_than_timestamp).order_by(AlarmSummary.id.desc())

            else:

                _query = AlarmSummary.select().where(AlarmSummary.alarm_time < less_than_timestamp).order_by(AlarmSummary.id.desc())


        result = [alarm.serialize() for alarm in _query]

        return result, 200

    def get_lasts(self, lasts:int=10):
        r"""
        Documentation here
        """
        _query = AlarmSummary.select().order_by(AlarmSummary.id.desc()).limit(lasts)
        result = [alarm.serialize() for alarm in _query]

        return result, 200

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

    def attach_all(self):

        def attach_observers(entity):

            _tag = entity.tag

            observer = TagObserver(self._tag_queue)
            self.tag_engine.attach(name=_tag, observer=observer)

        for _, _alarm in self._alarms.items():
            
            attach_observers(_alarm)

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
