from ..utils.units import *

class Mass(EngUnit):
    """Creates a mass object that can store a mass value and 
    convert between units of mass.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Mass Object]

    ```python
    >>> from automation.variables.mass import Mass
    >>> mass = Mass(value=1.0, unit="kg")
    >>> mass.value
    1.0
    >>> mass.unit
    'kg'
    >>> mass.convert(to_unit="lb")
    2.2046226218
    >>> Mass.convert_value(value=1.0, from_unit="kg", to_unit="g")
    1000.0
    >>> Mass.convert_values(values=[1.0, 10.0], from_unit="kg", to_unit="g")
    [1000.0, 10000.0]
    >>> mass.change_unit(unit="lb")
    2.2046226218
    >>> mass.unit
    'lb'
    >>> mass.get_value()
    [2.2046226218, 'lb']
    >>> print(mass)
    2.2046226218 lb
    >>> mass2 = Mass(value=3.0, unit="g")
    >>> mass_result = mass + mass2
    >>> print(mass_result)
    2.2112364896654 lb
    >>> mass_result = mass * mass2
    >>> print(mass_result)
    0.014581082713656917 lb
    >>> mass_result = mass / mass2
    >>> print(mass_result)
    333.33333333333337 lb
    >>> mass_result = mass ** mass2
    >>> print(mass_result)
    1.0052423283919558 lb

    ```
    """
    
    class Units(UnitSerializer):
        kg = 'kg'
        g = 'g'
        mg = 'mg'
        lb = 'lb'
        metricTon = 'metricTon'
        oz = 'oz'
        grain = 'grain'
        shortTon = 'shortTon'
        longTon = 'longTon'
        slug = 'slug'
    
    conversions = {
        'kg' : 1.0,
        'g' : 1000.0,
        'mg' : 1000000.0,
        'metricTon' : 1.0 / 1000.0,
        'lb' : 2.2046226218,
        'oz' : 35.274,
        'grain' : 2.2046226218 * 7000.0,
        'shortTon' : 1.0 / 907.185,
        'longTon' : 1.0 / 1016.047,
        'slug' : 1.0 / 14.5939029
    }

    def __init__(self, value, unit):

        if unit not in Mass.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Mass.Units.list()}")
        
        super(Mass, self).__init__(value=value, unit=unit)