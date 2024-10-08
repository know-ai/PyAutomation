from ..utils.units import EngUnit, UnitSerializer, UnitError

class Adimentional(EngUnit):
    """Creates an adimentional object that can store an adimentional value and 
    convert between units of adimentional.

    :param value: [int|float] Engineering value\n
    :param unit: [str] Engineering unit\n
    :return: [Length Object]\n

    
    ```
    """
    
    class Units(UnitSerializer):
        adim = 'adim' 


    conversions = {

        'adim' : 1.0
    }

    def __init__(self, value, unit):

        if unit not in Adimentional.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Adimentional.Units.list()}")
        
        super(Adimentional, self).__init__(value=value, unit=unit)