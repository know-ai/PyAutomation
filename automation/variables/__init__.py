from .temperature import Temperature
from .length import Length
from .current import Current
from .eng_time import Time
from .pressure import Pressure
from .mass import Mass
from .force import Force
from .power import Power
from .volumetric_flow import VolumetricFlow
from .mass_flow import MassFlow
from .density import Density
from .percentage import Percentage
from .adimentional import Adimentional
from .volume import Volume
from ..utils.unit_symbols import UNIT_ALIASES, canonical_symbol


temperature_base = Temperature(value=1, unit='K')
length_base = Length(value=1, unit="m")
current_base = Current(value=1, unit="A")
time_base = Time(value=1, unit="s")
pressure_base = Pressure(value=1, unit="bar")
mass_base = Mass(value=1, unit="kg")
force_base = Force(value=1, unit="J/m")
power_base = Power(value=1, unit="kW")
volumetric_flow_base = VolumetricFlow(value=1, unit="bbl/sec")
mass_flow_base = MassFlow(value=1.0, unit="kg/day")
density_base = Density(value=1.0, unit="kg/bbl")
percentage_base = Percentage(value=0.0, unit="%")
adimentional_base = Adimentional(value=0.0, unit="adim")
volume_base = Volume(value=0.0, unit="m3")


VARIABLES = {
    f"{temperature_base.__class__.__name__}": temperature_base.Units.serialize(),
    f"{length_base.__class__.__name__}": length_base.Units.serialize(),
    f"{current_base.__class__.__name__}": current_base.Units.serialize(),
    f"{time_base.__class__.__name__}": time_base.Units.serialize(),
    f"{pressure_base.__class__.__name__}": pressure_base.Units.serialize(),
    f"{mass_base.__class__.__name__}": mass_base.Units.serialize(),
    f"{force_base.__class__.__name__}": force_base.Units.serialize(),
    f"{power_base.__class__.__name__}": power_base.Units.serialize(),
    f"{volumetric_flow_base.__class__.__name__}": volumetric_flow_base.Units.serialize(),
    f"{mass_flow_base.__class__.__name__}": mass_flow_base.Units.serialize(),
    f"{density_base.__class__.__name__}": density_base.Units.serialize(),
    f"{percentage_base.__class__.__name__}": percentage_base.Units.serialize(),
    f"{adimentional_base.__class__.__name__}": adimentional_base.Units.serialize(),
    f"{volume_base.__class__.__name__}": volume_base.Units.serialize()
}

DATATYPES = [
    {'label': 'Float', 'value': 'float'},
    {'label': 'Integer', 'value': 'integer'},
    {'label': 'Boolean', 'value': 'boolean'},
    {'label': 'String', 'value': 'string'}
]


def resolve_units_for_variable(
    variable: str,
    *,
    requested_unit=None,
    requested_display_unit=None,
    current_unit=None,
    current_display_unit=None,
):
    """
    Pick engineering / display units when a tag's variable changes.

    Prefer explicit request values when valid for ``variable``; otherwise keep
    current values if still valid; otherwise fall back to the catalogue default
    (first unit for that variable).

    Returns ``(unit, display_unit)`` or raises ``KeyError`` if variable unknown.
    """
    units_dict = VARIABLES[variable]
    allowed = set(units_dict.values())
    default_unit = next(iter(units_dict.values()))
    from ..utils.unit_symbols import canonical_symbol

    requested_unit = canonical_symbol(requested_unit) or requested_unit
    requested_display_unit = canonical_symbol(requested_display_unit) or requested_display_unit
    current_unit = canonical_symbol(current_unit) or current_unit
    current_display_unit = canonical_symbol(current_display_unit) or current_display_unit

    def _pick(requested, current):
        if requested is not None and requested in allowed:
            return requested
        if (requested is None or requested == "") and current in allowed:
            return current
        return default_unit

    unit = _pick(requested_unit, current_unit)
    display = _pick(
        requested_display_unit,
        current_display_unit if current_display_unit is not None else current_unit,
    )
    return unit, display


FLOW_VARIABLES = frozenset({"MassFlow", "VolumetricFlow"})


def variable_for_unit(unit: str | None) -> str | None:
    """Catalogue variable name whose units include ``unit``, or ``None``."""
    if not unit:
        return None
    needle = str(unit).strip()
    if not needle:
        return None
    from ..utils.unit_symbols import canonical_symbol

    canon = canonical_symbol(needle) or needle
    for variable, units in VARIABLES.items():
        values = set(units.values()) | set(units.keys())
        if needle in values or canon in values:
            return variable
    return None


def unit_belongs_to_variable(unit: str | None, variable: str | None) -> bool:
    """True when ``unit`` is a catalogue symbol of ``variable``."""
    if not unit or not variable:
        return False
    units = VARIABLES.get(str(variable).strip())
    if not units:
        return False
    from ..utils.unit_symbols import canonical_symbol

    needle = canonical_symbol(str(unit).strip()) or str(unit).strip()
    allowed = set(units.values())
    return needle in allowed


def compatible_field_variables(variable: str | None) -> frozenset[str]:
    """Field-tag variable names that may bind to an internal ProcessType.

    MassFlow and VolumetricFlow are interchangeable: engines convert volumetric
    flow with density into mass flow.
    """
    name = str(variable or "").strip()
    if not name:
        return frozenset()
    if name in FLOW_VARIABLES:
        return FLOW_VARIABLES
    return frozenset({name})
