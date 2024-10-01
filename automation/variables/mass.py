from ..utils.units import *

class Mass(EngUnit):
    """Creates a mass object that can store a mass value and 
    convert between units of mass."""
    
    class Units(UnitSerializer):
        kg = 'kg'
        g = 'g'
        mg = 'mg'
        metricTon = 'metricTon'
        lb = 'lb'
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