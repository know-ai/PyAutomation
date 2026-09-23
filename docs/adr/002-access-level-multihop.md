# ADR 002 — AccessLevel, write-back y multi-hop

Fecha: 2026-09-23. Estado: aceptado.

El permiso de un nodo es un entero de 7 bits, no una fila de catálogo. `UserAccessLevel` copia `AccessLevel`. `AccessRestrictions` se intenta escribir; asyncua 2.0.1 responde `BadAttributeIdInvalid` en una variable nueva, así que el 0 vive en la ficha y en la API.

El write del SCADA se decide en un wrapper de `AttributeService.write` para sesiones que no son Admin. La sesión Admin del tick sigue publicando. El datachange solo encola. Un hilo de sistema aplica el valor al CVT con `source=external`, así el loop asyncio no escribe el CVT. El tracker de dirty no republica ese origen. Un fallo del PLC restaura el valor con `source=rollback`, y ese origen sí se republica para que el SCADA vea la vuelta. El StatusCode del Write original ya fue Good: asyncua termina el write antes del datachange.

El rate limit visible usa `BadTooManyOperations` (0x80100000). `BadOutOfRange` es 0x803C0000. Un write de valor que trae `SourceTimestamp` vacío sigue siendo válido. Se rechaza con `BadNotWritable` cuando el `StatusCode` no es Good y falta `StatusWrite`, o cuando el cliente fija un timestamp explícito (`SourcePicoseconds`) y falta `TimestampWrite`.
