# Auditoría compacta: logs de runtime, eventos de usuario y bitácora operacional

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI) |
| **Alcance** | L1 `logs/app.log`; L2 tabla `Logs` / `/operational-logs`; L3 tabla `Events` y anti-flood; relación con SAF |
| **Fecha original** | 2026-08-16 (Log Eterno + Trazabilidad Eterna + Bitácora Eterna) |
| **Compactación** | 2026-08-18 |
| **Aislamiento Bulkhead** | 2026-08-25 — Events/Logs por muestra; `set_tag`/`bind_tag` no relanzan IntegrityError |
| **Controles `/performance`** | 2026-08-25 — acciones admin auditan en Events (CA-OPS-04) |
| **Fuentes absorbidas** | `AUDIT_LOGGING`, `AUDIT_USER_EVENTS`, `AUDIT_OPERATIONAL_LOGS` |
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) §4.5, `docs/Developments_Guide/logs.md`, `docs/Users_Guide/OperationalLogs/index.md` |
| **Veredicto** | L1 archivo **A+**. Events **A−** (caja negra industrial; residual idle-timeout / delete user). Bitácora **A+** (CA-OL). Retención PG/backups SQLite = política de planta |
| **Clasificación** | Auditoría operativa · trazabilidad · confidencialidad interna |

---

## 0. Tres capas que se llaman «logs»

| Capa | Qué es | Dónde | ¿Crece sin tope? |
|---|---|---|---|
| **L1 — Runtime** | `logging` Python | `logs/app.log` + rotados | **No** — `RotatingFileHandler` |
| **L2 — Bitácora / comentarios** | Tabla `Logs` (operador, watchdog HMI, comentarios de evento/alarma) | Historiador + journal SAF | **Sí en PG** si planta no retenciona |
| **L3 — Historia industrial** | `TagValue`, `Events`, `AlarmSummary` | Historiador + SAF | Journal **sí** tiene caps; PG **no** se vacía solo |

`LoggerWorker` **no** escribe `app.log`. Su periodo (`logger_period`, default 10 s) es reconnect / backup SQLite / `replicate_once` / OPC. Bajarlo no aumenta líneas L1 salvo CRITICAL de reconnect.

Flag `is_history_logged`: si `False`, engines no persisten L2/L3.

---

## 1. L1 — archivo de runtime (Log Eterno)

### 1.1 Mecanismo

`PyAutomation.__start_logger`: limpia root (evita handlers duplicados); un `RotatingFileHandler` UTF-8; logger `pyautomation` propaga al root **sin** segundo FileHandler.

| Parámetro | Default | Override |
|---|---|---|
| `log_max_bytes` | 10 MiB | Env `AUTOMATION_LOG_MAX_BYTES` → config → API |
| `log_backup_count` | 3 | Env / config / API (enviar juntos con max_bytes) |
| `log_level` | 20 INFO (arranca WARNING hasta `__start_logger`) | 0/10/20/30/40/50 |
| `logger_period` | 10 s | Periodo del worker, no flush de archivo |
| `log_error_cooldown_seconds` | 60 (`0` = off) | API caliente |

Techo L1: `maxBytes × (1 + backupCount)` → **≤ 40 MiB** con defaults.

`update_log_config` actualiza el handler existente; **no** fuerza `doRollover()` inmediato (LOG-M2, aceptable).

### 1.2 Qué no rota el framework

| Artefacto | Rotación | Riesgo |
|---|---|---|
| `logs/app.log*` | Sí | Bajo |
| stdout Docker / gunicorn | Orquestador | `json-file` max-size 10m max-file 3 |
| `db/saf/journal.db` | Caps + GC SENT | Acotado |
| `db/backups/*.db` | Dispara > 1 GiB | Ops debe podar (`find -mtime +14`) |
| Tablas PG | No | DBA / particiones. No `DELETE` masivo desde la app |

### 1.3 Anti-flood L1

Librerías: `urllib3`/`requests`/`peewee` → WARNING; `opcua` → CRITICAL.

`DedupeFilter` (`automation/utils/log_filters.py`): suprime repeticiones `(pathname, lineno, funcName, msg)` durante cooldown. Al reemitir anota `[repeated N times]`. LRU ≤ 1000. Filtro en el **logger** (una decisión por record). `@logging_error_handler` y `validate_types` **solo** `logger.error` — **sin** `print` (LOG-H2 / **LOG-M3 cerrados**; el print bypaseaba el filtro y inundaba 1 Hz en laboratorio multi-edge).

Stdout: `StreamHandler` nivel ERROR, mismo formatter.

Métrica: `LOG_ERROR_RATE_PER_MIN` cuenta **intentos** (incl. suprimidos); `LOG_ERROR_ALERT` si > 5/min.

Error a 1 Hz → **1 línea escrita / 60 s**. Health sigue viendo ~60 intentos/min.

---

## 2. L3 Events — trazabilidad de acciones (Trazabilidad Eterna)

### 2.1 Modelo

Tabla `Events` (`automation/dbmodels/events.py`): `timestamp` UTC; FK `user` **obligatoria**; `message`/`description` varchar 256; `classification`; `priority`/`criticity` 1–5 del emisor (**no** ranking ISA).

Reglas: sin usuario no hay fila; clip 256; **nunca** contraseñas/tokens/cuerpos; persistencia `journal_then_remote` + `on.event`. Comentarios humanos van a `Logs` con FK `event`.

Tres caminos de escritura: `@set_event` (solo si truthy **y** `user=` es `User`); `persist_system_event` / `record_user_session_event` (fail-safe, fallback `system`); sin `user=` → no hay fila. Ese era el hueco de CRUD/tags/máquinas desde HMI.

**Antes no había login/logout en Events. Ahora sí** (`Security`).

### 2.2 Inventario

#### Security

| Acción | `message` | FK | description (patrón) |
|---|---|---|---|
| Login OK | `User logged in` | autenticado | `username=… method=password origin=<ip>` |
| Login fallido | `User login failed` | **`system`** | `username=<reclamado> reason=invalid_credentials origin=` |
| Logout | `User logged out` | sesión | `reason=user-initiated` |
| Toma de sesión | `User logged out` | el usuario | `reason=session_superseded` |
| Alta / clave / rol | `User account created` / `password changed\|reset` / `role updated` | objetivo | `actor=` si difieren |

503 de BD en login **no** genera `LOGIN_FAILED`. Cerrar pestaña / `SESSION_INVALID` **no** genera expiry (no hay idle-timeout). El usuario se resuelve **antes** de borrar el token en logout.

#### Configuration / Control

`Tag created|updated|deleted`; `Alarm created|updated|deleted`; `Machine interval|on_delay|attribute updated`; `System settings updated` (keys, sin secretos).

Control: `Tag value forced` (`from=`/`to=`); ack / ack-all; shelve/unshelve; suppress; OOS/RTS; `Machine switched`. Unshelve automático: `System` / FK `system`. UNACK/RTN de proceso: **AlarmSummary**, no Events. Cambios OPC/DAS: datalogger, no Events.

#### System / Database / OPC UA / SAF

Casi siempre FK `system`. Boot: `System started` **sin** `Database connected`. Outage en caliente: un `DISCONNECTED` + un `RECONNECTED` (fallos de reconnect **resumidos**). OPC fallos cooldown 60 s. SAF backpressure/disk cooldown 60 s. `System stopped` solo parada limpia (`safe_stop`); kill -9 no lo deja.

Controles de `/performance` (usuario real, no `system`): `Worker restarted: …`, `SAF retry requested`, `SAF queue emptied` (criticity 5), `Catalog sync requested`, `Catalog orphans cleaned`, `Derived tags rebuilt`, `Runtime settings updated`. Fallo de restart: `Worker restart failed: …`. Evidencia: `automation/utils/ops_controls.py` → `persist_system_event`; CA-OPS-04 en [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](./AUDIT_NODE_PERFORMANCE_DASHBOARD.md).

Anti-spam: operador **sin** debounce. DB boot silencioso; buffer auditor DB ≤ 8. Tasa `EVENTS_RATE_PER_MIN`; alerta > 30/min.

### 2.3 Qué no va a Events

Lecturas/export CSV; escritura OPC de tag; comentarios (van a `Logs`); bitácora libre (`Logs`); healthcheck/SSL; `GET /users/`; `credentials_are_valid`; cierre de pestaña.

### 2.4 Cómo reconstruir «quién hizo qué»

HMI `/events`: filtro usuario (login fallido → buscar en description, FK `system`); clasificación `Security`; mensaje estable; rango + TZ planta. `priority`/`criticity` no son severidad de proceso.

Login: 200 → LOGIN; 403 creds → LOGIN_FAILED; 503 → silencio identidad. Segundo login: LOGOUT `session_superseded` + LOGIN; HMI vieja 401 `SESSION_SUPERSEDED` (no llama `/logout`).

### 2.5 Residual Events

1. No idle-timeout ni `User session expired` atable en `SESSION_INVALID`.
2. No API de borrado de cuenta → no `User account deleted`.
3. UNACK/RTN en AlarmSummary (anti-spam, a propósito).
4. No se introdujo `EventFactory`/`IUserEvent`: contrato único `persist_system_event` + `@set_event` + helpers de dominio.

Veredicto Events: **A−**.

---

## 3. L2 Bitácora (Bitácora Eterna)

### 3.1 Antes vs ahora

Antes (B): `create_log` devolvía `"Logs DB is not up"` si `is_db_connected()` era falso, aunque el logger tenía journal. La página mezclaba notas, comentarios y `[HMI] heap`. FKs CASCADE. Sin turno/área/relevo ni `on.log`.

Ahora: nota operador `classification = "Operational"`. Vista Bitácora = `General`+`Operational`, excluye `memory-watchdog`. Outage PG **no impide escribir**: façade llama al engine; si no hay conectividad → `JournaledEnvelope` + `journaled: true` + `on.log`.

### 3.2 Modelo `Logs`

`user` nullable `ON DELETE SET NULL`; `user_name` obligatorio en create (sobrevive DELETE); `shift` whitelist morning/afternoon/night; `area` clip 64; `handover` bool. Clip en escritura. `ensure_schema()` añade columnas, backfill `user_name`, índice timestamp; en PostgreSQL reescribe FKs a SET NULL. Serialize: si `user` NULL, HMI ve `user.username` desde `user_name`. Residual: SQLite **legado** no ALTER FK.

El cliente **no** elige la familia. `POST /logs/add` elimina `timestamp`/`classification`/`user` del JSON y llama `classify_write`:

| Condición | classification | Emisor |
|---|---|---|
| `event_id` | `Event` | comentario `/events` |
| `alarm_summary_id` | `Alarm` | comentario `/alarms/summary` |
| `description == memory-watchdog` | `System` | `useMemoryWatchdog` (un POST por cruce de umbral) |
| resto | `Operational` | modal bitácora |

`POST /logs/add` **no** lleva `@require_remote_db` (sí `filter_by` / `lasts`). Deliberado: anotar en outage.

`PersistableRecord.log` es `critical=True`. Replay `_write_logs` **no** hace `continue` si el User no existe; crea con `user_name`.

### 3.3 Lectura HMI

`Logs.filter_by`: classifications IN; search message OR description; `exclude_description` (watchdog); usuario = FK **o** `user_name`.

Vistas: notebook (default) General+Operational − watchdog; comments Event+Alarm; system System. Rango default Last Day 24 h. Limpiar restaura notebook + 24 h. `on.log` refresca. 503 de lectura **no** vacía filas ya mostradas.

### 3.4 CA-OL

| ID | Criterio | Estado |
|---|---|---|
| **CA-OL-1** | Anotar con BD caída y replicar | **Cumple** |
| **CA-OL-2** | Vista default sin Event/Alarm/watchdog | **Cumple** |
| **CA-OL-3** | Búsqueda message OR description | **Cumple** |
| **CA-OL-4** | Turno y área en alta | **Cumple** |
| **CA-OL-5** | Limpiar filtros | **Cumple** |
| **CA-OL-6** | SET NULL + nombre conservado | **Cumple** (SQLite nuevo; legado no ALTER FK) |
| **CA-OL-7** | `LOGS_RATE_PER_MIN` independiente de Events | **Cumple** (alerta 30/min) |
| **CA-OL-8** | Guía = implementación | **Cumple** |

Tests: `test_operational_logs` + `test_audit_metrics` (11 OK en la corrida original). Residual de producto fuera de CA: firma electrónica, PDF 21 CFR.

### 3.1 Bulkhead L2/L3 (2026-08-25)

La replicación SAF de Events y Logs es **por muestra**. Un evento que no inserta (usuario ausente, `IntegrityError`) queda PENDING; el resto del lote y los demás dominios (tags, alarmas) siguen. Evidencia: CA-ISOLATION-01 en [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md).

Hidratación de metadatos: `DataLogger.set_tag` / `MachinesLogger.bind_tag` no relanzan `IntegrityError` (CA-ISOLATION-03/04). Un tag o bind huérfano no corta el resto de la carga.

---

## 4. Anti-spam cruzado y performance

| Dominio | Política |
|---|---|
| CycleSampleCache | mismo tag+ciclo+valor → drop journal (TTL 2 s) |
| DatabaseConnectionAuditor | cap 8; un DISCONNECTED por outage |
| OPC UA | failure cooldown 60 s |
| SAF capacity | Events cooldown 60 s |
| Watchdog HMI | un log por episodio |
| Operador (Events y bitácora) | **sin** debounce |

¿L1 es cuello? Régimen INFO/WARNING: no. DEBUG global: sí (rotación acota disco, no CPU). Excepción 1 Hz: I/O no (dedupe). Outage PG: parcial (auditor acotado + SAF).

---

## 5. Hallazgos L1 (IDs)

| ID | Estado |
|---|---|
| LOG-OK1…OK11 | Rotación, API, filtro único, librerías, auditores, CycleSampleCache, watchdog, DedupeFilter, métricas ERROR/Events/SAF |
| LOG-H1 / H2 / M1 / M3 | **Cerrados** |
| LOG-H3 | Info — stdout Docker documentado |
| LOG-H4 | Info — backups SQLite, poda ops |
| LOG-H5 | Info — TTL PG = DBA |
| LOG-M2 | Bajo — no rollover inmediato |

### CA-LOG

| ID | Criterio |
|---|---|
| **CA-LOG-1** | `du -sb logs/` ≤ techo × 1.1 tras soak 24 h |
| **CA-LOG-2** | Tras > maxBytes existen `app.log.1`… |
| **CA-LOG-3** | `PUT /settings/update` incluye cooldown |
| **CA-LOG-4** | Outage 1 h → Events DB O(1) por fase |
| **CA-LOG-5** | OPC fallos < 60 s no multiplican Events |
| **CA-LOG-6** | CycleSampleCache no incrementa PENDING |
| **CA-LOG-7** | Error 1 Hz → 1 línea / cooldown; `LOG_ERROR_RATE_PER_MIN` cuenta intentos |
| **CA-LOG-8** | `EVENTS_RATE_PER_MIN`; alerta > 30; boot DB silencioso |

---

## 6. Runbook rápido

```bash
ls -lh logs/app.log*
curl -sS -H "X-API-KEY: $TOKEN" "$BASE/api/settings/"
curl -sS "$BASE/api/health/system" | jq '{LOG_ERROR_RATE_PER_MIN,LOG_ERROR_SUPPRESSED_PER_MIN,LOG_ERROR_ALERT,EVENTS_RATE_PER_MIN,EVENTS_RATE_ALERT,LOGS_RATE_PER_MIN,LOGS_RATE_ALERT}'
```

Endurecer: `update_log_level(30)`; techo 5×5 MiB. Soak error controlado: `du logs/` acotado; rate intentos ≈ 60; suppressed ≈ 59; `LOG_ERROR_ALERT=true`.

Verificación planta Events: login/logout/superseded/ack/CRUD tag/force value/intervalo/transición máquina/`System started`/DB disconnect-reconnect.

---

## 7. Archivos clave

| Pieza | Ruta |
|---|---|
| Arranque logger / rotación | `automation/core.py` `__start_logger` |
| Dedupe | `automation/utils/log_filters.py` |
| Decoradores | `automation/utils/decorators.py` |
| Events modelo / logger | `automation/dbmodels/events.py`, `logger/events.py` |
| `persist_system_event` | `automation/utils/system_event_audit.py` |
| Sesión | `automation/utils/user_session_audit.py` |
| Métricas | `automation/utils/audit_metrics.py` |
| DB/OPC/lifecycle audit | `db_audit.py`, `opcua_audit.py`, `system_lifecycle_audit.py` |
| Logs modelo / classify | `dbmodels/logs.py`, `utils/operational_log_audit.py` |
| HTTP logs | `modules/events/resources/logs.py` |
| HTTP users | `modules/users/resources/users.py` |
| HMI Events / Bitácora | `hmi/src/pages/Events.tsx`, `OperationalLogs.tsx` |
| Controles ops | `automation/utils/ops_controls.py` · `POST /api/admin/…` |
| Tests | `test_log_filters`, `test_user_session_audit`, `test_operational_logs`, `test_audit_metrics`, `test_db_connection_audit`, `test_system_lifecycle_audit`, `test_ops_controls` |
