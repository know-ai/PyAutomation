# Bitácora operacional (Operational Logs)

La página **Registros operacionales** (`/operational-logs`) es el cuaderno de la **voz del operador**: notas de jornada, observaciones y relevos. No sustituye a **Eventos** (acciones automáticas / de control) ni al histórico de alarmas.

## Qué queda registrado

| Clasificación | Origen | Vista por defecto |
|---|---|---|
| `Operational` | Modal **Agregar** en esta página (nota de bitácora) | **Bitácora** |
| `General` | Notas antiguas (antes de Bitácora Eterna) | **Bitácora** |
| `Event` | Comentario sobre un evento (`/events`) | **Comentarios** |
| `Alarm` | Comentario sobre un AlarmSummary | **Comentarios** |
| `System` | Telemetría HMI (p. ej. watchdog de memoria) | **Sistema** |

La vista **Bitácora** muestra solo `Operational` y `General`, y **excluye** el watchdog (`description = memory-watchdog`). Use **Comentarios**, **Sistema** o **Todo** para el resto.

## Cómo crear una nota

1. Menú **Registros operacionales**.
2. **Agregar**.
3. Escriba el mensaje (máx. 256 caracteres).
4. Opcional: **turno** (mañana / tarde / noche), **área**, marca **Nota de relevo**.
5. Guardar. El autor es siempre el usuario de la sesión; no se puede impersonar.

Si el historiador está caído, la nota se guarda en el journal SAF local (`journaled`). Aparecerá en PostgreSQL al reconectar. El HMI emite `on.log` para refrescar la tabla.

## Filtros

- **Vista**: Bitácora / Comentarios / Sistema / Todo
- **Buscar**: texto en mensaje **o** descripción (Enter o botón Filtrar)
- **Usuarios** y **alarmas** (multi-select)
- **Rango**: última hora, 6 h, 12 h, **24 h (default)**, semana, mes, personalizado
- **Limpiar**: vuelve a Bitácora + últimas 24 h + sin búsqueda

Zona horaria: la de display de la estación (mismo canal que Eventos).

## Columnas

Id, marca de tiempo, usuario (`user_name` se conserva aunque se borre la cuenta), turno, área, mensaje, descripción, clasificación, relevo, alarma vinculada, evento vinculado.

Exportación **CSV** del conjunto filtrado (hasta 10 000 filas).

## Durabilidad e inmutabilidad

- Escritura: `journal_then_remote` (`DOMAIN.LOG`, crítica). No depende de que `is_db_connected()` sea verdadero.
- No hay edición ni borrado por API.
- Si se borra un usuario, evento o alarma, la fila de bitácora **permanece** (`ON DELETE SET NULL`) y el nombre del autor queda en `user_name`.
- Comentarios de eventos/alarmas se leen también en esas pantallas (`GET .../comments`).

## Eventos vs bitácora

- **Eventos**: qué hizo el sistema o el operador en un control (ack, forzar tag, login…).
- **Bitácora**: por qué se hizo, qué se observó, qué se entrega al siguiente turno.

## Métrica

`GET /api/health/system` incluye `LOGS_RATE_PER_MIN` y `LOGS_RATE_ALERT` (umbral 30/min).
