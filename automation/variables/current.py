from ..utils.units import EngUnit, UnitError, UnitSerializer

class Current(EngUnit):
    r"""
    Creates a current object that can store a current value and 
    convert between units of current.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Current Object]

    >>> from automation.variables.current import Current
    >>> current = Current(value=1.0, unit="A")
    >>> current.value
    1.0
    >>> current.unit
    'A'
    >>> current.convert(to_unit="kA")
    0.001
    >>> Current.convert_value(value=1.0, from_unit="A", to_unit="mA")
    1000.0
    >>> Current.convert_values(values=[1.0, 10.0], from_unit="A", to_unit="mA")
    [1000.0, 10000.0]
    >>> current.change_unit(unit="kA")
    0.001
    >>> current.unit
    'kA'
    >>> current.get_value()
    [0.001, 'kA']
    >>> print(current)
    0.001 kA
    >>> current2 = Current(value=3.0, unit="mA")
    >>> current_result = current + current2
    >>> print(current_result)
    0.001003 kA
    >>> current_result = current * current2
    >>> print(current_result)
    3e-09 kA
    >>> current_result = current / current2
    >>> print(current_result)
    333.3333333333333 kA
    >>> current_result = current ** current2
    >>> print(current_result)
    0.9999792769488884 kA

    """
    
    class Units(UnitSerializer):
        A = 'A'
        mA = 'mA'
        kA = 'kA'
    
    conversions = {
        'A' : 1,
        'mA' : 1000,
        'kA' : 0.001
    }

    def __init__(self, value, unit):

        if unit not in Current.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Current.Units.list()}")
        
        super(Current, self).__init__(value=value, unit=unit)