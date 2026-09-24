# Address space del servidor OPC UA embebido

Namespace URI: `urn:pyautomationio:opcua:{major}.{minor}` (versión del paquete, hoy 2.9).

El plano de publicación es único. Opción B: `MANUFACTURER` es la carpeta `{site}` y no es un campo del NodeId.

```
ns=<idx>;s=<t|a|e>:<nombre-canonico>
```

Ejemplo: `Supe.Linea1.FI_01` es `ns=2;s=t:supe.linea1.fi_01`.

El nombre se normaliza con NFC, se quitan los caracteres de control, `casefold`, espacios colapsados a `.`, `;` y `,` escapados a `_`, puntos solo al inicio y al final, y un tope de 256 caracteres. El segmento ya va dentro de ese nombre y en la carpeta `{Area}`. No se repite como campo del NodeId. Cambiar `AUTOMATION_MANUFACTURER` o `AUTOMATION_SEGMENT` no reescribe el NodeId de un tag cuyo nombre ya está calificado.

Árbol:

```
Objects/PyAutomationIO/{Site}/{Area}/Process|Alarms|Engines
```

Site vacío → `Default`. Area vacía → `Global`.

Tags analógicos (máximo 5 properties, 6 nodos): `unit` (símbolo de display en texto, por ejemplo `kg/lt`), `EURange` si hay rango, `variable`, `runtime_config` y `filter_config`. `runtime_config` es un JSON con `scan_time` y `dead_band` cuando aplican. `filter_config` es un JSON con `enabled`, `wavelet`, `level` y `threshold_factor` cuando el filtro está activo. Booleanos y strings: solo `variable`. No se publica una property `area`: el segmento ya está en la carpeta y en el nombre canónico.

Alarmas: variable + `state`, `process_condition`, `mnemonic`, `description`.

Engines: variable + `state`, `classification`, `fluid`.

`DataValue` lleva Value, StatusCode, SourceTimestamp y ServerTimestamp. `stale` se publica como `BadWaitingForInitialData`.

Flags:

- `AUTOMATION_OPCUA_SERVER_HOST` (default `0.0.0.0`) y `AUTOMATION_OPCUA_SERVER_PORT` (default `53530`). Endpoint `opc.tcp://{host}:{port}/OPCUAServer/`.
- `AUTOMATION_OPCUA_ANALOG_ITEM=false`: no intenta `AnalogItemType` (el stack 0.98.13 crea `BaseDataVariableType` y el cambio de tipo es best-effort).
- `AUTOMATION_OPCUA_CONSTANT_MODE=true`: omite el reconcile completo y usa la rebanada rotativa de tags.
