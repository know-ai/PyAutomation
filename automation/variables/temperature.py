from automation.utils.units import EngUnit, UnitSerializer, UnitError

class Temperature(EngUnit):
    """Creates a temperature object that can store a temperature value and
    convert between units of temperature."""
    
    class Units(UnitSerializer):
        degKelvin = 'K'
        degCelsius = 'C'
        degRankine = 'R'
        degFarenheit = 'F'

    # conversions { } is not used to convert the Temperature() class because 
    # temperature is not converted with a scalar.  See the convert() function below.
    conversions = {
        'K' : 1.0,
    }

    def __init__(self, value, unit):

        if unit not in Temperature.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Temperature.Units.list()}")
        
        super(Temperature, self).__init__(value=value, unit=unit)

    def convert(self, to_unit):
        """
        Converts a temperature value from one unit of measure to another.
        Returns a float value of the temperature in requested units. 
        Returns None for incorrect value.

        Units of Measure
        ---------------
        Units of measure entered as a string.
        'K' - Degree Kelvin\n
        'F' - Degree Farenheit\n
        'R' - Degree Rankine\n
        'C' - Degree Celcius

        Parameters
        ---------------
        value : float
            Value of the temperature measurement.\n
        from_unit : str
            Unit of measurement to convert from.\n
        to_unit : str
            Unit of measurement to convert to.
        """
    
        temperature_kelvin = 0
        if self.unit.upper() == 'K':
            temperature_kelvin = self.value
        elif self.unit == 'R':
            temperature_kelvin = self.value * 5.0 / 9.0
        elif self.unit == 'C':
            temperature_kelvin = self.value + 273.15
        elif self.unit == 'F':
            temperature_kelvin = (self.value + 459.67) / 9.0 * 5.0
        else:
            return None
        
        # Return Value in Required Unit
        if to_unit == 'K':
            return float(temperature_kelvin)
        elif to_unit == 'R':
            return temperature_kelvin * 9.0 / 5.0
        elif to_unit == 'C':
            return temperature_kelvin - 273.15
        elif to_unit == 'F':
            return temperature_kelvin * 9.0 / 5.0 - 459.67
        else:
            return None    

    def __add__(self, other):
        self_original_unit = self.unit

        self.changeUnit('K')

        if other.unit in ('K', 'C'):
            new_value = self.value + other.value
        else:
            new_value = self.value + (other.value * 5.0 / 9.0)            

        new_unit = self.__class__(new_value, 'K')
        new_unit.changeUnit(self_original_unit)
        return new_unit

    def __sub__(self, other):
            self_original_unit = self.unit

            self.changeUnit('K')

            if other.unit in ('K', 'C'):
                new_value = self.value - other.value
            else:
                new_value = self.value - (other.value * 5.0 / 9.0)            

            new_unit = self.__class__(new_value, 'K')
            new_unit.changeUnit(self_original_unit)
            return new_unit