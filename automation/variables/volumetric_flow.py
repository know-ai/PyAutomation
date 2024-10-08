from ..utils.units import *

class VolumetricFlow(EngUnit):
    """Creates a flow object that can store a flow value and 
    convert between units of flow.

    :param value: [int|float] Engineering value\n
    :param unit: [str] Engineering unit\n
    :return: [VolumetricFlow Object]\n

    ```python
    >>> from automation.variables.volumetric_flow import VolumetricFlow
    >>> volumetric_flow = VolumetricFlow(value=1.0, unit="bbl/sec")
    >>> volumetric_flow.value
    1.0
    >>> volumetric_flow.unit
    'bbl/sec'
    >>> volumetric_flow.convert(to_unit="m3/day")
    13736.5022817792
    >>> VolumetricFlow.convert_value(value=1.0, from_unit="gal/sec", to_unit="bbl/sec")
    0.023809523809523808
    >>> VolumetricFlow.convert_values(values=[1.0, 10.0], from_unit="gal/sec", to_unit="bbl/sec")
    [0.023809523809523808, 0.23809523809523808]
    >>> volumetric_flow.change_unit(unit="gal/sec")
    42.0
    >>> volumetric_flow.unit
    'gal/sec'
    >>> volumetric_flow.get_value()
    [42.0, 'gal/sec']
    >>> print(volumetric_flow)
    42.0 gal/sec
    >>> volumetric_flow2 = VolumetricFlow(value=120.0, unit="gal/min")
    >>> volumetric_flow_result = volumetric_flow + volumetric_flow2
    >>> print(volumetric_flow_result)
    44.0 gal/sec
    >>> volumetric_flow_result = volumetric_flow * volumetric_flow2
    >>> print(volumetric_flow_result)
    84.0 gal/sec
    >>> volumetric_flow_result = volumetric_flow / volumetric_flow2
    >>> print(volumetric_flow_result)
    21.0 gal/sec
    >>> volumetric_flow_result = volumetric_flow ** volumetric_flow2
    >>> print(volumetric_flow_result)
    1764.0 gal/sec

    ```
    """

    class Units(UnitSerializer):
        bbl_day = 'bbl/day'
        bbl_hr = 'bbl/hr'
        bbl_min = 'bbl/min'
        bbl_sec = 'bbl/sec'
        gal_day = 'gal/day'
        gal_hr = 'gal/hr'
        gal_min = 'gal/min'
        gal_sec = 'gal/sec'
        cubic_meter_day = 'm3/day'
        cubic_meter_hr = 'm3/hr'
        cubic_meter_min = 'm3/min'
        cubic_meter_sec = 'm3/sec'
        liter_day = 'lt/day'
        liter_hr = 'lt/hr'
        liter_min = 'lt/min'
        liter_sec = 'lt/sec'
        cubic_centimeter_day = 'cc/day'
        cubic_centimeter_hr = 'cc/hr'
        cubic_centimeter_min = 'cc/min'
        cubic_centimeter_sec = 'cc/sec'

    conversions = {
        'bbl/day' : 1.0 * 60.0 * 60.0 * 24.0,
        'bbl/hr' : 1.0 * 60 * 60,
        'bbl/min' : 1.0 * 60.0,
        'bbl/sec' : 1.0,
        'gal/day' : 42.0 * 60.0 * 60.0 * 24.0,
        'gal/hr' : 42.0 * 60.0 * 60.0,
        'gal/min' : 42.0 * 60.0,
        'gal/sec' : 42.0,
        'm3/day' : 0.158987294928 * 60 * 60 * 24,
        'm3/hr' : 0.158987294928 * 60 * 60,
        'm3/min' : 0.158987294928 * 60,
        'm3/sec' : 0.158987294928,
        'lt/day' : 158.987294928 * 60 * 60 * 24,
        'lt/hr' : 158.987294928 * 60 * 60,
        'lt/min' : 158.987294928 * 60,
        'lt/sec' : 158.987294928,
        'ml/day' : 158987.294928 * 60 * 60 * 24,
        'ml/hr' : 158987.294928 * 60 * 60,
        'ml/min' : 158987.294928 * 60,
        'ml/sec' : 158987.294928
    }

    def __init__(self, value, unit):

        if unit not in VolumetricFlow.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {VolumetricFlow.Units.list()}")
        
        super(VolumetricFlow, self).__init__(value=value, unit=unit)