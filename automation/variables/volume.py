from ..utils.units import *

class Volume(EngUnit):
    """Creates a flow object that can store a flow value and 
    convert between units of flow.

    :param value: [int|float] Engineering value\n
    :param unit: [str] Engineering unit\n
    :return: [Volume Object]\n

    ```python
    >>> from automation.variables.volume import Volume
    >>> volume = Volume(value=1.0, unit="bbl")
    >>> volume.value
    1.0
    >>> volume.unit
    'bbl'
    >>> volume.convert(to_unit="m3")
    0.158987294928
    >>> Volume.convert_value(value=1.0, from_unit="gal", to_unit="bbl")
    0.023809523809523808
    >>> Volume.convert_values(values=[1.0, 10.0], from_unit="gal", to_unit="bbl")
    [0.023809523809523808, 0.23809523809523808]
    >>> volume.change_unit(unit="gal")
    42.0
    >>> volume.unit
    'gal'
    >>> volume.get_value()
    [42.0, 'gal']
    >>> print(volume)
    42.0 gal
    >>> volume2 = Volume(value=120.0, unit="lt")
    >>> volume_result = volume + volume2
    >>> print(volume_result)
    73.7006462829778 gal
    >>> volume_result = volume * volume2
    >>> print(volume_result)
    1331.4271438850678 gal
    >>> volume_result = volume / volume2
    >>> print(volume_result)
    1.3248941244 gal
    >>> volume_result = volume ** volume2
    >>> print(volume_result)
    2.8711215836780378e+51 gal

    ```
    """

    class Units(UnitSerializer):
        bbl = 'bbl'
        gal = 'gal'
        cubic_meter = 'm3'
        liter_sec = 'lt'
        milliliter = 'ml'

    conversions = {
        'bbl' : 1.0,
        'gal' : 42.0,
        'm3' : 0.158987294928,
        'lt' : 158.987294928,
        'ml' : 158987.294928
    }

    def __init__(self, value, unit):

        if unit not in Volume.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Volume.Units.list()}")
        
        super(Volume, self).__init__(value=value, unit=unit)