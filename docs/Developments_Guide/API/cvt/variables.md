# Supported Variables and Units

PyAutomation provides a rich set of engineering variables with built-in unit conversion. When defining a Tag, you can specify its `variable` type and its `unit`. The system handles conversions automatically.

## Usage

When creating a tag, specify the variable type (Case Sensitive class name) and the unit symbol.

```python
app.create_tag(
    name="BoilerPressure",
    variable="Pressure",  # Must match the Variable class name
    unit="bar"            # Must be one of the supported units
)
```

## Available Variables

Below is the list of supported variables and their corresponding unit symbols.

### Adimentional

Used for ratios, factors, or unitless values.

- **Units**: `adim`

### Current

Electrical current measurements.

- **Units**: `A`, `mA`, `kA`

### Density

Mass per unit volume.

- **Units**: `kg/bbl`, `kg/gal`, `kg/m3`, `kg/lt`, `kg/ml`, `g/bbl`, `g/gal`, `g/m3`, `g/lt`, `g/ml`

### Force

- **Units**: `N`, `kN`, `MN`, `GN`, `gf`, `kgf`, `dyn`, `J/m`, `J/cm`, `shortTonF`

### Length

- **Units**: `fm`, `pm`, `nm`, `um`, `mm`, `cm`, `m`, `dam`, `hm`, `km`

### Mass

- **Units**: `kg`, `g`, `mg`, `lb`, `metricTon`, `oz`, `grain`, `shortTon`, `longTon`, `slug`

### MassFlow

Mass transfer rate.

- **Units**: `kg/day`, `kg/hr`, `kg/min`, `kg/sec`, `g/day`, `g/hr`, `g/min`, `g/sec`, `mg/day`, `mg/hr`

### Percentage

- **Units**: `%`

### Power

Energy rate.

- **Units**: `kW`, `BTU/hr`, `BTU/min`, `BTU/sec`, `cal/sec`, `cal/min`, `cal/hr`, `erg/sec`, `erg/min`, `erg/hr`

### Pressure

- **Units**: `bar`, `mbar`, `ubar`, `Pa`, `hPa`, `kPa`, `MPa`, `kgcm2`, `atm`, `mmHg`

### Temperature

- **Units**: `K` (Kelvin), `C` (Celsius), `R` (Rankine), `F` (Fahrenheit)

### Time (EngTime)

- **Units**: `ms`, `s`, `minute`, `hr`, `day`

### Volume

- **Units**: `bbl`, `gal`, `m3` (cubic meter), `lt` (liter), `ml`

### VolumetricFlow

Volume transfer rate.

- **Units**: `bbl/day`, `bbl/hr`, `bbl/min`, `bbl/sec`, `gal/day`, `gal/hr`, `gal/min`, `gal/sec`, `m3/day`, `m3/hr`
