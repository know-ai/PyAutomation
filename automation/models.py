# -*- coding: utf-8 -*-
"""automation/models.py

This module implements a Tags and other classes for
modelling the subjects involved in the core of the engine.
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
    Implement an abstract property type
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
        Documentation here
        """
        return self.__value

    @value.setter
    def value(self, value):
        
        self.__value = value
    
    @set_event(message=f"Attribute updated", classification="State Machine", priority=2, criticity=3)
    def set_value(self, value, user:User=None, name:str=None, machine=None):
        
        self.value = value
        
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

        if machine:
            
            if machine.sio:
                
                machine.sio.emit("on.machine", data=machine.serialize())

        if name=="machine_interval":
            
            return value, f"{name} To: {self.value.value} s."
        
        return value, f"{name} To: {self.value.value}"


class StringType(PropertyType):

    """
    Implement a Float Type
    """

    def __init__(self, default=None, unit=None):

        super(StringType, self).__init__(STRING, default, unit)


class FloatType(PropertyType):

    """
    Implement a Float Type
    """

    def __init__(self, default=None, unit=None):

        super(FloatType, self).__init__(FLOAT, default, unit)


class IntegerType(PropertyType):

    """
    Implement an Integer Typle
    """

    def __init__(self, default=None, unit=None):

        super(IntegerType, self).__init__(INTEGER, default, unit)

        
class BooleanType(PropertyType):

    """
    Implement a Boolean Type
    """

    def __init__(self, default=None, unit=None):

        super(BooleanType, self).__init__(BOOL, default, unit)


class ProcessType(FloatType):

    """
    Implement a Process Type

    Attributes

    - read_only: [bool] only read from CVT, used to field data.
    - tag: [Tag] Tag binded on CVT
    """

    def __init__(self, tag:Tag|None=None, default=None, read_only:bool=True, unit:str=None):
        
        self.tag = tag
        self.read_only = read_only
        
        super(ProcessType, self).__init__(default=default, unit=unit)
        
    @logging_error_handler
    def serialize(self):
        r"""
        Documentation here
        """
        tag = None
        if self.tag:

            tag = self.tag.serialize()

        value = None
        if self.value:
            
            if isinstance(self.value, (bool, float, int, str)):

                value = self.value

            elif isinstance(self.value, (BooleanType, FloatType, IntegerType, StringType)):

                value= self.value.value

        return {
            "value": value,
            "unit": self.unit,
            "tag": tag,
            "read_only": self.read_only
        }

