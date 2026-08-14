# Auditoría de husos horarios — PyAutomationIO (`automation/` + HMI)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`github/PyAutomation/automation`) + HMI React (`hmi/`) |
| **Alcance** | Captura OPC UA → CVT/Socket → historiador TagValue/Events/AlarmSummary → consultas HMI |
| **Clasificación** | Auditoría de arquitectura temporal · Confidencialidad interna |
| **Fecha** | 2026-08-14 |
| **Caso observado** | Laptop en **America/Caracas**; `AUTOMATION_TIMEZONE=America/Lima`; OPC UA SourceTimestamp en **UTC** |
| **Síntoma** | `datalogger` / `trends` / `events` muestran **Caracas**; `real-time-trends` / `alarms/summary` muestran **Lima** |
| **Veredicto** | **Inconsistente por diseño accidental.** Hay **tres relojes de presentación** distintos. El almacenamiento industrial (UTC epoch ms) es correcto; la capa de *display* no tiene una política única. |
| **Offsets relevantes** | Caracas = **UTC−4** fijo · Lima = **UTC−5** fijo → **Δ = 1 h** |

---

## 1. Resumen ejecutivo

PyAutomation **guarda** historia en UTC (bien) y **muestra** tiempos de tres formas distintas:

| Canal | Quién decide el huso de presentación | Origen del huso |
|---|---|---|
| **A — Consultas históricas parametrizadas** | El **cliente HMI** envía `timezone` en el body | Preferencia: `Intl…timeZone` del navegador (Caracas) |
| **B — Tiempo real (Socket.IO)** | El **servidor** convierte a `AUTOMATION_TIMEZONE` antes de emitir | Env `AUTOMATION_TIMEZONE` (Lima) |
| **C — AlarmSummary (histórico)** | El **servidor** serializa siempre con `TIMEZONE` de arranque | Env `AUTOMATION_TIMEZONE` (Lima); **ignora** el `timezone` del filtro para la salida |

Eso explica exactamente el síntoma: pantallas del canal A = laptop; pantallas B/C = planta/servidor.

**Estándar industrial recomendado (ISA / OPC UA / historiadores):**

1. **Almacenar siempre UTC** (o epoch UTC).
2. **Transmitir instantes con offset o `Z`** (ISO-8601), nunca “hora civil ingenua”.
3. **Convertir a huso de planta o de operador solo en la UI** (o con un parámetro de consulta explícito y consistente).
4. Un único “Plant Timezone” documentado; el cliente puede *opcionalmente* ver “My Timezone”.

Hoy PyAutomation cumple (1) en TagValue; falla (2)–(4) en varios caminos de presentación.

---

## 2. Configuración de entorno

### 2.1 Código (`automation/__init__.py`)

```python
_TIMEZONE = os.environ.get('AUTOMATION_TIMEZONE') or "America/Caracas"
TIMEZONE = pytz.timezone(_TIMEZONE)
```

- Solo lee **`AUTOMATION_TIMEZONE`**.
- **No** lee `TIMEZONE` a pelo.
- Default de código: `America/Caracas` (histórico del producto).

### 2.2 Compose iDetectFugas

```yaml
AUTOMATION_TIMEZONE: ${AUTOMATION_TIMEZONE:-${TIMEZONE}}
```

En planta, `TIMEZONE=America/Lima` en `.env` se proyecta a `AUTOMATION_TIMEZONE`. Coherente con Docker; confuso en docs locales que mezclan ambos nombres.

### 2.3 Semántica de `AUTOMATION_TIMEZONE`

Hoy actúa como **“Plant display timezone del proceso”**, no como “huso del operador”:

- Conversión en emit Socket.IO (`cvt.set_value` / alarmas).
- Default de APIs (`_TIMEZONE`).
- Serialización fija de `AlarmSummary`.
- Login payload (`datetime.now(TIMEZONE)`).

**No** gobierna las pantallas históricas que mandan `timezone` del navegador.

---

## 3. Cadena de tiempo (campo → disco → pantalla)

```
  OPC UA SourceTimestamp (UTC)
           │
           ▼
  DAS.update_tag_value
    · fuerza tzinfo=UTC (replace)
    · CVT / SAF / TagValue  ←── epoch ms UTC  ✅
    · buffer DAS: astimezone(TIMEZONE)        ⚠️ solo buffer interno
           │
           ├─► Socket "on.tag" / "on.alarm"
           │     timestamp ya convertido a AUTOMATION_TIMEZONE
           │     string naive "%m/%d/%Y, %H:%M:%S.%f"   ❌ sin offset
           │
           └─► Historiador (UTC)
                 │
                 ├─► Trends / DataLogger / Events
                 │     query: HMI manda timezone=navegador
                 │     respuesta: formateada en ese timezone     ✅ relativo al cliente
                 │
                 └─► AlarmSummary
                       query range: usa timezone del payload
                       serialize(): siempre AUTOMATION_TIMEZONE  ❌
```

---

## 4. Inventario por superficie HMI

| Pantalla | Ruta | Canal | Huso que ve el operador (caso actual) | Mecanismo |
|---|---|---|---|---|
| Data Logger | `/tags/datalogger` | A | **Caracas** | `Intl` → `datalogger_timezone` → API `timezone` → SQL/`astimezone` |
| Trends | `/tags/trends` | A | **Caracas** | Igual; Plotly parsea wall-clock del backend como `Date` local |
| Events | `/events` | A | **Caracas** | `Events.serialize(timezone=payload)` |
| Operational Logs | `/operational-logs` | A | **Caracas** (mismo patrón) | Browser TZ |
| **Real-Time Trends** | `/real-time-trends` | B | **Lima** | Socket ya viene en `TIMEZONE`; StripChart `new Date(p.timestamp)` |
| Alarmas vivas (footer/lista) | varios | B | **Lima** | `@put_alarm_state` hace `astimezone(TIMEZONE)` antes del emit |
| **Alarms Summary** | `/alarms/summary` | C | **Lima** | `AlarmSummary.serialize()` fuerza `TIMEZONE` |
| Communications (attrs) | `/communications` | Mixed | A menudo **Caracas** vía `toLocaleString()` | Timestamp OPC crudo / browser |

### 4.1 Detalle — Real-Time Trends

1. Backend (`cvt.py` ~639): `ts = timestamp.astimezone(TIMEZONE)` antes de `serialize_socket()`.
2. HMI (`StripChart.tsx`): `x: bufferSlice.map((p) => new Date(p.timestamp))`.
3. El string **no trae offset**. El eje muestra la hora civil que mandó el servidor (Lima).

### 4.2 Detalle — Alarms Summary

1. Filtro: convierte rango del operador → UTC (usa `payload.timezone`).
2. **Bug / inconsistencia:** `AlarmsSummary.tsx` si no hay TZ guardada usa `timezones[0]` = **`Africa/Abidjan`** (primer ítem de `pytz.all_timezones`), **no** el huso del navegador ni el de planta.
3. Aun con TZ correcta en el filtro, la **salida** ignora ese parámetro:

```python
# automation/dbmodels/alarms.py — AlarmSummary.serialize
alarm_time = pytz.UTC.localize(alarm_time).astimezone(TIMEZONE)
```

Resultado: operador en Caracas ve filas en Lima (UTC−5).

### 4.3 Detalle — Events / Trends / DataLogger

- Detectan `America/Caracas` con `Intl.DateTimeFormat().resolvedOptions().timeZone`.
- Lo persisten en `localStorage` (`events_timezone`, `trends_timezone`, …).
- Backend formatea la respuesta en ese huso → coincide con el reloj de la laptop.

---

## 5. Almacenamiento (capa correcta)

| Artefacto | Representación | Veredicto |
|---|---|---|
| `TagValue.timestamp` | `TimestampField` epoch **ms UTC** (`timebase.TAGVALUE_TIMESTAMP_RESOLUTION = 3`) | ✅ |
| SAF / journal | ISO UTC / epoch UTC | ✅ |
| `AlarmSummary.alarm_time` | datetime UTC (naive + convención UTC) | ✅ con convención documentada |
| `Events.timestamp` | UTC en BD; serialize admite TZ de salida | ✅/⚠️ |
| Socket / CVT display | String civil **sin zona** en `AUTOMATION_TIMEZONE` | ❌ para interoperabilidad |

La regla “historiador en UTC” está alineada con práctica industrial. El problema está en la **frontera de presentación**.

---

## 6. Hallazgos (severidad)

| ID | Severidad | Hallazgo |
|---|---|---|
| **TZ-C1** | **Alta** | Dos políticas de display coexisten (navegador vs `AUTOMATION_TIMEZONE`) sin documentar → Δ 1 h Caracas↔Lima. |
| **TZ-C2** | **Alta** | `AlarmSummary.serialize` **ignora** el `timezone` del request; siempre planta. |
| **TZ-C3** | **Media** | Socket emite timestamps **naive** ya convertidos; el cliente no puede saber si es UTC, planta u operador. |
| **TZ-H1** | **Media** | `AlarmsSummary` default `timezones[0]` = `Africa/Abidjan` (no browser, no planta). |
| **TZ-H2** | **Media** | Trends parsea wall-clock del servidor como `Date` “local del browser” (coincide solo si TZ query = TZ browser). |
| **TZ-B1** | **Baja** | `SourceTimestamp.replace(tzinfo=UTC)` asume naive UTC; si viniera aware en otra zona, sería incorrecto (`astimezone` sería más seguro). |
| **TZ-B2** | **Baja** | Docs/env mezclan `TIMEZONE` y `AUTOMATION_TIMEZONE`; el código solo honra el segundo. |
| **TZ-OK1** | — | TagValue / SAF en UTC ms es la base correcta. |

---

## 7. Estándar industrial de referencia

| Fuente | Principio aplicable |
|---|---|
| **OPC UA** | Timestamps de valor = UTC (Source/ServerTimestamp). |
| **ISA-18.2 / alarm management** | Eventos de alarma con marca temporal inequívoca; reportes en huso de **planta** acordado. |
| **Historiadores (PI, IP.21, etc.)** | Store UTC; client timezone / plant timezone en visualización. |
| **ISO 8601** | Instantes con `Z` u offset; evitar datetime naive en APIs. |

### Política objetivo recomendada para PyAutomation

| Capa | Política |
|---|---|
| Campo / OPC | UTC |
| Disco / SAF / PG | UTC (epoch o ISO-Z) |
| API JSON | **ISO-8601 con offset o `Z`** (ej. `2026-08-14T03:15:00.000Z`) |
| HMI | Convertir con: (1) **Plant TZ** = `AUTOMATION_TIMEZONE`, o (2) **Operator TZ** = browser, con selector explícito y default documentado |
| Alarmas históricas | Misma regla que Events: `serialize(timezone=…)` |

**Default de producto sugerido**

- Planta (SCADA en sitio): default display = **Plant TZ** (`AUTOMATION_TIMEZONE`).
- Ingeniería remota: permitir override “Mi zona (navegador)”.
- Nunca mezclar ambos sin etiqueta en la UI (“hora planta” / “hora local”).

---

## 8. Matriz “esperado vs actual” (caso Caracas + Lima)

Asumiendo un evento de campo a **15:00:00 UTC**:

| Pantalla | Esperado si Plant TZ = Lima | Esperado si Operator TZ = Caracas | **Actual** |
|---|---|---|---|
| Trends / DataLogger / Events | 10:00 Lima | 11:00 Caracas | **11:00 Caracas** (browser) |
| Real-Time Trends | 10:00 Lima | 11:00 Caracas | **10:00 Lima** (server emit) |
| Alarms Summary | 10:00 Lima | 11:00 Caracas | **10:00 Lima** (serialize fijo) |

No es un “bug de OPC”; es **divergencia de política de display**.

---

## 9. Plan de remediación (priorizado)

### P0 — Alinear presentación (sin romper storage)

1. **AlarmSummary.serialize(timezone=…)** igual que Events; el resource debe pasar el TZ del payload a la salida.
2. **Socket payload**: emitir ISO-Z (UTC) *o* `{ utc: "...Z", plant: "..." }` — dejar de mutar el instante a civil naive.
3. **HMI RT / alarms live**: formatear con un único helper (`plant` vs `operator`) y mostrar etiqueta de huso.

### P1 — Defaults HMI coherentes

4. Unificar detección de TZ en DataLogger / Trends / Events / AlarmsSummary / OperationalLogs:
   - Preferir browser si está en la lista;
   - else `AUTOMATION_TIMEZONE` expuesto por API (`/api/system/timezone` o settings);
   - **nunca** `timezones[0]`.
5. Exponer en API el plant timezone efectivo (`_TIMEZONE`) para que la HMI no adivine.

### P2 — Contrato y docs

6. Documentar en README/DESPLIEGUE: `AUTOMATION_TIMEZONE` = huso de **planta**; `TIMEZONE` en compose es alias.
7. Tests: un instante UTC fijo → assert de strings en Caracas vs Lima en cada endpoint/socket.

### No hacer

- No “arreglar” cambiando solo `.env` a Caracas: eso alinea RT/alarms con la laptop **de prueba**, pero en planta Lima seguiría siendo el huso operativo correcto; el bug de política permanecería.

---

## 10. Checklist de verificación (post-fix)

```text
[x] TagValue / Events / AlarmSummary en BD siguen en UTC
[x] GET/POST históricos con timezone=America/Caracas y America/Lima dan Δ 1 h
[x] AlarmSummary output respeta el timezone del request
[x] on.tag / on.alarm traen Z u offset; RT trends coinciden con el selector elegido
[x] UI muestra badge "Planta: America/Lima" o "Local: America/Caracas"
[x] Default AlarmsSummary ≠ Africa/Abidjan
[x] Documentación env: AUTOMATION_TIMEZONE vs TIMEZONE
```

**Estado (2026-08-14):** Operación «Hora Única» aplicada. `AUTOMATION_TIMEZONE` = huso de **planta** (presentación / informes). La HMI elige planta vs local (`localStorage display_timezone`). Sockets emiten ISO-8601 UTC. `GET /api/system/timezone` expone el huso de planta.

---

## 11. Archivos clave

| Área | Archivo |
|---|---|
| Env / TZ global | `automation/__init__.py` |
| OPC → CVT | `automation/opcua/subscription.py` |
| Emit tags | `automation/tags/cvt.py` (`set_value` / `serialize_socket`) |
| Emit alarms | `automation/utils/decorators.py` (`put_alarm_state`) |
| Trends SQL | `automation/logger/datalogger.py` |
| Events out | `automation/dbmodels/events.py` (`serialize(timezone=…)`) |
| AlarmSummary out | `automation/dbmodels/alarms.py` (`AlarmSummary.serialize`) |
| API filter alarms | `automation/modules/alarms/resources/summary.py` |
| HMI TZ detect | `hmi/src/pages/{Trends,DataLogger,Events,AlarmsSummary,OperationalLogs}.tsx` |
| HMI RT | `hmi/src/components/StripChart.tsx`, `hmi/src/pages/RealTimeTrends.tsx` |
| Compose | `idetectfugas/compose/docker-compose.yml`, `compose/.env` |

---

## 12. Conclusión

El sistema **no está “mal sincronizado con OPC UA”**: el campo llega en UTC y el historiador lo guarda en UTC. Lo que falla es la **política de presentación**:

- Consultas históricas “modernas” → huso del **navegador** (Caracas en tu prueba).
- Tiempo real y resumen de alarmas → huso de **planta/servidor** (`America/Lima`).

Con Caracas (UTC−4) y Lima (UTC−5) la diferencia de **una hora** es el síntoma visible. La corrección no es solo cambiar el `.env` a Caracas, sino **unificar** el contrato (UTC en wire + un selector Plant/Operator en UI) según práctica industrial.
