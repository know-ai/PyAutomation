from ..utils.units import *

class MassFlow(EngUnit):
    """Creates a mass flow object that can store a mass flow value and 
    convert between units of mass flow.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [MassFlow Object]

    ```python
    >>> from automation.variables.mass_flow import MassFlow
    >>> mass_flow = MassFlow(value=1.0, unit="kg/hr")
    >>> mass_flow.value
    1.0
    >>> mass_flow.unit
    'kg/hr'
    >>> mass_flow.convert(to_unit="lb/sec")
    0.0006123951727222222
    >>> MassFlow.convert_value(value=1.0, from_unit="kg/hr", to_unit="lb/sec")
    0.0006123951727222222
    >>> MassFlow.convert_values(values=[1.0, 10.0], from_unit="kg/hr", to_unit="lb/sec")
    [0.0006123951727222222, 0.0061239517272222216]
    >>> mass_flow.change_unit(unit="lb/sec")
    0.0006123951727222222
    >>> mass_flow.unit
    'lb/sec'
    >>> mass_flow.get_value()
    [0.0006123951727222222, 'lb/sec']
    >>> print(mass_flow)
    0.0006123951727222222 lb/sec
    >>> mass_flow2 = MassFlow(value=3.0, unit="lb/sec")
    >>> mass_flow_result = mass_flow + mass_flow2
    >>> print(mass_flow_result)
    3.0006123951727224 lb/sec
    >>> mass_flow_result = mass_flow * mass_flow2
    >>> print(mass_flow_result)
    0.0018371855181666666 lb/sec
    >>> mass_flow_result = mass_flow / mass_flow2
    >>> print(mass_flow_result)
    0.00020413172424074073 lb/sec
    >>> mass_flow_result = mass_flow ** mass_flow2
    >>> print(mass_flow_result)
    2.2966524349040475e-10 lb/sec

    ```
    """
    
    class Units(UnitSerializer):
        kg_day = 'kg/day'
        kg_hr = 'kg/hr'
        kg_min = 'kg/min'
        kg_sec = 'kg/sec'
        g_day = 'g/day'
        g_hr = 'g/hr'
        g_min = 'g/min'
        g_sec = 'g/sec'
        mg_day = 'mg/day'
        mg_hr = 'mg/hr'
        mg_min = 'mg/min'
        mg_sec = 'mg/sec'
        lb_day = 'lb/day'
        lb_hr = 'lb/hr'
        lb_min = 'lb/min'
        lb_sec = 'lb/sec'
        metricTon_day = 'metricTon/day'
        metricTon_hr = 'metricTon/hr'
        metricTon_min = 'metricTon/min'
        metricTon_sec = 'metricTon/sec'
    
    conversions = {
        'kg/day' : 1.0,
        'kg/hr' : 1.0 / 24,
        'kg/min' : 1.0 / 24 / 60,
        'kg/sec' : 1.0 / 24 / 60 / 60,
        'g/day' : 1000.0,
        'g/hr' : 1000.0 / 24,
        'g/min' : 1000.0 / 24 / 60,
        'g/sec' : 1000.0 / 24 / 60 / 60,
        'mg/day' : 1000000.0,
        'mg/hr' : 1000000.0 / 24,
        'mg/min' : 1000000.0 / 24 / 60,
        'mg/min' : 1000000.0 / 24 / 60 / 60,
        'metricTon/day' : 1.0 / 1000.0,
        'metricTon/hr' : 1.0 / 1000.0 / 24,
        'metricTon/min' : 1.0 / 1000.0 / 24 / 60,
        'metricTon/sec' : 1.0 / 1000.0 / 24 / 60 / 60,
        'lb/day' : 2.2046226218,
        'lb/hr' : 2.2046226218 / 24,
        'lb/min' : 2.2046226218 / 24 / 60,
        'lb/sec' : 2.2046226218 / 24 / 60 / 60
    }

    def __init__(self, value, unit):

        if unit not in MassFlow.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {MassFlow.Units.list()}")
        
        super(MassFlow, self).__init__(value=value, unit=unit)