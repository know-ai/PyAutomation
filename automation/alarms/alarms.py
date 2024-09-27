# -*- coding: utf-8 -*-
"""pyautomation/alarms.py

This module implements all Alarms class definitions and Alarm Handlers.
"""
from datetime import datetime, timedelta
from ..tags import CVTEngine
from .states import AlarmState, Status, AlarmAttrs
from .trigger import Trigger, TriggerType
import secrets


class Alarm:
    r"""
    This class implements all definitions for Alarm object
    """

    tag_engine = CVTEngine()

    def __init__(
            self, 
            name:str, 
            tag:str, 
            description:str="", 
            identifier:str=None, 
            tag_alarm:str=None, 
            state:str=None,
            timestamp:str=None,
            acknowledged_timestamp:str=None
            ):
        from ..logger import DataLoggerEngine
        self.logger_engine = DataLoggerEngine()
        self.name = name
        self._tag = tag
        self._description = description
        self._value = False
        self._message = None
        self._state = AlarmState.NORM
        self._mnemonic = AlarmState.NORM.mnemonic
        if state:
            
            for _, attr in AlarmState.__dict__.items():
                
                if isinstance(attr, AlarmAttrs):
                    
                    if state==attr.state:
                        
                        self._state = attr
                        break
        self._trigger = Trigger()
        self._tag_alarm = tag_alarm
        self._enabled = True
        self._deadband = None
        self._priority = 0
        self._on_delay = None
        self._off_delay = None
        self._timestamp = None
        if timestamp:
            self._timestamp = datetime.strptime(timestamp, self.tag_engine.DATETIME_FORMAT)  
        self._acknowledged_timestamp = None
        if acknowledged_timestamp:
            self._acknowledged_timestamp = datetime.strptime(acknowledged_timestamp, self.tag_engine.DATETIME_FORMAT)
        self._shelved_time = None
        self.audible = False
        self._shelved_options_time = {
            'days': 0,
            'seconds': 0,
            'microseconds': 0,
            'milliseconds': 0,
            'minutes': 0,
            'hours': 0,
            'weeks': 0
        }
        self._shelved_until = None
        self.__default_operations()
        if identifier:
            self._id = identifier
        else:
            self._id =secrets.token_hex(4)

    def __default_operations(self):
        r"""
        Sets default operations from alarms
        """
        self._operations = {
            'acknowledge': False,
            'enable': False,
            'disable': True,
            'silence': False,
            'sound': True,
            'shelve': True,
            'suppress by design': True,
            'unsuppress by design': False,
            'out of service': True,
            'return to service': False,
            'reset': True
        }

    def get_operations(self)->dict:
        r"""
        Get alarms operations
        """
        return self._operations

    def update_alarm_definition(self, **kwargs):
        r"""
        Update alarm configuration

        **Parameters**
        
        * **name** (str): Alarm name
        * **tag** (str): Tag binded to alarm
        * **description** (str): Alarm description
        * **type** (str): Alarm type ['HIGH-HIGH', 'HIGH', 'LOW', 'LOW-LOW', 'BOOL']
        * **trigger_value** (float): Alarm trigger value

        """

        if 'type' in kwargs.keys():

            _type = kwargs.pop('type')
            if _type.upper() in ["HIGH-HIGH", "HIGH", "LOW", "LOW-LOW", "BOOL"]:

                self._trigger.type = _type

        if 'trigger_value' in kwargs.keys():
            trigger_value = kwargs.pop('trigger_value')
            self._trigger.value = float(trigger_value)

        for key, value in kwargs.items():

            setattr(self, f"_{key}", value)
        
        return self

    def get_trigger(self):
        r"""
        Gets Trigger object for alarm
        """

        return self._trigger

    def set_trigger(self, value, _type:str):
        r"""
        Sets Trigger object for alarm

        **Parameters**

        * **value**: (int - float - bool) Value at which the alarm is triggered
        * **_type**: (str) ["HIGH-HIGH" - "HIGH" - "LOW" - "LOW-LOW" - "BOOL"] Alarm type
        """
        self._trigger.value = value
        self._trigger.type = _type

    @property
    def value(self):
        r"""
        Property Sets and Gets current value of the tag that the alarm monitors
        """
        return self._value

    @value.setter
    def value(self, value):

        self._value = value

    @property
    def priority(self):
        r"""
        Property Sets and Gets current priority of an alarm
        """
        return self._priority

    @priority.setter
    def priority(self, value):

        self._priority = value

    @property
    def tag_alarm(self):
        r"""
        Property (str) Sets and Gets tag of the alarm
        """

        return self._tag_alarm

    @tag_alarm.setter
    def tag_alarm(self, tag):

        self._tag_alarm = tag

    def write_tag_alarm(self, value):
        r"""
        Documentation for write_tag_alarm
        """
        if self._tag_alarm:

            self.tag_engine.write_tag(self._tag, value)
    
    @property
    def name(self):
        r"""
        Property (str) Sets and Gets Alarm name
        """
        return self._name

    @name.setter
    def name(self, value:str):
        
        self._is_process_alarm = False

        if 'leak' not in value and 'iad' not in value:

            self._is_process_alarm = True

        self._name = value

    @property
    def tag(self):
        r"""
        Property (str) Sets and Gets tag of the CVT that alarm monitors
        """
        return self._tag

    @property
    def description(self):
        r"""
        Property (str) Sets and Gets alarm description
        """
        return self._description

    @description.setter
    def description(self, value):
        self._description = value

    @property
    def state(self):
        r"""
        Property (AlarmState Object) Sets and Gets Alarm state
        """
        return self._state

    @state.setter
    def state(self, _state):

        self._state = _state

        if self._state.state==AlarmState.UNACK.state:

            self._operations['silence'] = True
            self._operations['sound'] = False
            self.audible = True

        elif self._state.state==AlarmState.ACKED.state:
            
            self._operations['silence'] = False
            self._operations['sound'] = False
            self.audible = False

        elif self._state.state==AlarmState.RTNUN.state:

            self._operations['silence'] = False
            self._operations['sound'] = False
            self.audible = False
            # Persist on DB
            self.logger_engine.create_record_on_summary(name=self.name, state=self._state.state)

        elif self._state.state==AlarmState.NORM.state:

            self._operations['disable'] = True
            self._operations['silence'] = False
            self._operations['sound'] = False
            self.audible = False
            # Persist on DB
            self.logger_engine.create_record_on_summary(name=self.name, state=self._state.state)

    def trigger(self):
        r"""
        Trigger alarm in Unacknowledge state if the alarm is enabled
        """
        if not self.enabled and self.state.acknowledge_status==Status.NA.value:

            return
       
        self._timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.state = AlarmState.UNACK
        self._operations['acknowledge'] = True
        self._operations['shelve'] = True
        self._operations['suppress by design'] = True
        self._operations['out of service'] = True
        self._operations['enable'] = False
        self._operations['disable'] = False
    
    @property
    def enabled(self):
        r"""
        Property, check if alarm is enabled
        """
        return self._enabled

    def enable(self):
        r"""
        Enable or disable alarm according the parameter *value*

        **Parameters**

        * **value**: (bool) if *True* enable alarm, otherwise, disable it
        """

        self._enabled = True
        self._operations['disable'] = True
        self._operations['enable'] = False
        self._operations['shelve'] = True
        self._operations['suppress by design'] = True
        self._operations['unsuppress by design'] = False
        self._operations['out of service'] = True
        self._operations['reset'] = True

    def disable(self):
        r"""
        Enable or disable alarm according the parameter *value*

        **Parameters**

        * **value**: (bool) if *True* enable alarm, otherwise, disable it
        """

        self._enabled = False
        self._operations['disable'] = False
        self._operations['enable'] = True
        self._operations['acknowledge'] = False
        self._operations['silence'] = False
        self._operations['sound'] = False
        self._operations['shelve'] = False
        self._operations['suppress by design'] = False
        self._operations['unsuppress by design'] = False
        self._operations['out of service'] = False
        self._operations['return to service'] = False
        self._operations['reset'] = False
        self.silence()

    def acknowledge(self):
        r"""
        Allows you to acknowledge alarm triggered
        """
        if not self.enabled:

            return

        if self.state == AlarmState.UNACK:

            self.state = AlarmState.ACKED
            self.audible = False
        
        if self.state == AlarmState.RTNUN:
            
            self.state = AlarmState.NORM
            self.audible = False

        self._acknowledged_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._operations['acknowledge'] = False

    def silence(self):
        r"""
        Documentation here for silence alarm
        """
        if not self._enabled:

            return

        self.audible = False
        self._operations['silence'] = False

        if self._state.state==AlarmState.UNACK.state:
            
            self._operations['sound'] = True
        
        else:

            self._operations['sound'] = False

    def sound(self):
        r"""
        Documentation here for sound alarm
        """
        if not self._enabled:

            return

        if self.state.is_triggered:
        
            self.audible = True
            self._operations['sound'] = False
            
            if self._state.state==AlarmState.UNACK.state:
            
                self._operations['silence'] = True
            
            else:

                self._operations['silence'] = False
        
    def reset(self):
        r"""
        Returns alarm to normal condition
        """
        self._enabled = True
        self._timestamp = None
        self._acknowledged_timestamp = None
        self._silence = False
        self.state = AlarmState.NORM
        self.__default_operations()

    def shelve(
        self, 
        **options):
        r"""
        Set alarm to Shelved state

        **Parameters**

        * **days:** (int)
        * **seconds:** (int)
        * **minutes:** (int)
        * **hours:** (int)
        * **weeks:** (int)
        """
        options_time = {key: options[key] if key in options else self._shelved_options_time[key] for key in self._shelved_options_time}
        
        if options_time!=self._shelved_options_time:
            
            self._shelved_time = datetime.now()
            self._shelved_until = self._shelved_time + timedelta(**options_time)
        
        self.state = AlarmState.SHLVD
        self.audible = False
        self._operations['acknowledge'] = False
        self._operations['enable'] = False
        self._operations['disable'] = False
        self._operations['silence'] = False
        self._operations['sound'] = False
        self._operations['shelve'] = False
        self._operations['suppress by design'] = False
        self._operations['unsuppress by design'] = False
        self._operations['out of service'] = False
        self._operations['return to service'] = False
        self._operations['reset'] = True

    def unshelve(self):
        r"""
        Set Alarm to normal state after Shelved state
        """
        self._shelved_time = None
        self._shelved_until = None
        self.state = AlarmState.NORM
        self.audible = False
        self.__default_operations()

    def suppress_by_design(self):
        r"""
        Suppress Alarm by design
        """
        self.state = AlarmState.DSUPR
        self._operations['acknowledge'] = False
        self._operations['enable'] = False
        self._operations['disable'] = False
        self._operations['silence'] = False
        self._operations['sound'] = False
        self._operations['shelve'] = False
        self._operations['suppress by design'] = False
        self._operations['unsuppress by design'] = True
        self._operations['out of service'] = False
        self._operations['return to service'] = False
        self._operations['reset'] = False
        self.audible = False

    def unsuppress_by_design(self):
        r"""
        Unsuppress alarm, return to normal state after suppress state
        """
        self.state = AlarmState.NORM
        self.audible = False
        self.__default_operations()

    def out_of_service(self):
        r"""
        Remove alarm from service
        """
        self.state = AlarmState.OOSRV
        self.audible = False
        self._operations['acknowledge'] = False
        self._operations['enable'] = False
        self._operations['disable'] = False
        self._operations['silence'] = False
        self._operations['sound'] = False
        self._operations['shelve'] = False
        self._operations['suppress by design'] = False
        self._operations['unsuppress by design'] = False
        self._operations['out of service'] = False
        self._operations['return to service'] = True
        self._operations['reset'] = False
    
    def return_to_service(self):
        r"""
        Return alarm to normal condition after Out Of Service state
        """
        self.state = AlarmState.NORM
        self.audible = False
        self.__default_operations()

    def update(self, value):
        r"""
        Update alarm state according the tag value that the alarm monitors and according its state

        **Parameters**

        * **value**: (int - float - bool) according alarm type, current tag value
        """
        if not self.enabled and self.state.acknowledge_status==Status.NA.value:

            return

        self._value = value

        _type = self._trigger.type

        if self.state in (AlarmState.NORM, AlarmState.RTNUN):

            if (_type == TriggerType.H) or (_type == TriggerType.HH):
                
                if value >= self._trigger.value:
                
                    self.trigger()

            elif (_type == TriggerType.L) or (_type == TriggerType.LL):
                
                if value <= self._trigger.value:
                
                    self.trigger()

            elif _type == TriggerType.B:

                if value == self._trigger.value:
                
                    self.trigger()

        elif self.state == AlarmState.UNACK:

            if (_type == TriggerType.H) or (_type == TriggerType.HH):
                
                if value < self._trigger.value:
                
                    self.state = AlarmState.RTNUN

            elif (_type == TriggerType.L) or (_type == TriggerType.LL):
                
                if value > self._trigger.value:
                
                    self.state = AlarmState.RTNUN

            elif _type == TriggerType.B:

                if value != self._trigger.value:
                
                    self.state = AlarmState.RTNUN

        elif self.state == AlarmState.ACKED:

            if (_type == TriggerType.H) or (_type == TriggerType.HH):
                
                if value < self._trigger.value:
                
                    self.state = AlarmState.NORM

            elif (_type == TriggerType.L) or (_type == TriggerType.LL):
                
                if value > self._trigger.value:
                
                    self.state = AlarmState.NORM

            elif _type == TriggerType.B:
                
                if value != self._trigger.value:
                
                    self.state = AlarmState.NORM

    def serialize(self):
        r"""
        Allows you to serialize alarm to a dict jsonable

        **Return**

        * **alarm_info**: (dict) A jsonable dictionary
        """
        return {
            "id": self._id,
            "timestamp": self._timestamp,
            "name": self.name,
            "tag": self.tag,
            "tag_alarm": self.tag_alarm,
            "state": self.state.state,
            "mnemonic": self.state.mnemonic,
            "enabled": self.enabled,
            "process": self.state.process_condition,
            "triggered": self.state.is_triggered,
            "trigger_value": self._trigger.value,
            "acknowledged": self.state.is_acknowledged(),
            "acknowledged_timestamp": self._acknowledged_timestamp,
            "value": self._value,
            "audible": self.audible,
            "type": self._trigger.type.value,
            "description": self.description,
            "operations": self.get_operations(),
            "priority": self.priority,
            "is_process_alarm": self._is_process_alarm
        }
