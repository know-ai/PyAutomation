from automation.utils.units import EngUnit, UnitSerializer, UnitError

class Length(EngUnit):
    """Creates a length object that can store a length value and 
    convert between units of length."""
    
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