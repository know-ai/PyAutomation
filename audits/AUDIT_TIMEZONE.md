# Auditoría compacta: husos horarios (Operación «Hora Única»)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/`) |
| **Alcance** | Captura OPC UA → CVT/Socket → historiador → consultas HMI |
| **Fecha original** | 2026-08-14 (tres relojes de presentación) |
| **Compactación** | 2026-08-18 — evidencia de código: sockets ISO-UTC; selector planta/local; AlarmSummary respeta TZ de request |
| **Caso observado (pre-fix)** | Laptop `America/Caracas`; planta `America/Lima`; Δ = 1 h entre pantallas |
| **Veredicto vigente** | Storage UTC **correcto**. Presentación unificada: wire ISO-8601 UTC; HMI convierte con selector **Planta** (`AUTOMATION_TIMEZONE`) vs **Local** (navegador). Badge visible |
| **Clasificación** | Auditoría de arquitectura temporal |

---

## 0. Contrato vigente (2026-08-18)

| Capa | Política |
|---|---|
| Campo / OPC | UTC (`ensure_utc`) |
| Disco / SAF / PG | UTC (epoch ms o ISO-Z) |
| API JSON / Socket.IO | ISO-8601 con offset (`+00:00` o `Z`) |
| HMI | Operador elige `display_timezone` = `plant` \| `local` (`localStorage`). Default: local si el browser tiene IANA, si no planta |
| Informes / serialize histórico | Parámetro `timezone` del request; fallback `AUTOMATION_TIMEZONE` |

`AUTOMATION_TIMEZONE` es el **huso de planta**. No cambia storage ni lógica (alarmas, detección, cálculos). En compose, `TIMEZONE` es solo alias: `AUTOMATION_TIMEZONE: ${AUTOMATION_TIMEZONE:-${TIMEZONE}}`. El proceso Python lee **solo** `AUTOMATION_TIMEZONE` (default código `America/Caracas`).

`GET /api/system/timezone` → `{ "timezone": "<IANA>", "role": "plant" }`.

Tests: `automation.tests.test_timezone_hora_unica`.

---

## 1. Diagnóstico original (por qué se vio 1 h)

Se conserva: explica el síntoma Caracas vs Lima **antes** de Hora Única.

Tres canales de display:

| Canal | Quién decidía | Efecto en la prueba |
|---|---|---|
| **A** — Históricos parametrizados | HMI mandaba `timezone` = `Intl` del navegador | DataLogger / Trends / Events / Operational Logs = **Caracas** |
| **B** — Socket.IO | Servidor hacía `astimezone(TIMEZONE)` y emitía string **naive** | Real-Time Trends / alarmas vivas = **Lima** |
| **C** — AlarmSummary | `serialize()` forzaba `TIMEZONE` e **ignoraba** el TZ del filtro | Alarms Summary = **Lima**. Default HMI `timezones[0]` = **`Africa/Abidjan`** si no había TZ guardada |

El campo llegaba en UTC y TagValue se guardaba en UTC. El fallo era **política de presentación**, no OPC.

Matriz (evento 15:00:00 UTC, pre-fix):

| Pantalla | Plant TZ = Lima | Operator TZ = Caracas | **Actual entonces** |
|---|---|---|---|
| Trends / DataLogger / Events | 10:00 Lima | 11:00 Caracas | **11:00 Caracas** |
| Real-Time Trends | 10:00 Lima | 11:00 Caracas | **10:00 Lima** |
| Alarms Summary | 10:00 Lima | 11:00 Caracas | **10:00 Lima** |

---

## 2. Hallazgos (IDs) y estado

| ID | Sev. original | Hallazgo | Estado 2026-08-18 |
|---|---|---|---|
| **TZ-C1** | Alta | Dos políticas (navegador vs planta) sin documentar | **Cerrado** — selector explícito + badge |
| **TZ-C2** | Alta | `AlarmSummary.serialize` ignoraba el TZ del request | **Cerrado** — `serialize(timezone=…)` + `format_display_datetime` |
| **TZ-C3** | Media | Socket timestamps naive ya convertidos | **Cerrado** — `serialize_socket` / `iso_millis` ISO con offset UTC |
| **TZ-H1** | Media | AlarmsSummary default `Africa/Abidjan` | **Cerrado** — no usar `pytz.all_timezones[0]` |
| **TZ-H2** | Media | Trends parseaba wall-clock como Date local | Mitigado si el wire trae offset (ISO) |
| **TZ-B1** | Baja | `SourceTimestamp.replace(tzinfo=UTC)` vs `astimezone` | `ensure_utc` en tests; revisar DAS usa `ensure_utc` |
| **TZ-B2** | Baja | Docs mezclan `TIMEZONE` y `AUTOMATION_TIMEZONE` | Documentado: compose alias; código solo el segundo |
| **TZ-OK1** | — | TagValue / SAF UTC ms | Sigue vigente |

Estándar de referencia (sin cambio): OPC UA timestamps UTC; ISA-18.2 marca inequívoca; historiadores store UTC / display plant or operator; ISO-8601 con Z u offset.

**No hacer:** «arreglar» solo poniendo `.env` a Caracas. Eso alinea la laptop de prueba y deja el bug de política en planta Lima.

---

## 3. Cadena de tiempo (actual)

```
OPC UA SourceTimestamp
    → ensure_utc → CVT / SAF / TagValue (epoch ms UTC)
    → serialize_socket: iso_millis → "…+00:00" / "…Z"
    → HMI: Date parse + format en plant | local
Historiador
    → filter_by / trends: rango convertido a UTC
    → serialize(timezone=payload o planta)
```

AlarmSummary: resolución ms en `alarm_time` / `ack_time` (`ensure_schema` escala ticks legacy en segundos).

---

## 4. Checklist

```text
[x] TagValue / Events / AlarmSummary en BD en UTC
[x] GET/POST históricos Caracas vs Lima → Δ 1 h
[x] AlarmSummary output respeta timezone del request (fallback planta)
[x] on.tag / on.alarm ISO-8601 UTC; RT trends siguen el selector
[x] UI badge Planta vs Local (`display_timezone`)
[x] Default AlarmsSummary ≠ Africa/Abidjan
[x] README/docs: AUTOMATION_TIMEZONE vs TIMEZONE
[x] Tests test_timezone_hora_unica
```

Validación rápida:

```bash
python -m unittest automation.tests.test_timezone_hora_unica -v
curl -k https://localhost:8050/api/system/timezone
```

---

## 5. Archivos clave

| Área | Archivo |
|---|---|
| Env | `automation/__init__.py` |
| Timebase | `automation/timebase.py` (`iso_millis`, `ensure_utc`, `format_display_datetime`) |
| Socket tags | `automation/tags/tag.py` `serialize_socket` |
| AlarmSummary | `automation/dbmodels/alarms.py` |
| API timezone | `automation/modules/system/resources/system.py` |
| HMI selector / format | `hmi/src/utils/timezone.ts`, `hmi/src/hooks/useDisplayTimezone.ts`, `TimezoneBadge` |
| Tests | `automation/tests/test_timezone_hora_unica.py` |
