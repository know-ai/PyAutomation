from ..utils.units import EngUnit, UnitSerializer, UnitError

class Length(EngUnit):
    """Creates a length object that can store a length value and 
    convert between units of length.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Length Object]

    ```python
    >>> from automation.variables.length import Length
    >>> length = Length(value=1.0, unit="m")
    >>> length.value
    1.0
    >>> length.unit
    'm'
    >>> length.convert(to_unit="inch")
    39.3701
    >>> Length.convert_value(value=1.0, from_unit="m", to_unit="cm")
    100.0
    >>> Length.convert_values(values=[1.0, 10.0], from_unit="m", to_unit="cm")
    [100.0, 1000.0]
    >>> length.change_unit(unit="inch")
    39.3701
    >>> length.unit
    'inch'
    >>> length.get_value()
    [39.3701, 'inch']
    >>> print(length)
    39.3701 inch
    >>> length2 = Length(value=3.0, unit="cm")
    >>> length_result = length + length2
    >>> print(length_result)
    40.551203 inch
    >>> length_result = length * length2
    >>> print(length_result)
    46.500143220300004 inch
    >>> length_result = length / length2
    >>> print(length_result)
    33.333333333333336 inch
    >>> length_result = length ** length2
    >>> print(length_result)
    76.56952620577046 inch

    ```
    """
    
    class Units(UnitSerializer):
        fm = 'fm' 
        pm = 'pm' 
        nm = 'nm' 
        um = 'um' 
        mm = 'mm' 
        cm = 'cm'
        m = 'm'
        dam = 'dam'
        hm = 'hm' 
        km = 'km'
        Mm = 'Mm' 
        Gm = 'Gm'
        Tm = 'Tm'
        Pm = 'Pm'

        inch = 'inch'
        ft = 'ft'
        yd = 'yd'
        mi = 'mi'

        nautMi = 'nautMi'
        lightYear = 'lightYear'

    conversions = {
        'fm' : 1000000000000000,
        'pm' : 1000000000000,
        'nm' : 1000000000,
        'um' : 1000000,
        'mm' : 1000,
        'cm' : 100,
        'm' : 1.0,
        'dam' : 0.1,
        'hm' : 0.01,
        'km' : 0.001,
        'Mm' : 0.000001,
        'Gm' : 0.000000001,
        'Tm' : 0.000000000001,
        'Pm' : 0.000000000000001,

        'inch' : 39.3701,
        'ft' : 3.28084,
        'yd' : 1.09361,
        'mi' : 0.000621371,

        'nautMi' : 1.0 / 1852.0,
        'lightYear' : 1.0 / (9.4607304725808 * (10**15))
    }

    def __init__(self, value, unit):

        if unit not in Length.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Length.Units.list()}")
        
        super(Length, self).__init__(value=value, unit=unit)