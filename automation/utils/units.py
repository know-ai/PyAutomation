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
        from .unit_symbols import canonical_symbol

        self.value = value
        self.unit = canonical_symbol(unit) or unit
        self.baseUnit = dict(zip(self.conversions.values(), self.conversions.keys()))[1]

    def _resolved_pair(self, to_unit):
        from .unit_symbols import canonical_symbol

        from_unit = canonical_symbol(self.unit) or self.unit
        to_unit = canonical_symbol(to_unit) or to_unit
        return from_unit, to_unit

    @classmethod
    def _require_symbols(cls, from_unit, to_unit):
        if from_unit not in cls.conversions:
            raise UnitError(
                f"{from_unit!r} is not a valid unit for {cls.__name__}; "
                f"allowed: {sorted(cls.conversions)}"
            )
        if to_unit not in cls.conversions:
            raise UnitError(
                f"{to_unit!r} is not a valid unit for {cls.__name__}; "
                f"allowed: {sorted(cls.conversions)}"
            )

    def convert(self, to_unit):
        """Converts the object from one unit to another."""
        from_unit, to_unit = self._resolved_pair(to_unit)
        if from_unit == to_unit:
            return float(self.value)
        self._require_symbols(from_unit, to_unit)
        return float(self.value) / float(self.conversions[from_unit]) * float(self.conversions[to_unit])
    
    @classmethod
    def convert_values(self, values:list, from_unit:str, to_unit:str)->list:
        r"""
        Documentation here
        """
        from .unit_symbols import canonical_symbol

        from_unit = canonical_symbol(from_unit) or from_unit
        to_unit = canonical_symbol(to_unit) or to_unit
        if from_unit == to_unit:
            return [float(value) for value in values]
        self._require_symbols(from_unit, to_unit)
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
        from .unit_symbols import canonical_symbol

        from_unit = canonical_symbol(from_unit) or from_unit
        to_unit = canonical_symbol(to_unit) or to_unit
        if from_unit == to_unit:
            return float(value)
        cls._require_symbols(from_unit, to_unit)
        return float(value) / float(cls.conversions[from_unit]) * float(cls.conversions[to_unit])
       
    def change_unit(self, unit):
        """Converts the current value of the object to a new unit.  Returns a float of the new value."""
        from .unit_symbols import canonical_symbol

        unit = canonical_symbol(unit) or unit
        self.value = self.convert(unit)
        self.unit = unit
        return float(self.value)

    def set_value(self, value, unit):
        """Sets the value and unit of the object"""
        from .unit_symbols import canonical_symbol

        self.value = value
        self.unit = canonical_symbol(unit) or unit

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
        new_value = self.value * other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)

    def __rmul__(self, other):
        new_value = self.value * other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)

    def __truediv__(self, other):
        new_value = self.value / other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)

    def __floordiv__(self, other):
        new_value = self.value // other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)

    def __pow__(self, other):
        new_value = self.value ** other.change_unit(self.unit)
        return self.__class__(new_value, self.unit)
    
    def __lt__(self, other):
        return self.value < other.change_unit(self.unit)

    def __le__(self, other):
        return self.value <= other.change_unit(self.unit)

    def __gt__(self, other):
        return self.value > other.change_unit(self.unit)

    def __ge__(self, other):
        return self.value >= other.change_unit(self.unit)
    