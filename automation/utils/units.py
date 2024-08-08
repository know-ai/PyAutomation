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
        
    def changeUnit(self, unit):
        """Converts the current value of the object to a new unit.  Returns a float of the new value."""
        self.value = self.convert(unit)
        self.unit = unit
        return float(self.value)

    def setValue(self, value, unit):
        """Sets the value and unit of the object"""
        self.value = value
        self.unit = unit

    def getValue(self):
        """Returns a list of the float value and unit of the object."""
        return [float(self.value), self.unit]

    def __str__(self):
        return str(self.value) + ' ' + self.unit

    def __add__(self, other):
        new_value = self.value + other.changeUnit(self.unit)
        return self.__class__(new_value, self.unit)

    def __sub__(self, other):
        new_value = self.value - other.changeUnit(self.unit)
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