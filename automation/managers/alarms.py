# -*- coding: utf-8 -*-
"""pyhades/managers/alarms.py
This module implements Alarm Manager.
"""
from datetime import datetime
import queue
from automation.singleton import Singleton
from ..tags import CVTEngine, TagObserver, Tag
from ..alarms import AlarmState
from ..alarms.alarms import Alarm
from ..alarms.trigger import Trigger


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
            description:str=""
        )->dict:
        r"""
        Append alarm to the Alarm Manager

        **Paramters**

        * **alarm**: (Alarm Object)

        **Returns**

        * **None**
        """
        alarm = Alarm(name=name, tag=tag, description=description)
        alarm.set_trigger(value=trigger_value, _type=type)
        if not self.get_alarm_by_name(name):
        
            self._alarms[alarm._id] = alarm

        else:

            return f"Alarm {name} is already defined"
        
        self.attach_all()

    def update_alarm(self, id:str, **kwargs):
        r"""
        Updates alarm attributes

        **Parameters**

        * **id** (int).
        * **name** (str)[Optional]:
        * **tag** (str)[Optional]:
        * **description** (str)[Optional]:
        * **alarm_type** (str)[Optional]:
        * **trigger** (float)[Optional]:

        **Returns**

        * **alarm** (dict) Alarm Object jsonable
        """
        alarm = self._alarms[id]
        if "name" in kwargs:
            
            if self.get_alarm_by_name(kwargs["name"]):
                
                return f"Alarm {kwargs['name']} is already defined"
        
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

    def get_alarm_by_tag(self, tag:str)->dict:
        r"""
        Gets alarm associated to some tag

        **Parameters**

        * **tag**: (str) tag name binded to alarm

        **Returns**

        * **alarm** (list) of alarm objects
        """
        for id, alarm in self._alarms.items():
            
            if tag == alarm.tag:
                
                return {
                    id: alarm
                }

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
