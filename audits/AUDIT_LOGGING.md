# Auditoría de gestión de logs — PyAutomationIO (`automation/`)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`github/PyAutomation/automation`) |
| **Alcance** | Logs de aplicación (archivo), logs operativos en BD, anti-flood / debounce, rotación y techos de disco; relación con historiador/SAF cuando el “log” es persistencia industrial |
| **Clasificación** | Auditoría operativa · Confidencialidad interna |
| **Fecha** | 2026-08-16 (actualizado: Operación «Trazabilidad Eterna» + «Log Eterno») |
| **Metodología** | Revisión estática de `core.__start_logger`, `RotatingFileHandler`, Settings API, decoradores, auditores OPC/DB/SAF/sesión, `CycleSampleCache`, journal SAF, HMI watchdog, `audit_metrics` |
| **Veredicto** | **A+** en logs de archivo y anti-flood de ERROR: `DedupeFilter` (cooldown 60 s, caché ≤ 1000), `StreamHandler` ERROR, métrica `LOG_ERROR_RATE_PER_MIN`. L3 Events: anti-spam por dominio (DB boot silencioso, OPC/SAF 60 s, operador sin debounce) + `EVENTS_RATE_PER_MIN`. Retención PG/backups SQLite sigue siendo política de planta. |
| **Complementa** | `AUDIT_USER_EVENTS.md` (inventario de la tabla `Events`), `AUDIT_OPERATIONAL_LOGS.md` (bitácora L2 / tabla `Logs`), `AUDIT_BACKEND_PERFORMANCE.md` (BE-OK3), `STORE_AND_FORWARD.md`, `PERFORMANCE_RUNBOOK.md`, `docs/Developments_Guide/logs.md` |

---

## 1. Resumen ejecutivo

PyAutomation gestiona **tres capas distintas** que a menudo se llaman “logs” pero no comparten el mismo ciclo de vida:

| Capa | Qué es | Dónde vive | ¿Crece sin tope? |
|---|---|---|---|
| **L1 — Log de runtime** | `logging` Python (`ERROR`/`WARNING`/`INFO`) | `logs/app.log` (+ rotados) | **No** — `RotatingFileHandler` con `maxBytes` × `backupCount` |
| **L2 — Log operativo / auditoría HMI** | Tabla `Logs` (mensajes de usuario, watchdog HMI, `/api/logs/add`) | Historiador remoto (+ journal SAF) | **Sí en PG** si planta no retenciona; escritura acotada por paginación en lectura y por `is_history_logged` |
| **L3 — Historia industrial** | `TagValue`, `Events`, `AlarmSummary` | Historiador + SAF local | Journal **sí** tiene caps; PG remoto **no** se vacía solo |

Esta auditoría se centra en **L1** (cuello de botella de I/O de texto y disco local del contenedor) y en las **estrategias de debounce / anti-spam** que evitan que L2/L3 o el propio L1 se conviertan en un problema de performance. L3 se documenta solo en la medida en que satura disco o el logger worker.

```
  Hot path SM / API / OPC
           │
           ├─► @logging_error_handler ──► logging.error ──► DedupeFilter ──► File + stdout ERROR
           │                                      ▲
           │                                      │ niveles urllib3/peewee/opcua silenciados
           │
           ├─► set_event / auditores ──► Events (L3)  [cooldown / buffer acotado]
           │
           └─► set_value ──► CycleSampleCache ──► SAF journal (caps) ──► PG TagValue (L3)
```

---

## 2. Inventario de productores de log

### 2.1 Runtime (L1)

| Productor | Nivel típico | Frecuencia | Notas |
|---|---|---|---|
| `@logging_error_handler` | ERROR | Por excepción | Solo `logger.error` (sin `print`). Dedupe 60 s en el logger |
| `logging.getLogger("pyautomation")` | INFO–CRITICAL | Ad hoc | Propagates al root |
| Librerías | Filtrado | Arranque | `urllib3`/`requests`/`peewee` → WARNING; `opcua` → CRITICAL |
| SAF journal flush/replicator | ERROR/CRITICAL | Fallos | `exc_info=True` en fallos de flush/replicación |
| LoggerWorker | CRITICAL | Reconnect DB | “Trying reconnect…” / éxito |

### 2.2 Operativo estructurado (L2)

| Productor | Destino | Anti-flood |
|---|---|---|
| `app.create_log` / `POST /api/logs/add` | `Logs` via `LogsLoggerEngine` | Solo si `is_history_logged`; journal_then_remote |
| HMI `useMemoryWatchdog` | `POST /logs/add` | Emite **una vez** por cruce de umbral (`warned` flag); poll 60 s |
| Settings / arranque | `app.log` INFO | Una vez por boot / cambio |

### 2.3 Historia / auditoría de planta (L3)

| Productor | Destino | Anti-flood / techo |
|---|---|---|
| `set_value` → TagValue | SAF + PG | `CycleSampleCache` (mismo tag/valor/timestamp de ciclo → drop) |
| `@set_event` / `persist_system_event` | Events | Operador **sin** debounce. Sistema: DB boot silencioso; OPC/SAF cooldown 60 s. Inventario: `AUDIT_USER_EVENTS.md` |
| `DatabaseConnectionAuditor` | Events | Runtime: `DISCONNECTED` + `RECONNECTED`. Buffer ≤ 8. Fallos de reconnect resumidos en RECONNECTED |
| `system_lifecycle_audit` | Events | Un `System started` / `System stopped` por ciclo de proceso |
| `user_session_audit` | Events | `Security`: login/logout/identidad. IP en `origin=` |
| `audit_metrics` | `/api/health/system` | `EVENTS_RATE_PER_MIN`; `EVENTS_RATE_ALERT` si > 30/min |
| OPC UA audit | Events | Cooldown de fallos **60 s** (`failure_cooldown_seconds`) |
| SAF journal | Events + L1 CRITICAL | `SAF backpressure triggered` / `SAF disk full` (cooldown 60 s via `audit_metrics.cooldown_allows`) |
| Alarm operator actions | Events (`Control`) | ack/shelve/OOS — una fila por acción |
| Alarm process transitions | AlarmSummary | UNACK/RTN **no** van a Events (anti-spam) |

---

## 3. Rotación de logs de archivo (L1) — garantía de disco acotado

### 3.1 Mecanismo

En `PyAutomation.__start_logger` (`automation/core.py`):

1. Se limpia el root logger (evita handlers duplicados tras re-arranques en el mismo proceso).
2. Se crea un único `RotatingFileHandler` sobre `self._log_file` (por defecto `logs/app.log`).
3. Formato: `%(asctime)s:%(levelname)s:%(message)s`, encoding UTF-8.
4. El logger nombrado `pyautomation` **propaga** al root (sin segundo FileHandler → sin duplicar líneas en archivo).

Cuando el archivo activo supera `maxBytes`, se rota a `app.log.1` … `app.log.N` y se descarta el más antiguo según `backupCount`.

### 3.2 Valores por defecto y techo de disco

| Parámetro | Default | Origen de override |
|---|---|---|
| `log_max_bytes` | **10 MiB** (`10 * 1024 * 1024`) | Env `AUTOMATION_LOG_MAX_BYTES` → `db/app_config.json` → `update_log_config` |
| `log_backup_count` | **3** | Env `AUTOMATION_LOG_BACKUP_COUNT` → config → API |
| `log_level` | **20 (INFO)** en config; `__init__` arranca con WARNING hasta `__start_logger` | `log_level` en config / `update_log_level` |
| `logger_period` | **10.0 s** | Periodo del `LoggerWorker` (replicación SAF / backup SQLite), **no** es flush de `app.log` |

**Techo teórico de disco L1:**

\[
\text{disco}_{L1} \le \texttt{log\_max\_bytes} \times (1 + \texttt{log\_backup\_count})
\]

Con defaults: **≤ 40 MiB** (`app.log` + 3 backups). No es crecimiento infinito.

Validación API (`/api/settings/update`):

- `log_max_bytes` ≥ 1024  
- `log_backup_count` ≥ 1  
- Ambos deben enviarse juntos  
- `log_level` ∈ {0, 10, 20, 30, 40, 50}  
- `logger_period` ≥ 1.0 s  

### 3.3 Actualización en caliente

`update_log_config(max_bytes, backup_count)`:

- Recorre handlers del root y actualiza `maxBytes` / `backupCount` del `RotatingFileHandler` existente.
- Persiste en `app_config`.
- **No** fuerza `doRollover()` inmediato (el rollover ocurre en la siguiente escritura que exceda el tamaño).

`update_log_level(level)` actualiza root + `pyautomation` y persiste.

### 3.4 Qué **no** rota el framework

| Artefacto | Rotación framework | Riesgo |
|---|---|---|
| `logs/app.log*` | Sí | Bajo |
| stdout/stderr de gunicorn / Docker | Depende del orquestador | Si se redirige a archivo sin logrotate del host, **sí** puede crecer. `@logging_error_handler` ya no hace `print`; queda `print` residual en `validate_types` (mismatch de tipo, no el hot path) y prints de arranque en `core.py` |
| `db/saf/journal.db` | Caps + GC de SENT | Acotado por `saf_max_disk_bytes` (default 10 GiB) |
| `db/backups/*.db` (VACUUM INTO SQLite local) | Dispara a > 1 GiB del historian local | **Puede acumular archivos** si ops no los poda |
| Tablas PG `Logs` / `Events` / `TagValue` | No | Retención = política de planta |

---

## 4. Estrategias de debounce / anti-flood / “no spam”

PyAutomation **no** usa un `logging.Filter` genérico de rate-limit. El control de volumen es **por dominio**:

### 4.1 Silencio de librerías ruidosas (startup)

```text
urllib3, requests, peewee → WARNING
opcua → CRITICAL
```

Evita que el stack OPC/HTTP llene `app.log` a INFO en régimen.

### 4.2 CycleSampleCache — debounce de historiador (L3), impacto indirecto en L1/SAF

| | |
|---|---|
| **Archivo** | `automation/persistence/cycle_dedupe.py` |
| **Regla** | Mismo `tag` + mismo `timestamp` de ciclo + mismo `value` → **drop** (no entra al journal) |
| **TTL** | 2.0 s con prune cada 0.5 s |
| **Dominio** | Solo `DOMAIN.TAG` (no alarmas/eventos) |
| **Efecto** | Reduce I/O SAF/PG y, en fallos de persistencia, reduce cascadas de `logging.error` por batch |

Esto es el “debounce” más importante del hot path de **escritura de historia**, no del texto de log.

### 4.3 DatabaseConnectionAuditor — buffer acotado (L2/L3 Events)

| | |
|---|---|
| **Archivo** | `automation/utils/db_audit.py` |
| **Capacidad** | `_PENDING_CAP = 8` eventos en memoria mientras DB está caída |
| **Anti-spam** | Connect inicial de boot **no** escribe Events. En outage: un `DISCONNECTED`; fallos de reconnect se **resumen** en el `RECONNECTED` en lugar de encolar uno por ciclo del watchdog |
| **Descripciones** | `clip(..., DESCRIPTION_MAX=256)`; nunca credenciales |

Sin esto, un `logger_period` de 10 s durante un outage de horas generaría miles de Events / líneas ERROR.

### 4.4 OPC UA failure cooldown — 60 s

| | |
|---|---|
| **Archivo** | `automation/utils/opcua_audit.py` |
| **Constante** | `_FAILURE_COOLDOWN_S = 60.0` |
| **Efecto** | Fallos de conexión/reconnect no generan un Event de auditoría por cada intento inmediato |

### 4.5 HMI memory watchdog — un log por episodio

| | |
|---|---|
| **Archivo** | `hmi/src/hooks/useMemoryWatchdog.ts` |
| **Poll** | 60 s |
| **Debounce** | Flag `warned`: un `POST /logs/add` y un toast por cruce de umbral; se resetea al bajar del umbral |

### 4.6 SAF backpressure (protege disco, no el texto de log)

| Guardrail | Default | Comportamiento |
|---|---|---|
| `max_pending_rows` | 5e6 | `JournalBackpressureError`; métrica `SAF_PENDING_CAP_HITS` |
| `ring_maxsize` | 50 000 | Drop + backpressure |
| `max_disk_bytes` | 10 GiB | Evict SENT antiguos; si no basta → `JournalDiskFullError` + CRITICAL en L1 **y** Event `SAF disk full` (cooldown 60 s) |
| `gc_sent_after_s` | 3600 s | GC post-ACK |
| `replicate_rate_per_s` | 10 000 | Rate limit de réplica |

### 4.7 `@logging_error_handler` + `DedupeFilter` — **RESUELTO (Log Eterno)**

| | |
|---|---|
| **Archivo** | `automation/utils/log_filters.py`, `decorators.py`, `core.__start_logger` |
| **Comportamiento** | Cada excepción → `logger.error(msg)` estructurado. **Sin** `print` (tampoco en `validate_types`). El filtro suprime repeticiones `(pathname, lineno, funcName, msg)` durante `log_error_cooldown_seconds` (default 60). Al reemitir, anota `[repeated N times in last Xs]`. Caché LRU ≤ 1000. `cooldown=0` desactiva. |
| **Stdout** | `StreamHandler(sys.stdout)` nivel ERROR, mismo formatter; no comparte el filtro a nivel handler (evitaría el segundo destino). |
| **Métrica** | `LOG_ERROR_RATE_PER_MIN` cuenta **intentos** ERROR (incl. suprimidos); `LOG_ERROR_ALERT` si > 5/min. |
| **Caliente** | `PUT /api/settings/update` `{ "log_error_cooldown_seconds": 60 }` |

Un error a 1 Hz → **1 línea escrita / 60 s** (~98 % menos I/O). La alerta de health sigue viendo ~60 intentos/min.

### 4.8 Capa Events — anti-spam por dominio (Trazabilidad Eterna)

| Dominio | Política | Archivo |
|---|---|---|
| Acciones de operador (login, ack, forzar tag, CRUD, transición) | **Sin** debounce | `@set_event` / `record_user_session_event` / recursos HTTP |
| DB historiador | Boot silencioso; en caliente un `DISCONNECTED` + un `RECONNECTED` por outage | `db_audit.py` |
| OPC UA | Cooldown 60 s en fallos | `opcua_audit.py` |
| SAF capacidad | Cooldown 60 s (`saf:backpressure` / `saf:disk`) | `persistence/journal.py` + `audit_metrics.cooldown_allows` |
| Arranque / parada | Una vez por proceso | `system_lifecycle_audit.py` |
| Tasa global | `EVENTS_RATE_PER_MIN`; alerta > 30/min | `GET /api/health/system` |

Catálogo de mensajes y clasificaciones (`Security` / `Configuration` / `Control` / `System` / `Database` / `OPC UA`): **`AUDIT_USER_EVENTS.md`**.

---

## 5. LoggerWorker vs “logging”

Nombre histórico engañoso: `LoggerWorker` **no** escribe `app.log`. Su ciclo (`logger_period`, default 10 s):

1. Verifica conectividad / reconnect DB (auditor DB).  
2. Backup SQLite local si el archivo > 1 GiB (`VACUUM INTO`, checksum SHA-256).  
3. `replicate_once()` del gateway SAF.  
4. Mantiene sesiones OPC UA.

Bajar `logger_period` aumenta presión de réplica y de intentos de reconnect; **no** aumenta la tasa de líneas en `app.log` salvo por mensajes CRITICAL de reconnect.

Flag global `is_history_logged` (vía `DBManager.set_db`): si es `False`, los engines de TagValue/Alarms/Events/Logs **no persisten** historia (corte de volumen L2/L3).

---

## 6. Performance: ¿los logs son cuello de botella?

| Escenario | ¿Cuello? | Evidencia / mitigación |
|---|---|---|
| Régimen sano, nivel INFO/WARNING | No | Un FileHandler; librerías silenciadas; sin sync fsync forzado en cada línea (buffer stdlib) |
| Excepción 1 Hz en N state machines | No (I/O) | Dedupe 60 s; métrica alerta si intentos > 5/min |
| Outage PG prolongado | Parcial | Auditor DB acotado; SAF cap; CRITICAL ocasional en L1 |
| DEBUG global en planta | **Sí** | `log_level=10` multiplica volumen; rotación sigue acotando disco L1 pero el worker gasta más CPU |
| Lectura HMI de Logs/Events | No si se pagina | API `page`/`limit` (default 20) |

Métrica operativa:

- `GET /api/health/system` → `LOG_ERROR_RATE_PER_MIN`, `LOG_ERROR_SUPPRESSED_PER_MIN`, `LOG_ERROR_ALERT`, **`EVENTS_RATE_PER_MIN`**, **`EVENTS_RATE_ALERT`**, **`LOGS_RATE_PER_MIN`**, **`LOGS_RATE_ALERT`**.
- Tamaño de `logs/app.log*` vs `log_max_bytes * (1+backup)`.
- `SAF_PENDING_CAP_HITS` / `SAF_QUEUE_DEPTH` (historia, no L1).

---

## 7. Hallazgos

### 7.1 Fortalezas (OK)

| ID | Hallazgo |
|---|---|
| **LOG-OK1** | `RotatingFileHandler` con techo explícito y defaults conservadores (10 MiB × 3) |
| **LOG-OK2** | Config persistente + API Settings + env vars |
| **LOG-OK3** | FileHandler + StreamHandler ERROR; filtro en **logger** (una vez por record) |
| **LOG-OK4** | Niveles de terceros elevados (peewee/opcua/urllib3) |
| **LOG-OK5** | Auditores DB/OPC con buffer/cooldown; textos clippeados |
| **LOG-OK6** | CycleSampleCache + caps SAF |
| **LOG-OK7** | Watchdog HMI no spamea Logs |
| **LOG-OK8** | `DedupeFilter` cooldown 60 s, LRU 1000, `cooldown=0` desactiva |
| **LOG-OK9** | `LOG_ERROR_RATE_PER_MIN` / `LOG_ERROR_ALERT` en `/api/health/system` |
| **LOG-OK10** | `EVENTS_RATE_PER_MIN` / `EVENTS_RATE_ALERT` (umbral 30/min) en `/api/health/system` |
| **LOG-OK11** | Events de SAF backpressure/disk con cooldown 60 s; no un Event por sample rechazado |

### 7.2 Gaps / riesgos

| ID | Severidad | Hallazgo | Estado |
|---|---|---|---|
| **LOG-H1** | — | Rate-limit decorator | **Cerrado** — `DedupeFilter` |
| **LOG-H2** | — | `print` doble en `@logging_error_handler` | **Cerrado** — solo logger + StreamHandler ERROR |
| **LOG-M3** | — | `print` residual en `validate_types` | **Cerrado** — solo `logger.error`; `DedupeFilter` anota repeticiones al reemitir |
| **LOG-H3** | Info | stdout Docker | **Documentado** — runbook §6.2 (`max-size=10m`) |
| **LOG-H4** | Info | Backups SQLite | **Documentado** — no poda automática a propósito; script ops §6.3 |
| **LOG-H5** | Info | TTL PG | **Documentado** — retención DBA, no `DELETE` desde app |
| **LOG-M1** | — | Métrica | **Cerrado** |
| **LOG-M2** | Bajo | `update_log_config` no fuerza rollover inmediato | Aceptable |

---

## 8. Criterios de aceptación (gestión de logs sana)

| ID | Criterio | Cómo verificar |
|---|---|---|
| **CA-LOG-1** | Disco L1 acotado | `du -sb logs/` ≤ `log_max_bytes * (1 + log_backup_count) * 1.1` tras soak 24 h |
| **CA-LOG-2** | Rotación efectiva | Tras generar > `maxBytes`, existen `app.log.1`… y el más viejo se recicla |
| **CA-LOG-3** | Cambio en caliente | `PUT /api/settings/update` incluye `log_error_cooldown_seconds` |
| **CA-LOG-4** | Sin spam de reconnect DB | Durante outage 1 h, Events de DB ≤ O(1) por fase (no uno por `logger_period`) |
| **CA-LOG-5** | OPC failure cooldown | Intentos fallidos < 60 s no multiplican Events de fallo |
| **CA-LOG-6** | CycleSampleCache | Reescrituras idénticas mismo ciclo no incrementan PENDING |
| **CA-LOG-7** | Error 1 Hz → 1 línea escrita / cooldown; proceso vivo | `DedupeFilter`; `LOG_ERROR_RATE_PER_MIN` cuenta intentos |
| **CA-LOG-8** | Tasa de Events visible y acotada | `GET /api/health/system` expone `EVENTS_RATE_PER_MIN`; alerta > 30/min; boot DB silencioso |

---

## 9. Runbook rápido (ops)

### 9.1 Verificar techos

```bash
# Archivo de runtime
ls -lh logs/app.log*
# Config efectiva
curl -sS -H "Authorization: Bearer $TOKEN" "$BASE/api/settings/" | jq '{log_max_bytes,log_backup_count,log_level,logger_period}'
# SAF
curl -sS "$BASE/api/health/system" | jq '{LOG_ERROR_RATE_PER_MIN,LOG_ERROR_SUPPRESSED_PER_MIN,LOG_ERROR_ALERT,LOG_ERROR_COOLDOWN_S,EVENTS_RATE_PER_MIN,EVENTS_RATE_ALERT,LOGS_RATE_PER_MIN,LOGS_RATE_ALERT}'
```

### 9.2 Endurecer planta ruidosa

```python
app.update_log_level(30)  # WARNING
app.update_log_config(max_bytes=5*1024*1024, backup_count=5)  # 5×5 MiB = 30 MiB techo
```

O env:

```bash
export AUTOMATION_LOG_MAX_BYTES=5242880
export AUTOMATION_LOG_BACKUP_COUNT=5
```

### 9.3 Síntoma: disco del contenedor lleno pero `app.log` pequeño

Buscar: `db/saf/journal.db`, `db/backups/`, volumen PG, logs de **Docker json-file** sin `max-size`. No asumir fallo de `RotatingFileHandler`.

### 9.4 Síntoma: CPU alta + `app.log` rotando sin parar

Buscar el mismo `AttributeError`/`TypeError` repetido (patrón pre-alarma `Buffer.count`, etc.). Mitigar la causa raíz; mientras tanto subir a WARNING no elimina ERRORs del decorator.

---

## 10. Relación con otros documentos

| Documento | Relación |
|---|---|
| `AUDIT_USER_EVENTS.md` | Inventario L3 de la tabla `Events` (quién/qué/cuándo, clasificaciones, residual de sesión) |
| `AUDIT_OPERATIONAL_LOGS.md` | Bitácora L2 (tabla `Logs`, HMI `/operational-logs`, comentarios, watchdog) |
| `docs/Developments_Guide/logs.md` | Guía de usuario (rotación, decorator, API) — esta auditoría añade techos, gaps y CA |
| `AUDIT_BACKEND_PERFORMANCE.md` | BE-OK3 confirma rotación; BE-H4 usa `app.log` como evidencia de 503 |
| `STORE_AND_FORWARD.md` / `PERSISTENCE_FLOW.md` | Caps de journal = “log de durabilidad”, no texto |
| `PERFORMANCE_RUNBOOK.md` | Deriva RSS/OPC/SAF; ampliar con chequeo `logs/` si hay flood ERROR |

---

## 11. Conclusión

La gestión de logs de archivo está **acotada y silenciada bajo error sostenido**: rotación ~40 MiB, `DedupeFilter` 60 s, sin `print` en `@logging_error_handler`, stdout ERROR controlado, y `LOG_ERROR_RATE_PER_MIN` para alertar sin leer el archivo.

La capa **Events (L3)** tiene anti-spam **por dominio** (operador sin debounce; DB boot silencioso; OPC/SAF 60 s) y métrica `EVENTS_RATE_PER_MIN`. El catálogo de mensajes está en `AUDIT_USER_EVENTS.md`.

La retención de **historia PG** y **backups SQLite** permanece deliberadamente fuera del framework (ops/DBA). Stdout del contenedor se acota con el driver Docker documentado en el runbook §6.

**Veredicto operativo:** A+ en L1 y anti-flood de ERROR. L3 Events alineado con Trazabilidad Eterna. Soak de planta (inyección de error 24 h) confirma techo de disco y CPU.
