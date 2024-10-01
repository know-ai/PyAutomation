from ..utils.units import *

class Time(EngUnit):
    """Creates a time object that can store a time value and 
    convert between units of time."""
    
    class Units(UnitSerializer):
        ms = 'ms'
        s = 's'
        minute = 'minute'
        hr = 'hr'
        day = 'day'
    
    conversions = {
        'ms' : 1000.0,
        's' : 1.0,
        'minute' : 1.0 / 60.0,
        'hr' : 1.0 / 60.0 / 60.0,
        'day' : 1.0 / 60.0 / 60.0 / 24.0
    }

    def __init__(self, value, unit):

        if unit not in Time.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Time.Units.list()}")
        
        super(Time, self).__init__(value=value, unit=unit)