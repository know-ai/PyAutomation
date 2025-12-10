# -*- coding: utf-8 -*-
"""automation/models.py

This module implements data models used within state machines and core logic to represent
properties and process variables with strong typing and event handling.
"""
from .modules.users.users import User
from .tags.tag import Tag
from .utils.decorators import set_event, logging_error_handler
from datetime import datetime, timezone


FLOAT = "float"
INTEGER = "int"
BOOL = "bool"
STRING = "str"

class PropertyType:

    """
    Abstract base class for property types.

    Wraps a value with type information and unit. Used for state machine attributes
    that need to be serialized or monitored.
    """

    def __init__(self, _type, default=None, unit=None):
        from .tags.cvt import CVTEngine
        from .opcua.subscription import DAS
        self._type = _type
        self.unit = unit
        self.__value = default
        self.cvt = CVTEngine()
        self.das = DAS()

    @property
    def value(self):
        r"""
        Gets the stored value.
        """
        return self.__value

    @value.setter
    def value(self, value):
        
        self.__value = value
    
    @set_event(message=f"Attribute updated", classification="State Machine", priority=2, criticity=3)
    def set_value(self, value, user:User=None, name:str=None, machine=None):
        r"""
        Sets the value and triggers updates (CVT, Events, SocketIO).

        **Parameters:**

        * **value**: The new value object.
        * **user** (User, optional): User initiating the change.
        * **name** (str, optional): Attribute name.
        * **machine** (StateMachine, optional): The parent state machine instance.
        """
        
        if isinstance(self, ProcessType):

            if not self.read_only:

                if hasattr(self, "tag"):

                    if self.tag:

                        if hasattr(machine, "data_timestamp"):
                            timestamp = machine.data_timestamp
                        else:
                            timestamp = datetime.now(timezone.utc)
                        val = self.tag.value.convert_value(value=value.value, from_unit=self.tag.get_unit(), to_unit=self.tag.get_display_unit())
                        self.tag.value.set_value(value=val, unit=self.tag.get_display_unit()) 
                        self.cvt.set_value(id=self.tag.id, value=val, timestamp=timestamp)
                        if self.tag.get_name() in self.das.buffer:
                            self.das.buffer[self.tag.get_name()]["timestamp"](timestamp)
                            self.das.buffer[self.tag.get_name()]["values"](val)
        
        if self.value:
            if value.value!=self.value.value:
                if machine:
                    if machine.sio:
                        if name:
                            payload = {machine.name.value: {name: value.value}}
                            machine.sio.emit("on.machine.property", data=payload)
                            machine.sio.emit("on.machine", data=machine.serialize())

        if name=="machine_interval":
            
            return value, f"{name} To: {value.value} s."
        
        self.value = value
        
        return value, f"{name} To: {value.value}"


class StringType(PropertyType):

    """
    Represents a String property.
    """

    def __init__(self, default=None, unit=None):

        super(StringType, self).__init__(STRING, default, unit)


class FloatType(PropertyType):

    """
    Represents a Float property.
    """

    def __init__(self, default=None, unit=None):

        super(FloatType, self).__init__(FLOAT, default, unit)


class IntegerType(PropertyType):

    """
    Represents an Integer property.
    """

    def __init__(self, default=None, unit=None):

        super(IntegerType, self).__init__(INTEGER, default, unit)

        
class BooleanType(PropertyType):

    """
    Represents a Boolean property.
    """

    def __init__(self, default=None, unit=None):

        super(BooleanType, self).__init__(BOOL, default, unit)


class ProcessType(FloatType):

    """
    Represents a process variable linked to a Tag.

    **Attributes:**

    * **read_only** (bool): If True, value comes from CVT (input). If False, writes to CVT (output).
    * **tag** (Tag): The associated Tag object.
    """

    def __init__(self, tag:Tag|None=None, default=None, read_only:bool=True, unit:str=None):
        
        self.tag = tag
        self.read_only = read_only
        
        super(ProcessType, self).__init__(default=default, unit=unit)
        
    @logging_error_handler
    def serialize(self):
        r"""
        Serializes the process variable.

        **Returns:**

        * **dict**: {value, unit, tag, read_only}
        """
        tag = None
        if self.tag:

            tag = self.tag.serialize()

        value = None
        if self.value:
            
            if isinstance(self.value, (bool, float, int, str)):

                value = self.value

            elif isinstance(self.value, (BooleanType, FloatType, IntegerType, StringType)):

                value = self.value.value

        return {
            "value": value,
            "unit": self.unit,
            "tag": tag,
            "read_only": self.read_only
        }
