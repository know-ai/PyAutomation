# Address space del servidor OPC UA embebido

Namespace URI: `urn:pyautomationio:opcua:{major}.{minor}` (versión del paquete, hoy 2.9).

El plano de publicación es único. Opción B: `MANUFACTURER` es la carpeta `{site}` y no es un campo del NodeId.

```
ns=<idx>;s=<t|a|e>:<area>:<nombre-canonico>
```

Ejemplo: `Supe.Linea1.FI_01` en el área `Linea1` es `ns=2;s=t:linea1:supe.linea1.fi_01`.

El nombre se normaliza con NFC, se quitan los caracteres de control, `casefold`, espacios colapsados a `.`, `;` y `,` escapados a `_`, puntos solo al inicio y al final, y un tope de 256 caracteres. El NodeId no depende de la carpeta ni de `AUTOMATION_MANUFACTURER`. Cambiar `AUTOMATION_SEGMENT` sí cambia los NodeIds de esa área. No cambiar `SEGMENT` en una planta que ya tiene bindings.

Árbol:

```
Objects/PyAutomationIO/{Site}/{Area}/Process|Alarms|Engines
```

Site vacío → `Default`. Area vacía → `Global`.

Tags analógicos (máximo 6 properties, 7 nodos): `EngineeringUnits` (o la property `unit` si el probe de AnalogItem falla), `EURange` si hay rango, `variable`, `area`, `runtime_config` y `filter_config`. `runtime_config` es un JSON con `scan_time` y `dead_band` cuando aplican. `filter_config` es un JSON con `enabled`, `wavelet`, `level` y `threshold_factor` cuando el filtro está activo. Booleanos y strings: solo `variable` y `area`.

Alarmas: variable + `state`, `process_condition`, `mnemonic`, `description`.

Engines: variable + `state`, `classification`, `fluid`.

`DataValue` lleva Value, StatusCode, SourceTimestamp y ServerTimestamp. `stale` se publica como `BadWaitingForInitialData`.

Flags:

- `AUTOMATION_OPCUA_SERVER_HOST` (default `0.0.0.0`) y `AUTOMATION_OPCUA_SERVER_PORT` (default `53530`). Endpoint `opc.tcp://{host}:{port}/OPCUAServer/`.
- `AUTOMATION_OPCUA_ANALOG_ITEM=false`: no intenta `AnalogItemType` (el stack 0.98.13 crea `BaseDataVariableType` y el cambio de tipo es best-effort).
- `AUTOMATION_OPCUA_CONSTANT_MODE=true`: omite el reconcile completo y usa la rebanada rotativa de tags.
