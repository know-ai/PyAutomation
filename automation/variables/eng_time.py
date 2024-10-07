from ..utils.units import *

class Time(EngUnit):
    """Creates a eng_time object that can store a eng_time value and 
    convert between units of eng_time.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Time Object]

    >>> from automation.variables.eng_time import Time
    >>> eng_time = Time(value=1.0, unit="hr")
    >>> eng_time.value
    1.0
    >>> eng_time.unit
    'hr'
    >>> eng_time.convert(to_unit="minute")
    60.0
    >>> Time.convert_value(value=1.0, from_unit="hr", to_unit="s")
    3600.0
    >>> Time.convert_values(values=[1.0, 10.0], from_unit="hr", to_unit="s")
    [3600.0, 36000.0]
    >>> eng_time.change_unit(unit="minute")
    60.0
    >>> eng_time.unit
    'minute'
    >>> eng_time.get_value()
    [60.0, 'minute']
    >>> print(eng_time)
    60.0 minute
    >>> eng_time2 = Time(value=3.0, unit="s")
    >>> eng_time_result = eng_time + eng_time2
    >>> print(eng_time_result)
    60.05 minute
    >>> eng_time_result = eng_time * eng_time2
    >>> print(eng_time_result)
    3.0 minute
    >>> eng_time_result = eng_time / eng_time2
    >>> print(eng_time_result)
    1200.0 minute

    """
    
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