from automation.utils.units import EngUnit, UnitError, UnitSerializer

class Current(EngUnit):
    """Creates a current (amperage) object that can store a current (amperage) value and 
    convert between units of current (amperage)."""
    
    class Units(UnitSerializer):
        A = 'A'
        mA = 'mA'
        kA = 'kA'
    
    conversions = {
        'A' : 1,
        'mA' : 1000,
        'kA' : 0.001
    }

    def __init__(self, value, unit):

        if unit not in Current.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Current.Units.list()}")
        
        super(Current, self).__init__(value=value, unit=unit)