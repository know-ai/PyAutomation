from ..utils.units import *

class Force(EngUnit):
    """Creates a force object that can store a force value and 
    convert between units of force.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Force Object]

    ```python
    >>> from automation.variables.force import Force
    >>> force = Force(value=1.0, unit="N")
    >>> force.value
    1.0
    >>> force.unit
    'N'
    >>> force.convert(to_unit="kgf")
    0.1019716213
    >>> Force.convert_value(value=1.0, from_unit="N", to_unit="lbf")
    0.2248089431
    >>> Force.convert_values(values=[1.0, 10.0], from_unit="N", to_unit="lbf")
    [0.2248089431, 2.248089431]
    >>> force.change_unit(unit="kgf")
    0.1019716213
    >>> force.unit
    'kgf'
    >>> force.get_value()
    [0.1019716213, 'kgf']
    >>> print(force)
    0.1019716213 kgf
    >>> force2 = Force(value=3.0, unit="lbf")
    >>> force_result = force + force2
    >>> print(force_result)
    1.4627487313277014 kgf
    >>> force_result = force * force2
    >>> print(force_result)
    0.1387606481374532 kgf
    >>> force_result = force / force2
    >>> print(force_result)
    0.07493631436666666 kgf
    >>> force_result = force ** force2
    >>> print(force_result)
    0.04474673588461198 kgf

    ```
    """

    class Units(UnitSerializer):
        N = 'N'
        kN = 'kN'
        MN = 'MN'
        GN = 'GN'
        gf = 'gf'
        kgf = 'kgf'
        dyn = 'dyn'
        Jm = 'J/m'
        Jcm = 'J/cm'
        shortTonF = 'shortTonF'
        longTonF = 'longTonF'
        kipf = 'kipf'
        lbf = 'lbf'
        ozf = 'ozf'
        pdl = 'pdl'

    conversions = {
        'N' : 1.0,
        'kN' : 1.0 / 1000.0,
        'MN' : 1.0 / 1000000.0,
        'GN' : 1.0 / 1000000000.0,
        'gf' : 1.019716213e+2,
        'kgf' : 1.019716213e-1,
        'dyn' : 1e+5,
        'J/m' : 1.0,
        'J/cm' : 100.0,
        'shortTonF' : 1.124045e-4,
        'longTonF' : 1.003611e-4,
        'kipf' : 2.248089e-4,
        'lbf' : 2.248089431e-1,
        'ozf' : 3.5969430896,
        'pdf' : 7.2330138512
    }

    def __init__(self, value, unit):

        if unit not in Force.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Force.Units.list()}")
        
        super(Force, self).__init__(value=value, unit=unit)