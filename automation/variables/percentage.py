from ..utils.units import EngUnit, UnitSerializer, UnitError

class Percentage(EngUnit):
    """Creates a percentage object that can store a percentage value and 
    convert between units of percentage.

    :param value: [int|float] Engineering value\n
    :param unit: [str] Engineering unit\n
    :return: [Length Object]\n

    
    ```
    """
    
    class Units(UnitSerializer):
        percentage = '%' 


    conversions = {

        '%' : 1.0
    }

    def __init__(self, value, unit):

        if unit not in Percentage.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Percentage.Units.list()}")
        
        super(Percentage, self).__init__(value=value, unit=unit)