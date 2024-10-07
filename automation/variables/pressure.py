from ..utils.units import *

class Pressure(EngUnit):
    """Creates a pressure object that can store a pressure value and 
    convert between units of pressure.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Pressure Object]

    ```python
    >>> from automation.variables.pressure import Pressure
    >>> pressure = Pressure(value=1.0, unit="atm")
    >>> pressure.value
    1.0
    >>> pressure.unit
    'atm'
    >>> pressure.convert(to_unit="psi")
    14.695979321588414
    >>> Pressure.convert_value(value=1.0, from_unit="atm", to_unit="bar")
    1.0132502738308866
    >>> Pressure.convert_values(values=[1.0, 10.0], from_unit="atm", to_unit="bar")
    [1.0132502738308866, 10.132502738308865]
    >>> pressure.change_unit(unit="psi")
    14.695979321588414
    >>> pressure.unit
    'psi'
    >>> pressure.get_value()
    [14.695979321588414, 'psi']
    >>> print(pressure)
    14.695979321588414 psi
    >>> pressure2 = Pressure(value=3.0, unit="bar")
    >>> pressure_result = pressure + pressure2
    >>> print(pressure_result)
    58.20737932158842 psi
    >>> pressure_result = pressure * pressure2
    >>> print(pressure_result)
    639.4426346533621 psi
    >>> pressure_result = pressure / pressure2
    >>> print(pressure_result)
    0.3377500912769622 psi
    >>> pressure_result = pressure ** pressure2
    >>> print(pressure_result)
    6.115644251483115e+50 psi

    ```

    """
    
    class Units(UnitSerializer):
        bar = 'bar' 
        mbar = 'mbar' 
        ubar = 'ubar' 
        Pa = 'Pa' 
        hPa = 'hPa' 
        kPa = 'kPa' 
        MPa = 'MPa' 
        kgcm2 = 'kgcm2' 
        atm = 'atm' 
        mmHg = 'mmHg' 
        mmH2O = 'mmH2O' 
        mH2O = 'mH2O' 
        psi = 'psi' 
        ftH2O = 'ftH2O' 
        inH2O = 'inH2O' 
        inHg = 'inHg' 
    
    conversions = {
        'bar' : 1.0,
        'mbar' : 1000.0,
        'ubar' : 1000000.0,
        'Pa' : 100000.0,
        'hPa' : 1000.0,
        'kPa' : 100.0,
        'MPa' : 0.1,
        'kgcm2' : 1.01972,
        'atm' : 0.986923,
        'mmHg' : 750.062,
        'mmH2O' : 10197.162129779,
        'mH2O' : 10.197162129779,
        'psi' : 14.5038,
        'ftH2O' : 33.455256555148,
        'inH2O' : 401.865,
        'inHg' : 29.53
    }

    def __init__(self, value, unit):

        if unit not in Pressure.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Pressure.Units.list()}")
        
        super(Pressure, self).__init__(value=value, unit=unit)