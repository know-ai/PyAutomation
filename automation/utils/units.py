from enum import Enum

class UnitError(Exception):
    pass

class UnitSerializer(Enum):

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))
    
    @classmethod
    def serialize(cls):

        return {unit.name: unit.value for unit in cls}

class EngUnit(object):
    """Generic class for engineering unit objects containing a float value and string unit."""
    
    numerator = []
    denominator = []
    conversions = dict()
    
    def __init__(self, value, unit):
        super().__init__()
        self.value = value
        self.unit = unit
        self.baseUnit = dict(zip(self.conversions.values(), self.conversions.keys()))[1]

    def convert(self, to_unit):
        """Converts the object from one unit to another."""
        from_unit = self.unit
        to_unit = to_unit
        return float(self.value) / float(self.conversions[from_unit]) * float(self.conversions[to_unit])
    
    def convert_values(self, values:list, from_unit:str, to_unit:str)->list:
        r"""
        Documentation here
        """
        return [float(value) / float(self.conversions[from_unit]) * float(self.conversions[to_unit]) for value in values]
    
    @classmethod
    def convert_value(cls, value:int|float, from_unit:str, to_unit:str)->float:
        """Unit value conversion

        :param value: [int|float] Value to convert
        :param from_unit: [str] Value's unit
        :param to_unit: [str] Unit which you want to convert the value
        :return: [float] Converted value into "to_unit"

        ```python
        >>> from automation.variables.pressure import Pressure
        >>> Pressure.convert_value(value=2, from_unit="atm", to_unit="Pa")
        202650.05476617732
        
        ```
        """
        return float(value) / float(cls.conversions[from_unit]) * float(cls.conversions[to_unit])
        
    def change_unit(self, unit):
        """Converts the current value of the object to a new unit.  Returns a float of the new value."""
        self.value = self.convert(unit)
        self.unit = unit
        return float(self.value)

    def set_value(self, value, unit):
        """Sets the value and unit of the object"""
        self.value = value
        self.unit = unit

    def get_value(self):
        """Returns a list of the float value and unit of the object."""
        return [float(self.value), self.unit]

    def __str__(self):
        return str(self.value) + ' ' + self.unit

    def __add__(self, other):
        new_value = self.value + other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)

    def __sub__(self, other):
        new_value = self.value - other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)

    def __mul__(self, other):
        new_value = self.value * other
        return self.__class__(new_value, self.unit)

    def __rmul__(self, other):
        new_value = self.value * other
        return self.__class__(new_value, self.unit)

    def __truediv__(self, other):
        new_value = self.value / other
        return self.__class__(new_value, self.unit)

    def __floordiv__(self, other):
        new_value = self.value // other
        return self.__class__(new_value, self.unit)

    def __pow__(self, other):
        new_value = self.value ** other
        return self.__class__(new_value, self.unit)
    

# if __name__ == "__main__":
#     import doctest
#     doctest.testmod()