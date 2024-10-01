from ..utils.units import *

class Force(EngUnit):
    """Creates a force object that can store a force value and 
    convert between units of force."""

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