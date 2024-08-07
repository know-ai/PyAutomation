# -*- coding: utf-8 -*-
"""automation/models.py

This module implements a Tags and other classes for
modelling the subjects involved in the core of the engine.
"""
from inspect import ismethod

FLOAT = "float"
INTEGER = "int"
BOOL = "bool"
STRING = "str"

class PropertyType:

    """
    Implement an abstract property type
    """

    def __init__(self, _type, default=None, unit=None):
        
        self._type = _type
        self.unit = unit
        self.__value = default

    @property
    def value(self):
        r"""
        Documentation here
        """
        return self.__value

    @value.setter
    def value(self, value):
            
        self.__value = value


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


class Model(object):

    """
    Implement an abstract model for inheritance
    """

    def __init__(self, **kwargs):

        attrs = self.get_attributes()

        for key, value in attrs.items():
            
            if key in kwargs:
                default = kwargs[key]
            else:
                try:
                    default = value.default
                    _type = value._type
                    
                except Exception as e:
                    continue

            if default:
                setattr(self, key, default)
            else:
                if _type == FLOAT:
                    setattr(self, key, 0.0)
                elif _type == INTEGER:
                    setattr(self, key, 0)
                elif _type == BOOL:
                    setattr(self, key, False)
                elif _type == STRING:
                    setattr(self, key, "")

        self.attrs = attrs

    def __getattribute__(self, attr):
        
        method = object.__getattribute__(self, attr)
        
        if not method:
            return method

        if callable(method):
             
            def new_method(*args, **kwargs):
                 
                result = method(*args, **kwargs)
                name = method.__name__

                if ("__" not in name) and (name != "save"):
                    try:
                        self.save()
                    except Exception as e:
                        pass

                return result
            return new_method
        else:
            return method

    def __copy__(self):
        newone = type(self)()
        newone.__dict__.update(self.__dict__)
        return newone

    @classmethod
    def get_attributes(cls):

        result = dict()
        
        props = cls.__dict__

        for key, value in props.items():
            
            if hasattr(value, '__call__'):
                continue
            if isinstance(value, cls):
                continue
            if not ismethod(value):

                if "__" not in key:
                    result[key] = value

        return result

    def set_attr(self, name, value):
        
        setattr(self, name, value)

    def get_attr(self, name):

        result = getattr(self, name)
        return result

    @classmethod
    def set(cls, tag, obj):

        obj.tag = tag

    def serialize(self):

        result = dict()

        attrs = self.get_attributes()

        for key in attrs:
            value = getattr(self, key)
            result[key] = value

        return result

    def _load(self, values):

        for key, value in values.items():

            setattr(self, key, value)