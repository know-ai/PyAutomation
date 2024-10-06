from ..utils.units import EngUnit, UnitSerializer, UnitError

class Temperature(EngUnit):
    """Creates a temperature object that can store a temperature value and 
    convert between units of temperature.

    :param value: [int|float] Engineering value
    :param unit: [str] Engineering unit
    :return: [Temperature Object]

    ```python
    >>> from automation.variables.temperature import Temperature
    >>> temperature = Temperature(value=25, unit="C")
    >>> temperature.value
    25
    >>> temperature.unit
    'C'
    >>> temperature.convert(to_unit="F")
    76.99999999999994
    >>> Temperature.convert_value(value=1.0, from_unit="C", to_unit="K")
    274.15
    >>> temperature.change_unit(unit="F")
    76.99999999999994
    >>> temperature.unit
    'F'
    >>> temperature.get_value()
    [76.99999999999994, 'F']
    >>> print(temperature)
    76.99999999999994 F
    >>> temperature2 = Temperature(value=3.0, unit="K")
    >>> temperature_result = temperature + temperature2
    >>> print(temperature_result)
    82.39999999999992 F
    >>> temperature_result = temperature * temperature2
    >>> print(temperature_result)
    894.4499999999999 K
    >>> temperature_result = temperature / temperature2
    >>> print(temperature_result)
    99.38333333333333 K
    >>> temperature_result = temperature ** temperature2
    >>> print(temperature_result)
    26503573.918374993 K

    ```
    """
    
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

    @classmethod
    def convert_value(cls, value, from_unit:str, to_unit:str):
        
        temperature_kelvin = 0
        if from_unit.upper() == 'K':
            temperature_kelvin = value
        elif from_unit.upper() == 'R':
            temperature_kelvin = value * 5.0 / 9.0
        elif from_unit.upper() == 'C':
            temperature_kelvin = value + 273.15
        elif from_unit.upper() == 'F':
            temperature_kelvin = (value + 459.67) / 9.0 * 5.0
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

        self.change_unit('K')

        if other.unit in ('K', 'C'):
            new_value = self.value + other.value
        else:
            new_value = self.value + (other.value * 5.0 / 9.0)            

        new_unit = self.__class__(new_value, 'K')
        new_unit.change_unit(self_original_unit)
        return new_unit

    def __sub__(self, other):
            self_original_unit = self.unit

            self.change_unit('K')

            if other.unit in ('K', 'C'):
                new_value = self.value - other.value
            else:
                new_value = self.value - (other.value * 5.0 / 9.0)            

            new_unit = self.__class__(new_value, 'K')
            new_unit.change_unit(self_original_unit)
            return new_unit