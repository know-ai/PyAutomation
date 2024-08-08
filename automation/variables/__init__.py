from .temperature import Temperature
from .length import Length


temperature_base = Temperature(value=1, unit='K')
length_base = Length(value=1, unit="m")

VARIABLES = {
    f"{temperature_base.__class__.__name__}": temperature_base.Units.serialize(),
    f"{length_base.__class__.__name__}": length_base.Units.serialize()
}