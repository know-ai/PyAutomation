from automation.utils.units import *

class VolumetricFlow(EngUnit):
    """Creates a flow object that can store a flow value and 
    convert between units of flow."""

    class Units(UnitSerializer):
        BBL_hr = 'BBL/hr'
        BBL_min = 'BBL/min'
        BBL_sec = 'BBL/sec'
        GAL_hr = 'GAL/hr'
        GAL_min = 'GAL/min'
        GAL_sec = 'GAL/sec'

    conversions = {
        'BBL/hr' : 3600.0,
        'BBL/min' : 60.0,
        'BBL/sec' : 1.0,
        'GAL/hr' : 151200.0,
        'GAL/min' : 2520.0,
        'GAL/sec' : 42.0,
    }

    def __init__(self, value, unit):

        if unit not in VolumetricFlow.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {VolumetricFlow.Units.list()}")
        
        super(VolumetricFlow, self).__init__(value=value, unit=unit)