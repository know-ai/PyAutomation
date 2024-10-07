from ..utils.units import *

class Density(EngUnit):
    """Creates a density object that can store a density value and 
    convert between units of density.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Density Object]

    ```python
    >>> from automation.variables.density import Density
    >>> density = Density(value=1.0, unit="kg/m3")
    >>> density.value
    1.0
    >>> density.unit
    'kg/m3'
    >>> density.convert(to_unit="lb/ml")
    2.2046226218000004e-06
    >>> Density.convert_value(value=1.0, from_unit="kg/m3", to_unit="g/ml")
    0.0010000000000000002
    >>> Density.convert_values(values=[1.0, 10.0], from_unit="kg/m3", to_unit="g/ml")
    [0.0010000000000000002, 0.010000000000000002]
    >>> density.change_unit(unit="lb/ml")
    2.2046226218000004e-06
    >>> density.unit
    'lb/ml'
    >>> density.get_value()
    [2.2046226218000004e-06, 'lb/ml']
    >>> print(density)
    2.2046226218000004e-06 lb/ml
    >>> density2 = Density(value=3.0, unit="g/ml")
    >>> density_result = density + density2
    >>> print(density_result)
    0.0066160724880218 lb/ml
    >>> density_result = density * density2
    >>> print(density_result)
    1.458108271365692e-08 lb/ml
    >>> density_result = density / density2
    >>> print(density_result)
    0.00033333333333333343 lb/ml
    >>> density_result = density ** density2
    >>> print(density_result)
    0.9174608905185654 lb/ml

    ```

    """
    
    class Units(UnitSerializer):
        kg_bbl = 'kg/bbl'
        kg_gal = 'kg/gal'
        kg_m3 = 'kg/m3'
        kg_lt = 'kg/lt'
        kg_ml = 'kg/ml'
        g_bbl = 'g/bbl'
        g_gal = 'g/gal'
        g_m3 = 'g/m3'
        g_lt = 'g/lt'
        g_ml = 'g/ml'
        mg_bbl = 'mg/bbl'
        mg_gal = 'mg/gal'
        mg_m3 = 'kmg/m3'
        mg_lt = 'mg/lt'
        mg_ml = 'mg/ml'
        lb_bbl = 'lb/bbl'
        lb_gal = 'lb/gal'
        lb_m3 = 'lb/m3'
        lb_lt = 'lb/lt'
        lb_ml = 'lb/ml'
        metricTon_bbl = 'metricTon/bbl'
        metricTon_gal = 'metricTon/gal'
        metricTon_m3 = 'metricTon/m3'
        metricTon_lt = 'metricTon/lt'
        metricTon_ml = 'metricTon/ml'
    
    conversions = {
        'kg/bbl' : 1.0,
        'g/bbl' : 1.0 * 1000,
        'mg/bbl' : 1.0 * 1000 * 1000,
        'metricTon/bbl' : 1.0 / 1000.0,
        'lb/bbl' : 2.2046226218,

        'kg/gal' : 1.0 / 42.0,
        'g/gal' : 1.0 * 1000 / 42.0,
        'mg/gal' : 1.0 * 1000 * 1000 / 42.0,
        'metricTon/gal' : 1.0 / 1000.0 / 42.0,
        'lb/gal' : 2.2046226218 / 42.0,

        'kg/m3' : 1.0 / 0.158987294928,
        'g/m3' : 1.0 * 1000 / 0.158987294928,
        'mg/m3' : 1.0 * 1000 * 1000 / 0.158987294928,
        'metricTon/m3' : 1.0 / 1000.0 / 0.158987294928,
        'lb/m3' : 2.2046226218 / 0.158987294928,

        'kg/lt' : 1.0 / 158.987294928,
        'g/lt' : 1.0 * 1000 / 158.987294928,
        'mg/lt' : 1.0 * 1000 * 1000 / 158.987294928,
        'metricTon/lt' : 1.0 / 1000.0 / 158.987294928,
        'lb/lt' : 2.2046226218 / 158.987294928,

        'kg/ml' : 1.0 / 158987.294928,
        'g/ml' : 1.0 * 1000 / 158987.294928,
        'mg/ml' : 1.0 * 1000 * 1000 / 158987.294928,
        'metricTon/ml' : 1.0 / 1000.0 / 158987.294928,
        'lb/ml' : 2.2046226218 / 158987.294928,
    }

    def __init__(self, value, unit):

        if unit not in Density.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Density.Units.list()}")
        
        super(Density, self).__init__(value=value, unit=unit)