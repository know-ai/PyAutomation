# Auditoría: Fiabilidad operativa (logs, continuidad, misión crítica, caos)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Documento canónico** | 10 / 10 |
| **Fecha de agrupación** | 2026-09-16 |
| **Fuentes absorbidas** | `AUDIT_LOGGING`, `AUDIT_USER_EVENTS`, `AUDIT_OPERATIONAL_LOGS`, `AUDIT_LONG_RUN_CONTINUITY`, `AUDIT_MISSION_CRITICAL`, `CHAOS_LAST_RUN` |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_TIME.md](./AUDIT_TIME.md), [AUDIT_TAGS.md](./AUDIT_TAGS.md) |
| **Veredicto vigente** | Logs: aplicación ≠ eventos; GUI logs pendiente; Loki **C**. Continuidad edge **A−** código / PG **B−**. Misión **A− / B+** código; campaña OT pendiente |
| **Clasificación** | Auditoría de contraste código vs diseño. IDs de hallazgos conservados. |


Este archivo agrupa **todas** las auditorías del dominio. Cada parte conserva el texto original.

## Índice de partes

- [Parte A — Logs, eventos y bitácora](#parte-a-logs-eventos-y-bitácora)
- [Parte B — Continuidad día 1 vs día 1000](#parte-b-continuidad-día-1-vs-día-1000)
- [Parte C — Puntos críticos de misión](#parte-c-puntos-críticos-de-misión)
- [Parte D — Plantilla campaña de caos CT-07](#parte-d-plantilla-campaña-de-caos-ct-07)

---

## Parte A — Logs, eventos y bitácora

> Fuente original: `AUDIT_LOGGING.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI) |
| **Alcance** | L1 `logs/app.log`; L2 tabla `Logs` / `/operational-logs`; L3 tabla `Events` y anti-flood; relación con SAF |
| **Fecha original** | 2026-08-16 (Log Eterno + Trazabilidad Eterna + Bitácora Eterna) |
| **Compactación** | 2026-08-18 |
| **Revisión logs de aplicación** | 2026-08-27 — **Log aplicación ≠ Eventos**; pantalla GUI dedicada; export O(1) (§8) |
| **Aislamiento Bulkhead** | 2026-08-25 — Events/Logs por muestra; `set_tag`/`bind_tag` no relanzan IntegrityError |
| **Controles `/performance`** | 2026-08-25 — acciones admin auditan en Events (CA-OPS-04) |
| **Fuentes absorbidas** | `AUDIT_LOGGING`, `AUDIT_USER_EVENTS`, `AUDIT_OPERATIONAL_LOGS` |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) §4.5, `docs/Developments_Guide/logs.md`, `docs/Users_Guide/OperationalLogs/index.md` |
| **Veredicto** | L1 infra **A+**; **Log aplicación ≠ Eventos** (dominios separados; falta pantalla HMI/runtime). Export store **C**. Eventos **A−** (§2, otro producto UI). Bitácora **A+** |
| **Clasificación** | Auditoría operativa · trazabilidad · confidencialidad interna |

---

### 0. Cuatro cosas distintas — no confundir nombres

En planta se mezclan cuatro conceptos bajo la palabra «log». **Son dominios separados** con responsabilidades distintas:

| ID | Nombre correcto | Qué es | Dónde | Pantalla HMI / GUI |
|---|---|---|---|---|
| **L1** | **Log de aplicación** (runtime) | Salida del módulo `logging` Python: ERROR, WARNING, DEBUG, tracebacks, fallos **no previstos** | `logs/app.log` + stdout Docker | **Pendiente:** `/application-logs` o Grafana/Loki (§8.16) — **no** es `/events` |
| **L2** | **Bitácora operacional** | Comentarios de operador, watchdog memoria HMI | Tabla `Logs` | `/operational-logs` |
| **L3-E** | **Eventos** (auditoría industrial) | Acciones **deliberadas** y de negocio: login, CRUD, socket HMI, SAF, CRUD config | Tabla `Events` | `/events` — **no** es log de aplicación |
| **L3-H** | **Historiador de proceso** | TagValue, AlarmSummary | PG + SAF | Tendencias, alarmas |

> **Regla de oro:** un `AttributeError` en `/api/history/backfill`, un `WARNING` de journal flush o un `CRITICAL` de reconnect **van a L1 (log de aplicación)**. **No** deben aparecer en la tabla `Events` salvo que un auditor explícito decida duplicar un subconjunto (anti-patrón por defecto).

`LoggerWorker` **no** escribe L1. Su periodo (`logger_period`, default 10 s) es reconnect / SAF / OPC — otro concepto más.

Flag `is_history_logged`: si `False`, engines no persisten L2/L3-E/L3-H.

---

### 1. L1 — archivo de runtime (Log Eterno)

#### 1.1 Mecanismo

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

#### 1.2 Qué no rota el framework

| Artefacto | Rotación | Riesgo |
|---|---|---|
| `logs/app.log*` | Sí | Bajo |
| stdout Docker / gunicorn | Orquestador | `json-file` max-size 10m max-file 3 |
| `db/saf/journal.db` | Caps + GC SENT | Acotado |
| `db/backups/*.db` | Dispara > 1 GiB | Ops debe podar (`find -mtime +14`) |
| Tablas PG | No | DBA / particiones. No `DELETE` masivo desde la app |

#### 1.3 Anti-flood L1

Librerías: `urllib3`/`requests`/`peewee` → WARNING; `opcua` → CRITICAL.

`DedupeFilter` (`automation/utils/log_filters.py`): suprime repeticiones `(pathname, lineno, funcName, msg)` durante cooldown. Al reemitir anota `[repeated N times]`. LRU ≤ 1000. Filtro en el **logger** (una decisión por record). `@logging_error_handler` y `validate_types` **solo** `logger.error` — **sin** `print` (LOG-H2 / **LOG-M3 cerrados**; el print bypaseaba el filtro y inundaba 1 Hz en laboratorio multi-edge).

Stdout: `StreamHandler` al **mismo nivel** que el archivo (`log_level` / env `AUTOMATION_LOG_TO_STDOUT=1` en Docker). Mismo formatter; en planta iDetectFugas suele ir todo a stdout del contenedor (`json-file` max 10m×3).

Métrica: `LOG_ERROR_RATE_PER_MIN` cuenta **intentos** (incl. suprimidos); `LOG_ERROR_ALERT` si > 5/min.

Error a 1 Hz → **1 línea escrita / 60 s**. Health sigue viendo ~60 intentos/min.

---

### 2. L3-E Eventos — trazabilidad de acciones (Trazabilidad Eterna)

> **No es log de aplicación.** Eventos registran acciones **modeladas** con contrato explícito (`@set_event`, auditores). Los ERROR/WARNING/tracebacks imprevistos del runtime van a **L1** (§1, §8) y a la pantalla **Log de aplicación** (§8.16), no a esta tabla.

#### 2.1 Modelo

Tabla `Events` (`automation/dbmodels/events.py`): `timestamp` UTC; FK `user` **obligatoria**; `message`/`description` varchar 256; `classification`; `priority`/`criticity` 1–5 del emisor (**no** ranking ISA).

Reglas: sin usuario no hay fila; clip 256; **nunca** contraseñas/tokens/cuerpos; persistencia `journal_then_remote` + `on.event`. Comentarios humanos van a `Logs` con FK `event`.

Tres caminos de escritura: `@set_event` (solo si truthy **y** `user=` es `User`); `persist_system_event` / `record_user_session_event` (fail-safe, fallback `system`); sin `user=` → no hay fila. Ese era el hueco de CRUD/tags/máquinas desde HMI.

**Antes no había login/logout en Events. Ahora sí** (`Security`).

#### 2.2 Inventario

##### Security

| Acción | `message` | FK | description (patrón) |
|---|---|---|---|
| Login OK | `User logged in` | autenticado | `username=… method=password origin=<ip>` |
| Login fallido | `User login failed` | **`system`** | `username=<reclamado> reason=invalid_credentials origin=` |
| Logout | `User logged out` | sesión | `reason=user-initiated` |
| Toma de sesión | `User logged out` | el usuario | `reason=session_superseded` |
| Alta / clave / rol | `User account created` / `password changed\|reset` / `role updated` | objetivo | `actor=` si difieren |

503 de BD en login **no** genera `LOGIN_FAILED`. Cerrar pestaña / `SESSION_INVALID` **no** genera expiry (no hay idle-timeout). El usuario se resuelve **antes** de borrar el token en logout.

##### Configuration / Control

`Tag created|updated|deleted`; `Alarm created|updated|deleted`; `Machine interval|on_delay|attribute updated`; `System settings updated` (keys, sin secretos).

Control: `Tag value forced` (`from=`/`to=`); ack / ack-all; shelve/unshelve; suppress; OOS/RTS; `Machine switched`. Unshelve automático: `System` / FK `system`. UNACK/RTN de proceso: **AlarmSummary**, no Events. Cambios OPC/DAS: datalogger, no Events.

##### System / Database / OPC UA / SAF

Casi siempre FK `system`. Boot: `System started` **sin** `Database connected`. Outage en caliente: un `DISCONNECTED` + un `RECONNECTED` (fallos de reconnect **resumidos**). OPC fallos cooldown 60 s. SAF backpressure/disk cooldown 60 s. `System stopped` solo parada limpia (`safe_stop`); kill -9 no lo deja.

Controles de `/performance` (usuario real, no `system`): `Worker restarted: …`, `SAF retry requested`, `SAF queue emptied` (criticity 5), `Catalog sync requested`, `Catalog orphans cleaned`, `Derived tags rebuilt`, `Runtime settings updated`. Fallo de restart: `Worker restart failed: …`. Evidencia: `automation/utils/ops_controls.py` → `persist_system_event`; CA-OPS-04 en [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md).

Anti-spam: operador **sin** debounce. DB boot silencioso; buffer auditor DB ≤ 8. Tasa `EVENTS_RATE_PER_MIN`; alerta > 30/min.

#### 2.3 Qué no va a Events

Lecturas/export CSV; escritura OPC de tag; comentarios (van a `Logs`); bitácora libre (`Logs`); healthcheck/SSL; `GET /users/`; `credentials_are_valid`; cierre de pestaña.

#### 2.4 Cómo reconstruir «quién hizo qué»

HMI `/events`: filtro usuario (login fallido → buscar en description, FK `system`); clasificación `Security`; mensaje estable; rango + TZ planta. `priority`/`criticity` no son severidad de proceso.

Login: 200 → LOGIN; 403 creds → LOGIN_FAILED; 503 → silencio identidad. Segundo login: LOGOUT `session_superseded` + LOGIN; HMI vieja 401 `SESSION_SUPERSEDED` (no llama `/logout`).

#### 2.5 Residual Events

1. No idle-timeout ni `User session expired` atable en `SESSION_INVALID`.
2. No API de borrado de cuenta → no `User account deleted`.
3. UNACK/RTN en AlarmSummary (anti-spam, a propósito).
4. No se introdujo `EventFactory`/`IUserEvent`: contrato único `persist_system_event` + `@set_event` + helpers de dominio.

Veredicto Events: **A−**.

---

### 3. L2 Bitácora (Bitácora Eterna)

#### 3.1 Antes vs ahora

Antes (B): `create_log` devolvía `"Logs DB is not up"` si `is_db_connected()` era falso, aunque el logger tenía journal. La página mezclaba notas, comentarios y `[HMI] heap`. FKs CASCADE. Sin turno/área/relevo ni `on.log`.

Ahora: nota operador `classification = "Operational"`. Vista Bitácora = `General`+`Operational`, excluye `memory-watchdog`. Outage PG **no impide escribir**: façade llama al engine; si no hay conectividad → `JournaledEnvelope` + `journaled: true` + `on.log`.

#### 3.2 Modelo `Logs`

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

#### 3.3 Lectura HMI

`Logs.filter_by`: classifications IN; search message OR description; `exclude_description` (watchdog); usuario = FK **o** `user_name`.

Vistas: notebook (default) General+Operational − watchdog; comments Event+Alarm; system System. Rango default Last Day 24 h. Limpiar restaura notebook + 24 h. `on.log` refresca. 503 de lectura **no** vacía filas ya mostradas.

#### 3.4 CA-OL

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

#### 3.1 Bulkhead L2/L3 (2026-08-25)

La replicación SAF de Events y Logs es **por muestra**. Un evento que no inserta (usuario ausente, `IntegrityError`) queda PENDING; el resto del lote y los demás dominios (tags, alarmas) siguen. Evidencia: CA-ISOLATION-01 en [AUDIT_DB.md](./AUDIT_DB.md).

Hidratación de metadatos: `DataLogger.set_tag` / `MachinesLogger.bind_tag` no relanzan `IntegrityError` (CA-ISOLATION-03/04). Un tag o bind huérfano no corta el resto de la carga.

---

### 4. Anti-spam cruzado y performance

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

### 5. Hallazgos L1 (IDs)

| ID | Estado |
|---|---|
| LOG-OK1…OK11 | Rotación, API, filtro único, librerías, auditores, CycleSampleCache, watchdog, DedupeFilter, métricas ERROR/Events/SAF |
| LOG-H1 / H2 / M1 / M3 | **Cerrados** |
| LOG-H3 | Info — stdout Docker documentado |
| LOG-H4 | Info — backups SQLite, poda ops |
| LOG-H5 | Info — TTL PG = DBA |
| LOG-M2 | Bajo — no rollover inmediato |

#### CA-LOG

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

### 7. Archivos clave

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
| Bitácora HTTP (L2) | `modules/events/resources/logs.py` |
| HTTP users / login audit | `modules/users/resources/users.py`, `utils/user_session_audit.py` |
| Contadores HTTP (sin access log) | `utils/http_metrics.py` |
| Export GUI (estándar sidecar) | §8.12–§8.19; backlog LOG-EXP-* |
| Socket.IO lifecycle audit | `utils/hmi_socket_audit.py` |
| TLS cliente (debounced Events) | `utils/hmi_tls_telemetry.py`, `utils/gevent_tls_quiet.py` |
| Gunicorn worker hooks | `gunicorn.conf.py` `post_worker_init` |
| Settings API log | `modules/settings/resources/settings.py` |
| HMI Events / Bitácora | `hmi/src/pages/Events.tsx`, `OperationalLogs.tsx` |
| Controles ops | `automation/utils/ops_controls.py` · `POST /api/admin/…` |
| Tests | `test_log_filters`, `test_user_session_audit`, `test_operational_logs`, `test_audit_metrics`, `test_db_connection_audit`, `test_system_lifecycle_audit`, `test_ops_controls`, `test_hmi_session_store`, `test_hmi_tls_telemetry` |

---

### 8. Auditoría — estrategia de logs de **aplicación** (no persistencia de datos)

> **Alcance §8:** exclusivamente el **log de aplicación (L1)** — diagnóstico técnico, errores imprevistos, access HTTP. **No** es la tabla **Eventos** (§2), **no** es bitácora (§3), **no** es historiador TagValue.

#### 8.1 Pregunta de auditoría

¿Puede mantenimiento ver en una **interfaz gráfica dedicada** (no la pantalla Eventos) los ERROR/WARNING/tracebacks del runtime — incluidos fallos **no previstos** que nunca pasaron por `@set_event` — con IP en access log, niveles DEBUG→CRITICAL, y sin abrir Docker/terminal?

#### 8.2 Separación estricta: Log de aplicación ≠ Eventos

| Criterio | **Log de aplicación (L1)** | **Eventos (L3-E)** |
|---|---|---|
| **Propósito** | Diagnóstico técnico, bugs, I/O, workers, excepciones Flask | Trazabilidad industrial «quién hizo qué» |
| **Origen** | `logging.getLogger("pyautomation")`, Flask, `@logging_error_handler` | `@set_event`, `persist_system_event`, auditores de dominio |
| **Contenido típico** | `Exception on /api/…`, SAF flush failed, OPC timeout, dedupe `[repeated N times]` | `User logged in`, `Tag created`, `HMI client connected` |
| **¿Imprevistos?** | **Sí** — aquí vive lo no modelado | **No** — solo acciones con contrato explícito |
| **Persistencia** | Archivo rotado + (objetivo) store Loki vía sidecar | Tabla `Events` + SAF → PG |
| **Pantalla** | **Nueva:** «Log de aplicación» o consola Loki/Grafana | **Existente:** HMI `/events` |
| **¿Mezclar en una sola UI?** | **No** — confunde operador de proceso con mantenimiento | Eventos quedan para auditoría humana |

**Ejemplo real (pre-prod 2026-08-27):** `AttributeError: 'DataLoggerEngine' object has no attribute 'read_backfill'` en `GET /api/history/backfill` → **solo L1** (y contador HTTP 5xx). **No** hay fila en Eventos porque nadie llamó a `persist_system_event`. Eso es correcto: es un bug de código, no una acción de operador.

**Anti-patrones prohibidos:**

1. Volcar todo `logger.error` a la tabla `Events` — inundaría L3-E y mezcla responsabilidades.
2. Usar `/events` como sustituto del log de aplicación — el operador no ve tracebacks ni DEBUG.
3. Duplicar en L1 lo que ya está bien modelado en Eventos (login, socket) salvo modo DEBUG explícito (`AUTOMATION_LOG_SOCKET_L1=1`).

#### 8.3 Modelo de planos (L1 vs L3-E)

| Plano | Destino | Qué captura | Fortaleza | Debilidad |
|---|---|---|---|---|
| **L1 — Log de aplicación** | `app.log` + stdout | Excepciones, I/O, workers, warnings no auditados | Rotación, dedupe ERROR | Sin GUI HMI hoy; sin access log completo |
| **L3-E — Eventos** | Tabla `Events` + `/events` | Login, socket HMI, CRUD, SAF resumido | Contrato industrial, IP en description | **No** captura bugs imprevistos |

**Conclusión:** Eventos cumplen auditoría de **acciones**. El **log de aplicación** cumple **salud técnica y bugs**. Faltan access log L1 (LOG-ACC-*) y **pantalla/consola propia** para L1 (LOG-GUI-* / LOG-EXP-*).

#### 8.4 Niveles del log de aplicación (contrato DEBUG → CRITICAL)

| Nivel | Valor | Uso en PyAutomationIO | Configuración |
|---|---|---|---|
| DEBUG | 10 | OPC skip, mirrors catálogo, hidratación socket, paths degradados | Solo diagnóstico; rotación acota disco; puede ser verboso en CPU |
| INFO | 20 | Arranque, reconexiones resumidas, cambios de nivel | **Default persistido** tras `__start_logger` |
| WARNING | 30 | Historiador caído, SAF backpressure, bind rechazado | Régimen operación estable |
| ERROR | 40 | Flush journal, socket audit fallido, `@logging_error_handler` | Dedupe 60 s default |
| CRITICAL | 50 | Recycle worker hub-lag, reconnect DB, tokens OPC | Siempre visible; librería `opcua` capada aquí |

**API / config:** `PUT /api/settings/update` con `log_level`, `log_max_bytes`+`log_backup_count`, `log_error_cooldown_seconds`. Env: `AUTOMATION_LOG_MAX_BYTES`, `AUTOMATION_LOG_BACKUP_COUNT`, `AUTOMATION_LOG_ERROR_COOLDOWN_SECONDS`, `AUTOMATION_LOG_FILE`, `AUTOMATION_LOG_TO_STDOUT`.

**Logger canónico:** `logging.getLogger("pyautomation")`. Sub-loggers permitidos: `pyautomation.metrics`, `pyautomation.<dominio>` — **propagan al root** (un solo `RotatingFileHandler`).

**Formato actual L1:** `%(asctime)s:%(levelname)s:%(message)s` — sin módulo, hilo ni `request_id` (ver backlog LOG-ACC-3).

#### 8.5 HTTP REST — estado actual vs requisito nuclear

| Requisito | Implementación | Evidencia | Veredicto |
|---|---|---|---|
| Contar peticiones O(1) | `install_http_metrics` → `HTTP_REQUESTS_*`, `HTTP_5XX_*` en `/health/system` | `utils/http_metrics.py`, hook en `define_socketio` | **A** rendimiento |
| **Línea por petición** method + path + status + IP | **No existe** en L1 | Solo contadores; Flask/Werkzeug no configurado; gunicorn sin `accesslog` | **F gap** |
| IP del cliente | Helper `request_origin()` — **solo** auditores Events (login, etc.) | `system_event_audit.py` respeta `X-Forwarded-For` | **A** donde se usa; **C** cobertura |
| Usuario autenticado en log | Login/logout → Events `username=` + `origin=` | `user_session_audit.py` | **B** — no en access log general |
| Secretos fuera del log | Tokens nunca en message; clip 256 en Events | `hmi_socket_audit`, `Api.token_required` | **A+** |
| Errores 5xx trazables | Flask log + `@logging_error_handler`; contador 5xx | Traceback en L1 para excepciones no capturadas | **B+** — sin correlación request↔error |

**Qué sí genera línea L1 hoy:** excepciones no manejadas (p. ej. el `AttributeError` en `/api/history/backfill`), warnings de workers, CRITICAL de lifecycle. **Qué no:** `GET /api/health/system`, `POST /api/tags/…`, export CSV, etc.

#### 8.6 Socket.IO — dónde va cada cosa (Eventos ≠ log aplicación)

El ciclo de vida Socket HMI es **Evento de negocio** (conexión de operador), no diagnóstico de runtime. **Pertenece a `/events`**, no a la pantalla de log de aplicación.

| Evento | Log aplicación (L1) | Eventos (L3-E) `/events` | IP |
|---|---|---|---|
| Connect OK | No (salvo warning store degradado) | `HMI client connected` | `origin=` |
| Reconnect | Idem | `HMI client reconnected` | Sí |
| Disconnect | No | `HMI client disconnected` | Sí |
| Token inválido | No | `HMI client connection rejected` | Sí |
| TLS handshake fallido | No (suprimido gevent) | `HMI TLS handshake failure` (debounced) | Sí |
| Heartbeat Engine.IO | No | No (deliberado) | — |
| Bug en fanout `on.tag` | **Sí** — traceback L1 | No (salvo auditor explícito) | — |

Detalle Eventos socket: [AUDIT_HMI.md](./AUDIT_HMI.md).

#### 8.7 Matriz «clase mundial» (solo log de aplicación)

| Dimensión | Nota | Comentario |
|---|---|---|
| **Eficiente** | **A** | Hot path HTTP = contador O(1); dedupe ERROR; librerías silenciadas |
| **Trazable (bugs imprevistos)** | **B−** | L1 captura excepciones; **sin pantalla** dedicada; Eventos no sustituyen |
| **Segura** | **A** | Sin tokens/contraseñas; IP clip; system user restringido por path |
| **Robusta** | **A** | Fail-safe auditores (`never raises`); logging no bloquea auth/socket |
| **Confiable / acotada** | **A+** | Rotación + techo disco + métricas de deriva |
| **Configurable** | **A** | API + env + `db/app_config.json` heredado por productos |
| **Herencia multi-producto** | **B+** | Contrato claro en código; falta spec formal, access log y export JSON |

**Veredicto global log de aplicación:** **B+** — infra madura; brechas = access log L1 + **pantalla GUI propia** (LOG-GUI-*) + export store (LOG-EXP-*).

#### 8.8 Herencia — PyAutomationIO → iDetectFugas (y cualquier producto)

```
PyAutomation.safe_start()
  └─ __start_logger()          ← único punto de verdad L1
       ├─ RotatingFileHandler / stdout
       ├─ DedupeFilter
       └─ niveles librerías

CreateApp() (producto)
  └─ server = automation.server   ← mismo Flask
  └─ modules.init_app(server)     ← namespaces REST del dominio

Producto (iDetectFugas)
  ├─ from automation import PyAutomation
  ├─ app = PyAutomation()         ← singleton comparte logger
  ├─ logging.getLogger("pyautomation")  ← OBLIGATORIO para logs visibles
  └─ compose: AUTOMATION_LOG_TO_STDOUT=1   ← sidecar tail → Loki (§8.12)
```

**Reglas para aplicaciones hijas:**

1. **No** configurar `logging.basicConfig` ni segundo `FileHandler` en el producto — compite con el root y duplica o pierde dedupe.
2. **No** loguear PII/secretos; usar el mismo clip que Events si hace falta contexto.
3. Nivel, rotación y formato JSON: vía env / `PUT /api/settings/update` — el producto **no** implementa export (sidecar ops).
4. Auditores de dominio (LDS/PFM): acciones de operador → **Eventos**; fallos técnicos → **`logging.getLogger("pyautomation")`** (L1).
5. Tras cambios en PyAutomationIO, redeploy wheel — el venv de planta **no** es editable.

#### 8.11 Consola operativa gráfica — requisito nuclear

El operador de planta y mantenimiento **no debe depender** de `docker logs`, SSH ni `grep` en el edge para vigilar la aplicación. El estándar exige:

| Requisito | Significado |
|---|---|
| **Vista unificada** | L1 runtime + (opcional) Events L3 auditables en una UI operativa (p. ej. Grafana Explore) |
| **Tiempo casi real** | Retraso ingestión → pantalla **≤ 5 s** (P95) en régimen normal |
| **Hot path intacto** | Emitir un log **nunca** espera red, disco remoto ni indexación |
| **Escala 1 → 100 M** | Insertar, exportar y consultar con coste **acotado por ventana/reciente**, no por tamaño total del historial |
| **Herencia** | iDetectFugas y cualquier producto PyAutomationIO heredan el mismo contrato sin código de export en la app |

**Principio de separación:** la aplicación **produce**; un **sidecar** o agente del host **transporta**; una **plataforma central** **indexa y sirve** la UI. Consultar 100 M de filas **nunca** ocurre dentro del worker gunicorn.

#### 8.12 Arquitectura de referencia (patrón sidecar)

```
┌─────────────────────────────────────────────────────────────────┐
│  Edge (NUC / contenedor idetectfugas)                           │
│                                                                 │
│  ┌──────────────────────┐      ┌─────────────────────────────┐  │
│  │ PyAutomationIO       │      │ Agente sidecar (Vector /    │  │
│  │ gunicorn + gevent    │      │ Alloy / Fluent Bit)         │  │
│  │                      │      │                             │  │
│  │ __start_logger()     │      │ • tail stdout json-file     │  │
│  │  → stdout JSON Lines │─────▶│ • parse + enrich labels     │  │
│  │  → (opc.) app.log    │      │ • batch async → Loki/OTLP   │  │
│  │                      │      │ • cola acotada + drop policy│  │
│  │ O(1) emit: append    │      │ O(1) export: por línea nueva│  │
│  └──────────────────────┘      └──────────────┬──────────────┘  │
│                                                 │ TLS / LAN       │
└─────────────────────────────────────────────────┼─────────────────┘
                                                  ▼
                        ┌─────────────────────────────────────┐
                        │ Plataforma central (hub / SOC)        │
                        │  Loki │ OpenSearch │ Graylog │ Splunk │
                        │  índice por tiempo + labels (no full  │
                        │  scan en edge)                        │
                        └──────────────────┬────────────────────┘
                                           ▼
                        ┌─────────────────────────────────────┐
                        │ GUI operativa — Grafana Explore /     │
                        │ Kibana / consola corporativa          │
                        │ • tail en vivo • filtros • alertas    │
                        │ • consulta siempre acotada en tiempo  │
                        └─────────────────────────────────────┘

Plano paralelo L3 (auditoría humana):
  Events / Logs (PG) ──▶ HMI /events + (opc.) datasource Grafana PG
  No mezclar con el hot path L1; unificar solo en la UI de planta.
```

**Estado planta iDetectFugas hoy:** `compose/docker-compose.yml` ya usa `logging: driver: json-file` (max-size 10m × 3). Eso **prepara** el sidecar, pero **no** hay agente ni store central documentado → operador sigue en terminal.

**Recomendación nuclear-industrial (edge ligero):** **Loki + Grafana** (indexación por labels/stream, bajo footprint) + **Vector** o **Grafana Alloy** como sidecar. OpenSearch/Splunk válidos en hub con más RAM.

#### 8.13 Contrato O(1) — insertar, exportar, consultar

| Fase | Dónde | Complejidad exigida | Mecanismo estándar | Anti-patrón (prohibido) |
|---|---|---|---|---|
| **Insertar (emit)** | Proceso app | **O(1)** por registro | `logging` → stdout o archivo; opcional `QueueHandler` + hilo writer; `DedupeFilter` LRU acotado | HTTP/OTLP síncrono desde handler de request; `flush()` en cada línea |
| **Exportar (ship)** | Sidecar / host | **O(1)** por línea **nueva** | Tail `json-file` Docker o pipe stdout; batch 100–1000 líneas / 1 s; backpressure = drop/muestra, **nunca** bloquear app | Releer `app.log` entero cada N s; API REST en app que lea el fichero |
| **Consultar (query)** | Plataforma + GUI | **O(1)** respecto al total histórico | Query **obligatoriamente** acotada: `{last 15m|1h|24h}` + labels `{node_id, area, level}`; índice temporal | `GET /api/logs?all=true`; `SELECT * FROM logs` sin rango; WebSocket desde gunicorn con tail del fichero |
| **Tiempo real (UI)** | GUI ← store | **O(1)** en edge | Grafana Live / tail Loki (`query_range` + refresh); suscripción en **querier**, no en worker OPC | Socket.IO `on.log_line` desde PyAutomation |

**Interpretación «1 vs 1 M vs 100 M registros»:**

- **Insertar:** siempre coste de **una** escritura en buffer/archivo — independiente del historial acumulado en el store central.
- **Exportar:** el sidecar solo procesa **delta** (tail); no escanea 100 M en el edge.
- **Consultar:** el operador **nunca** pide «todo»; la UI exige ventana temporal + filtros. El store (Loki) resuelve por stream+tiempo en O(log T) sobre la ventana, no O(N) global en la app.

#### 8.14 Formato de exportación — JSON Lines + labels

Contrato **LOG-EXP-FMT** (una línea UTF-8 = un evento):

```json
{
  "ts": "2026-08-27T15:21:08.428Z",
  "level": "ERROR",
  "logger": "pyautomation",
  "msg": "Exception on /api/history/backfill [GET]",
  "node_id": "edge-linea1",
  "area": "Linea1",
  "site": "Planta",
  "request_id": "a1b2c3d4",
  "origin": "192.168.1.50",
  "http_method": "GET",
  "http_path": "/api/history/backfill",
  "http_status": 500,
  "duration_ms": 12,
  "classification": "runtime"
}
```

| Campo | Obligatorio | Uso en GUI |
|---|---|---|
| `ts` | Sí | Eje temporal, alertas |
| `level` | Sí | Filtro DEBUG…CRITICAL |
| `msg` | Sí | Cuerpo searchable |
| `node_id`, `area`, `site` | Sí en multi-edge | Labels Loki `{node_id="…"}` |
| `request_id` | Recomendado | Correlación error ↔ access (LOG-ACC-3) |
| `origin` | En HTTP/Socket | IP cliente |
| `http_*`, `duration_ms` | En access log | Tablas operativas |

**Labels Loki (baja cardinalidad):** `node_id`, `area`, `level`, `logger`, `classification`. **No** usar `msg` ni `request_id` como label (alta cardinalidad).

**Activación en app (backlog):** `AUTOMATION_LOG_FORMAT=json` → `JsonFormatter` en `__start_logger`; texto plano actual queda como fallback.

#### 8.15 Tres pantallas — responsabilidades separadas (no unificar)

| Pantalla | Fuente de datos | Usuario típico | Contenido |
|---|---|---|---|
| **`/events`** | Tabla `Events` (PG) | Operador / supervisor | Acciones: login, CRUD, socket HMI, SAF resumido |
| **`/operational-logs`** | Tabla `Logs` (PG) | Operador de turno | Bitácora y comentarios |
| **`/application-logs`** *(pendiente)* o Grafana Loki | **Log de aplicación L1** vía store | Mantenimiento / ingeniería | ERROR, WARNING, tracebacks, access HTTP, DEBUG |

**No** mezclar filas de Eventos en la pantalla de log de aplicación ni viceversa. Son productos de datos distintos. Un menú de planta puede agruparlas visualmente (p. ej. sección «Diagnóstico»), pero cada vista consulta **su propio backend**.

Lo que **debe** verse en la pantalla de log de aplicación y **hoy solo está en L1/Docker**:

- Excepciones Flask no previstas (`Exception on /api/…`)
- `@logging_error_handler` y warnings de workers (SAF, OPC, historiador)
- Access log HTTP (LOG-ACC-1) con IP
- DEBUG bajo demanda (nivel 10 en caliente)

Lo que **permanece en Eventos** (no replicar como log de aplicación salvo DEBUG opcional):

- Login / logout / sesión
- Conexión / desconexión Socket HMI
- CRUD tags, alarmas, máquinas

#### 8.16 Pantalla HMI «Log de aplicación» — diseño propuesto (LOG-GUI)

Análoga en **UX** a `Events.tsx` (filtros, rango temporal, tabla, auto-refresh), pero **distinta en datos**:

```
┌─────────────────────────────────────────────────────────┐
│  Log de aplicación                    [Live ●] [Nivel ▼]│
├─────────────────────────────────────────────────────────┤
│  Rango: Last 1h  │  Nivel: ERROR+WARNING  │  Buscar…   │
├──────────┬────────┬──────────────────────────────────────┤
│ Hora UTC │ Nivel  │ Mensaje / detalle                    │
│ 15:21:08 │ ERROR  │ Exception on /api/history/backfill … │
│ 15:20:01 │ WARNING│ SAF journal flush slow elapsed_s=2.1 │
└──────────┴────────┴──────────────────────────────────────┘
```

| Aspecto | Eventos (`/events`) | Log de aplicación (`/application-logs`) |
|---|---|---|
| API backend | `POST /api/events/filter_by` | **`GET /api/application-logs/query`** → Loki/store (no tabla Events) |
| Modelo fila | `message`, `user`, `classification` | `level`, `msg`, `logger`, `http_path`, stack opcional |
| Tiempo real | `on.event` (opcional) | Poll 2–5 s o SSE desde **querier**, no desde gunicorn hot path |
| Roles | Operador+ | **Mantenimiento / admin / supervisor** |
| Imprevistos | No | **Sí — caso de uso principal** |

**Backlog LOG-GUI:**

| ID | Entrega |
|---|---|
| **LOG-GUI-1** | Página HMI `ApplicationLogs.tsx` + entrada menú «Diagnóstico → Log de aplicación» |
| **LOG-GUI-2** | API read-only `GET /api/application-logs/query?from=&to=&level=&q=` — proxy a Loki (ventana acotada, O(1) en edge) |
| **LOG-GUI-3** | Badge/header opcional: `LOG_ERROR_ALERT` → enlace directo a pantalla filtrada ERROR última 1 h |
| **LOG-GUI-4** | Tests: CA-GUI-1 — fila Eventos **no** aparece en query application-logs |

**Alternativa sin HMI:** Grafana Explore dedicado datasource Loki `{job="pyautomation"}` — mismo contrato de datos, otra UI. La pantalla HMI integra operadores que no tienen Grafana.

#### 8.17 Estado actual vs estándar export + GUI log aplicación

| Capacidad | Hoy | Estándar | Gap |
|---|---|---|---|
| Salida capturable | stdout + `json-file` Docker | Igual + JSON Lines | Formato texto; sin labels de nodo |
| Agente sidecar | **No** en repo compose | Vector/Alloy en compose hub | LOG-EXP-2 |
| Store + GUI | **No** documentado | Loki + Grafana | LOG-EXP-3 |
| Query desde app | **No** (correcto) | Sigue prohibido | — |
| Alertas sobre logs | `LOG_ERROR_ALERT` en `/health` | Grafana alert + métrica derivada | Complementario |
| Pantalla HMI log aplicación | **No** — solo `/events` (otro dominio) | `/application-logs` + LOG-GUI-* | **Gap P0** |
| Tiempo real sin terminal | **No** | Loki tail o HMI live poll | LOG-EXP-* + LOG-GUI-* |

**Veredicto export GUI:** **C** — infraestructura de captura local lista; falta pipeline declarado y formato estructurado.

#### 8.18 Backlog — export store (LOG-EXP)

| ID | Prioridad | Entrega | CA |
|---|---|---|---|
| **LOG-EXP-1** | P0 | `JsonFormatter` + env `AUTOMATION_LOG_FORMAT=json`; labels `node_id`/`area`/`site` | CA-EXP-1: línea parseable `jq` |
| **LOG-EXP-2** | P0 | Sidecar Vector/Alloy → Loki; **cero** código en app | CA-EXP-2: store alimenta GUI |
| **LOG-EXP-3** | P1 | Dashboard Grafana **solo log de aplicación** (ERROR/WARNING/access) — **sin** Eventos | CA-EXP-3: filtros `level` + `node_id` |
| **LOG-EXP-4** | P1 | Backpressure sidecar cola ≤10 MB | CA-EXP-4: store caído → app OK |
| **LOG-EXP-5** | P2 | Runbook `docs/log-export-runbook.md` | CA-EXP-5: ops sin SSH |

Co-requisito pantalla HMI: **LOG-GUI-*** (§8.16). LOG-EXP alimenta Grafana y `/application-logs`.

#### 8.19 CA de aceptación — export + GUI log aplicación

| ID | Criterio | Estado |
|---|---|---|
| **CA-EXP-1** | Emit L1 = O(1); p99 emit no crece con tamaño del store central | **Cumple** (logging stdlib); JSON pendiente |
| **CA-EXP-2** | Export sidecar = O(1) por línea nueva; no relee fichero completo | **Pendiente** (sidecar) |
| **CA-EXP-3** | Query GUI acotada en tiempo; prohibido API «todo el log» en app | **Cumple** (no existe API); falta GUI |
| **CA-EXP-4** | Store caído: app y OPC siguen; sidecar degrada sin bloquear | **Pendiente** |
| **CA-EXP-5** | iDetectFugas hereda JSON + compose sin módulo propio de export | **Parcial** (stdout sí; JSON no) |
| **CA-EXP-6** | Retraso tail GUI ≤5 s P95 | **Pendiente** |
| **CA-GUI-1** | Pantalla log aplicación **no** muestra filas de tabla Events | **Pendiente** |
| **CA-GUI-2** | ERROR/WARNING imprevisto visible en GUI sin Docker | **Pendiente** |

#### 8.20 Runbook — log de aplicación en GUI (objetivo post LOG-EXP + LOG-GUI)

```text
Mantenimiento — bugs / errores imprevistos (NO usar /events):
  1. HMI → Diagnóstico → Log de aplicación
     — o Grafana Explore → Loki (mismo store)
  2. Filtro: level=ERROR|WARNING, last 1h, node_id=edge-linea1
  3. Live tail ON — ver tracebacks, access 5xx, dedupe [repeated N times]

Supervisor — acciones de operador (NO usar log de aplicación):
  1. HMI → Eventos — login, CRUD, socket HMI

Sidecar caído:
  • /health/system → LOG_ERROR_ALERT, LOG_ERROR_RATE_PER_MIN
  • Fallback temporal: §8.22 forense terminal (solo emergencia)
```

#### 8.21 Backlog — access log HTTP (LOG-ACC)

| ID | Prioridad | Entrega | Criterio de aceptación |
|---|---|---|---|
| **LOG-ACC-1** | P0 | `AccessLogMiddleware` Flask: 1 línea INFO por petición `method path status duration_ms origin=` | CA-ACC-1: 100 GET `/api/health` → 100 líneas; IP visible tras proxy |
| **LOG-ACC-2** | P0 | Excluir ruido: `/static`, `/hmi/assets`, health probe opcional, Socket.IO long-poll | CA-ACC-2: soak RT HMI no multiplica líneas > umbral |
| **LOG-ACC-3** | P1 | `request_id` (UUID corto) en contexto + formatter L1 | CA-ACC-3: error 500 muestra mismo id en L1 y respuesta header |
| **LOG-ACC-4** | P1 | Mirror opcional DEBUG: Socket connect/disconnect en L1 (`AUTOMATION_LOG_SOCKET_L1=1`) | CA-ACC-4: grep `app.log` encuentra sid sin consultar Events |
| **LOG-ACC-5** | P2 | Spec `specs/12-APPLICATION-LOGGING.md` + tests CA-ACC | Herencia documentada; iDetectFugas sin config extra |

Ver también backlog export §8.18 (LOG-EXP-*).

**Implementación sugerida LOG-ACC-1:** módulo `automation/utils/access_log.py`; campos alineados con **LOG-EXP-FMT** (§8.14); alimenta **log de aplicación**, no Eventos.

#### 8.23 CA de aceptación — access log (pendiente implementación)

| ID | Criterio | Estado |
|---|---|---|
| **CA-ACC-1** | Toda petición REST (excepto exclusiones §8.21) deja traza con IP en **L1/GUI log aplicación** | **Pendiente** |
| **CA-ACC-2** | Socket lifecycle en **Eventos**; mirror L1 solo con `AUTOMATION_LOG_SOCKET_L1=1` | **Parcial** |
| **CA-ACC-3** | Nivel DEBUG activable en caliente sin reinicio | **Cumple** (`update_log_level`) |
| **CA-ACC-4** | Producto hijo hereda config sin código duplicado | **Cumple** (iDetectFugas + env) |
| **CA-ACC-5** | Soak 24 h: `du logs/` acotado con access log INFO | **Pendiente** |

#### 8.22 Runbook forense — terminal (solo emergencia; no sustituye GUI log aplicación)

```bash
# L1 — excepciones y workers
grep -E 'ERROR|CRITICAL|Exception on' logs/app.log | tail -50

# L3 — sesiones HMI + IP (requiere API token)
curl -sS -H "X-API-KEY: $TOKEN" "$BASE/api/events/filter_by" \
  -H "Content-Type: application/json" \
  -d '{"classification":"HMI","lasts":50}'

# Login / IP
curl -sS -H "X-API-KEY: $TOKEN" "$BASE/api/events/filter_by" \
  -H "Content-Type: application/json" \
  -d '{"classification":"Security","message":"User logged in","lasts":20}'

# Contadores HTTP (no sustituye access log)
curl -sS "$BASE/api/health/system" | jq '{HTTP_REQUESTS_1M,HTTP_5XX_1M,HTTP_IN_FLIGHT}'
```

---

### 9. Runbook rápido (L1 + métricas)

```bash
ls -lh logs/app.log*
curl -sS -H "X-API-KEY: $TOKEN" "$BASE/api/settings/"
curl -sS "$BASE/api/health/system" | jq '{LOG_ERROR_RATE_PER_MIN,LOG_ERROR_SUPPRESSED_PER_MIN,LOG_ERROR_ALERT,EVENTS_RATE_PER_MIN,EVENTS_RATE_ALERT,LOGS_RATE_PER_MIN,LOGS_RATE_ALERT,HTTP_REQUESTS_1M,HTTP_5XX_1M}'
```

Endurecer: `update_log_level(30)`; techo 5×5 MiB. Soak error controlado: `du logs/` acotado; rate intentos ≈ 60; suppressed ≈ 59; `LOG_ERROR_ALERT=true`.

Verificación planta Events: login/logout/superseded/ack/CRUD tag/force value/intervalo/transición máquina/`System started`/DB disconnect-reconnect.

Para log de aplicación en GUI vs Eventos, ver §8.20. Forense terminal: §8.22.


## Parte B — Continuidad día 1 vs día 1000

> Fuente original: `AUDIT_LONG_RUN_CONTINUITY.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + despliegue planta iDetectFugas |
| **Alcance** | Degradación a 1 / 10 / 100 / 1000 días: disco, RAM, CPU, locks, colas, historiador, catálogo, logs. Contraste código vs operación 24/7. Retención PG = DBA (fuera del edge). |
| **Fecha baseline** | 2026-08-27 (hallazgo N1 disco ≠ cola) |
| **Hardening código** | 2026-08-27 — SPEC_LONG_RUN_SOFTWARE_HARDENING (R1–R5) en checkout · **2026-09-15** prune DLQ archiva (no DELETE de proceso) |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md), [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) |
| **Evidencia planta** | N1 `intelcon2` / 192.168.1.80 · `journal.db` 331 MiB + WAL 50 MiB · PENDING=45 · SENT=190 712 · freelist 217 MiB · `auto_vacuum=0` (imagen `3.0.0` **sin** hardening) |
| **Veredicto** | Edge local (proceso + disco SAF/catálogo/DLQ) **A− en código**. Hot path O(1) + reclaim unificado + DLQ acotada + alerta disco + fuga SM cerrada. Historiador PG **B−** (retención = DBA). Certificado día-1000 **pendiente deploy + soak 24 h**. |
| **Clasificación** | Auditoría de continuidad operacional · degradación · grado planta 24/7 |

---

### 0. Pregunta fundamental

**¿El nodo del día 1000 es tan ligero y predecible como el del día 1, con catálogo fijo y red recuperable?**

**Respuesta (post-hardening en checkout):** **sí para el edge** — RAM, CPU del hot path, journal, `catalog.db` y `DEAD_LETTER` tienen techo duro o reclamación automática. El historiador PostgreSQL sigue creciendo de forma lineal; eso es política DBA, no del proceso del edge.

```
Día 1     proceso ligero + journal pequeño + PG vacío
Día 10    mismo RSS; tras catch-up + ~1 h, reclaim_idle compacta journal/catalog
Día 100   mismo RSS; DLQ ≤ 10k / ≤ 7 d; PG crece (DBA)
Día 1000  mismo RSS si catálogo fijo; disco edge autoregenerativo; PG retenido por planta
```

---

### 1. Horizonte temporal (qué debe pasar)

| Horizonte | Régimen | Lo que debe permanecer plano | Lo que puede crecer (y cómo se corta) |
|---|---|---|---|
| **Día 1** | Arranque, catálogo caliente | RSS worker, `set_value` p99, `SAF_QUEUE_DEPTH` ≈ flujo vivo | Journal WAL transitorio |
| **Día 10** | Outage PG de horas + catch-up | Tras drenar: PENDING ≈ decenas | SENT TTL 1 h → freelist → VACUUM idle; WAL TRUNCATE |
| **Día 100** | Operación continua | Mismas métricas de proceso; `TAG_OBSERVER_COUNT` estable | Historiador PG ~ lineal (DBA); DLQ podada |
| **Día 1000** | Años de planta | Hot path O(1); ring ≤ 100k; logs L1 rotados | Sin retención DBA, PG es el único unbounded “oficial” |

Objetivo de aceptación (alineado con [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md)):

- RSS gunicorn **±15 %** vs baseline a catálogo fijo.
- `SAF_QUEUE_DEPTH` sin crecimiento monotónico con PG sano.
- `SAF_DISK_BYTES` **después de compactar** en el orden del flujo vivo (MiB, no el pico de la outage).
- `HOST_DISK_CRITICAL` falso en régimen sano; alerta al cruzar 85 %.
- `DAS.monitored_items` / `TAG_OBSERVER_COUNT` / `len(_machines)` estables.
- p99 `set_value` no degrada con journal gordo (O(1) `pending_count`).

---

### 2. Qué está acotado (día 1 ≈ día 1000 en el edge)

| Recurso | Techo | Dónde |
|---|---|---|
| Ring RAM tags | 100 000 | `SafConfig.ring_maxsize` |
| PENDING durable | 5 000 000 → backpressure | `max_pending_rows` |
| Disco journal (hard) | 10 GiB | `max_disk_bytes`; evict SENT; si no basta → `JournalDiskFullError` |
| Shed analog history | high 50k / low 10k | solo tags no críticos (`SYS.PERF.*`); **nunca** campo `FI_`/`PI_`/`DI_`/`TI_`, `*.leak*`, alarmas/eventos/logs |
| SENT | GC TTL **1 h**, lotes 5 000 | `gc_sent` |
| **DEAD_LETTER** | **TTL 7 d + cap 10 000** | `prune_dead_letters` **archiva** a `journal-archive.db` (`ARCHIVED`); no DELETE de proceso |
| Journal freelist / WAL | TRUNCATE + VACUUM idle | `reclaim_idle` (pending ≤ 256, freelist ≥ 64 MiB, ≤ 1/h) |
| **catalog.db** | Mismo umbral, **lock propio** | `compact_catalog_idle` fuera del `RLock` del journal |
| CycleSampleCache | TTL 2 s | `cycle_dedupe.py` |
| Buffer OPC / SM | `deque(maxlen=…)` | `buffer.py`, DAS, core |
| Async SM registry | `drop()` remueve `_machines` | `state_machine.py` |
| Trend PERF | ~68 puntos / 5 min | `metrics_sampler.py` |
| Cooldown audit | cap 256 | `audit_metrics.py` |
| L1 `app.log` | 10 MiB × 3 ≈ 40 MiB | `RotatingFileHandler` |
| Docker json-file | 10m × 7 ≈ 70 MiB | compose iDetectFugas |
| Disco host (alerta) | **85 %** → `HOST_DISK_CRITICAL` | sampler + evento con cooldown 1 h |
| Health `/health/saf` | O(1) | post-parche |
| Hot path pending / shed / cap | **O(1)** | `_pending_durable + len(_ring)` |

---

### 3. Hallazgo planta 2026-08-27 — disco ≠ cola (evidencia baseline)

N1 Linea1, cola ya drenada (imagen `idetectfugas/app:3.0.0` **sin** el hardening):

| Magnitud | Valor | Lectura |
|---|---|---|
| PENDING / REPLICATING | 45 | Flujo vivo. No hay lag de réplica. |
| SENT | 190 712 | Catch-up marcado SENT en la última hora. TTL 1 h aún no aplica. |
| `journal.db` | 331 MiB | Tamaño de fichero, no de filas vivas. |
| WAL | 50 MiB | No se truncaba en idle en esa imagen. |
| Freelist | 217 MiB | Huecos internos. `auto_vacuum=0`. |
| Gauge HMI | `SAF_DISK_BYTES` = db+wal+shm | Correcto; **no** es “cola”. |

Ese síntoma motivó el compact idle. Con el código actual del checkout, tras deploy:

```
t=0      Cola drenada → PENDING ≈ flujo vivo
t≈0+     TRUNCATE WAL (journal + catalog) → baja WAL
t≈1 h    GC SENT → freelist grande
t≥1 h    VACUUM idle (ambos .db) → SO recupera el pico
continuo prune_dead_letters (TTL 7 d / cap 10k → ARCHIVED, no DELETE)
```

VACUUM del journal sigue bajo el `RLock` (trade-off conocido: segundos en idle, ≤ 1/h). El VACUUM de `catalog.db` **no** comparte ese lock.

---

### 4. SPEC_LONG_RUN_SOFTWARE_HARDENING — evidencia implementada

Orden ejecutado: R3 → R5 → R2 → R1 → R4 (+ docs sampler).

#### 4.1 Cierres R1–R5

| ID | Requerimiento | Evidencia en código | Tests |
|---|---|---|---|
| **R1 / LR-DLQ-1** | DLQ acotada **sin perder proceso** | `JournalWriter.prune_dead_letters()`: copia a `journal-archive.db` y `status=ARCHIVED` por `created_at` (TTL default 7 d) y por exceso sobre `dead_letter_max_rows` (default 10 000). Llamado desde `reclaim_idle()`. Config: `saf_dead_letter_ttl_s`, `saf_dead_letter_max_rows`. Replay: `resurrect_dead_letters` vía `POST /api/admin/saf/retry`. | `test_prune_dead_letters_caps_max_rows`, `test_prune_dead_letters_ttl`, `test_p0_4_prune_archives_process_rows`, `test_p0_7_resurrect_dead_letters` |
| **R2 / LR-CAT-1** (+ compact journal) | Compactación unificada | Tras compactar journal, si `pending ≤ compact_max_pending`, `compact_catalog_idle()` en `catalog/local_db.py` con `_compact_lock` propio: checkpoint TRUNCATE + VACUUM condicional. | `test_compact_catalog_idle_vacuums_freelist`, `test_reclaim_idle_*` |
| **R3 / LR-MEM-1** | Fuga SM | `AsyncStateMachineWorker.drop()` hace `_machines.remove(machine)` y `sched_to_drop.stop()`. | `test_drop_removes_from_registry` |
| **R4 / LR-DEP-1** | Alarma disco host | Sampler mide volumen de datos (`journal_path` dir o `AUTOMATION_DATA_DIR`). Snapshot: `HOST_DISK_USED_PERCENT`, `HOST_DISK_CRITICAL` (> `host_disk_critical_percent` default 85). Flanco → `persist_system_event("Disk usage critical")` cooldown 3600 s. HMI: tile rojo si critical. | `test_host_disk_critical_*`, `test_psutil_fields_when_available` |
| **R5 / LR-CFG-1** | Config huérfana | Eliminados `ingest_heartbeat_s` y `backup_size_bytes` de `SafConfig` / `from_app_config`. `grep` en `automation/` vacío. | CA-LR-06 por grep |

#### 4.2 Defaults nuevos (`SafConfig`)

| Parámetro | Default | Override |
|---|---|---|
| `dead_letter_max_rows` | 10 000 | `saf_dead_letter_max_rows` |
| `dead_letter_ttl_s` | 604 800 (7 d) | `saf_dead_letter_ttl_s` |
| `compact_min_freelist_bytes` | 64 MiB | `saf_compact_min_freelist_bytes` |
| `compact_min_interval_s` | 3600 | `saf_compact_min_interval_s` |
| `compact_max_pending` | 256 | `saf_compact_max_pending` |
| `host_disk_critical_percent` | 85.0 | `saf_host_disk_critical_percent` |

#### 4.3 Docs / operabilidad (LR-SYS-1 mitigado en ops)

- [docs/runbook.md](../docs/runbook.md): poll de métricas → `/health/node` O(1); no poll frecuente de `/health/system`.
- [docs/node-performance-runbook.md](../docs/node-performance-runbook.md): mismo aviso + `HOST_DISK_CRITICAL`.
- HMI `performance.pollHint` (es/en): tooltip en `/performance`.

El coste O(n tags) de `/health/system` y `_sample_field` **permanece**; la mitigación es no usarlo para dashboard.

---

### 5. Matriz de riesgos (día 1000) — estado post-hardening

#### 5.1 Cerrados en checkout

| ID | Riesgo | Estado |
|---|---|---|
| **LR-DLQ-1** | DEAD_LETTER sin tope **ni pérdida de proceso** | **Cerrado** — TTL 7 d + cap 10k; prune **archiva** |
| **LR-CAT-1** | catalog.db sin compact | **Cerrado** — `compact_catalog_idle` |
| **LR-MEM-1** | `drop()` no limpia `_machines` | **Cerrado** |
| **LR-CFG-1** | Config huérfana | **Cerrado** — eliminada |
| **LR-DEP-1** | Disco host sin alerta | **Cerrado** — `HOST_DISK_CRITICAL` + evento |
| O(1) pending / reclaim journal | COUNT por tag; fichero que no encoge | **Cerrado** (sesión previa + R2) |

#### 5.2 Residuales aceptados / fuera de alcance edge

| ID | Riesgo | Notas |
|---|---|---|
| **LR-PG-1** | TagValue/Events/Logs en PG sin TTL | **Fuera de alcance** — DBA / particiones. LOG-H5. |
| **LR-VAC-1** | VACUUM journal bajo `RLock` | Mitigado (idle, ≤ 1/h, pending ≤ 256). Medir `elapsed_s` en soak. Catalog compact **fuera** del lock. |
| **LR-BKP-1** | `sqlite_db_backup` sin poda | Historiador SQLite legado; planta usa PG. Spec: backups historiador fuera de alcance. |
| **LR-SYS-1** | `/health/system` O(n) | Documentado; dashboard usa `/health/node`. |
| **LR-CTR-1** | Contadores monotónicos | Usar rates, no totales. |
| **LR-IDX-1** | Índice UNIQUE mientras fila viva | SENT 1 h; DL ahora archivada (no borrada). |

#### 5.3 Ya no son el problema

| Tema | Estado |
|---|---|
| `COUNT(*)` por tag | Cerrado |
| Health hub COUNT sqlite | Cerrado (P0) |
| FIFO / shed TAG-only / DLQ escape | Cerrado |
| L1 logs / json-file | Acotados |
| Ring / shed / cap / max disk | Acotados |
| `pending_orphans` catálogo | TTL 5 min + 5 retries |

---

### 6. CPU, locks y latencia

| Camino | Complejidad | Riesgo a 1000 d |
|---|---|---|
| `set_value` → ring | O(1) | Bajo si no hay VACUUM journal en curso |
| Flusher INSERT | O(log N) | N = filas vivas (PENDING + SENT &lt; 1 h + DL acotada) |
| `fetch_pending LIMIT` | O(lote) | OK |
| Sampler PERF / FIELD_STALE | O(tags) / 5 s | Crece con catálogo, no con el calendario |
| VACUUM journal | O(fichero), bajo lock | Raro; log `elapsed_s` |
| VACUUM catalog | O(fichero), lock propio | No bloquea enqueue SAF |
| `prune_dead_letters` | O(archivados), idle | Capado a ≥ 60 s entre podas; UPDATE ARCHIVED, no DELETE proceso |

**Invariante:** ninguna lógica R1–R5 corre dentro de `Tag.set_value`.

---

### 7. Resiliencia (outage)

| Escenario | Día 1 | Día 1000 (código nuevo) |
|---|---|---|
| PG caído 1 h | PENDING crece; shed **no crítico** | Tras recuperar: catch-up + SENT TTL + reclaim. Campo/leak **siguen encolándose**. Retryable **no** va a DLQ |
| PG caído muchos días | Cap 5e6 / 10 GiB | Backpressure; PENDING sagrado; ops **retry** (resurrect); **no** reset |
| Poison row | → DLQ | DLQ se **archiva** sola (TTL/cap); resurrect con retry |
| Catálogo a ratos | Backoff 30→900 s | `catalog.db` compacta en idle |
| Disco host ≥ 85 % | — | `HOST_DISK_CRITICAL` + Event |
| Restart gunicorn | Hidrata contadores | Arranque con journal gordo: COUNT una vez |

---

### 8. Despliegue iDetectFugas

| Recurso | Tope | Comentario |
|---|---|---|
| `./temp/db` | Disco host + alerta 85 % | Journal + catalog; reclaim tras deploy |
| `./temp/logs` | ~40 MiB app | Volumen persiste |
| `./temp/models` | Artefactos ML | Estático salvo redeploy |
| json-file | ~70 MiB | OK |
| Healthcheck / `GUNICORN_TIMEOUT=120` | No relajar | Fuera de alcance |

**Planta hoy:** imagen `3.0.0` **no** incluye R1–R5 ni O(1) pending hasta reinstalar wheel PyAutomation (+ rebuild HMI para tile/tooltip).

---

### 9. Estrategia de continuidad (estado)

| Paso | Estado |
|---|---|
| 1. Hot path O(1) | **Hecho** en checkout |
| 2. Reclaim idle journal | **Hecho** |
| 3. Compact catalog | **Hecho** (R2) |
| 4. DLQ TTL/cap | **Hecho** (R1) |
| 5. Alerta disco host | **Hecho** (R4) |
| 6. Fuga SM + config limpia | **Hecho** (R3, R5) |
| 7. Retención PG | **Pendiente DBA** (LR-PG-1) |
| 8. Deploy wheel + soak 24 h | **Pendiente planta** |

**No hacer:** VACUUM en enqueue; COUNT por muestra; borrar PENDING automático; relajar healthcheck/timeout.

---

### 10. Criterios de aceptación (CA-LR)

| ID | Criterio | Estado |
|---|---|---|
| **CA-LR-01** (spec: DLQ ≤ 10k / ≤ 7 d, **sin DELETE de proceso**) | `prune_dead_letters` archiva | **PASS** unit (`test_long_run_hardening`, `test_p0_4_prune_archives_process_rows`) |
| **CA-LR-02** | `reclaim_idle` compacta journal **y** catalog con PENDING ≤ 256 | **PASS** unit; **pendiente planta** |
| **CA-LR-03** | `drop()` decrementa `_machines` | **PASS** `test_drop_removes_from_registry` |
| **CA-LR-04** | `/health/node` expone `HOST_DISK_*` + CRITICAL | **PASS** unit (psutil skip si no instalado) |
| **CA-LR-05** | Evento Disk usage critical con cooldown | **PASS** unit flanco |
| **CA-LR-06** | Sin `ingest_heartbeat_s` / `backup_size_bytes` en `automation/` | **PASS** grep |
| **CA-LR-07** | Hot path no ejecuta R1–R5 | **PASS** por diseño (idle workers); soak/py-spy planta pendiente |
| **CA-LR-08** (legado) | Enqueue sin `COUNT(*)` | **PASS** tests SAF |
| **CA-LR-09** | Tras outage + compact, `SAF_DISK_BYTES` orden MiB | **Pendiente deploy N1** |
| **CA-LR-10** | Retención TagValue/Events PG | **Pendiente DBA** |
| **CA-LR-11** | Soak 24 h RSS ±15 %, cola plana | **Pendiente planta** |

Numeración CA-LR-01…07 alineada a SPEC_LONG_RUN_SOFTWARE_HARDENING; CA-LR-08…11 conservan criterios del baseline O(1)/disco/PG/soak.

---

### 11. Archivos clave

| Pieza | Ruta |
|---|---|
| Contador O(1), prune DLQ, reclaim | `automation/persistence/journal.py` |
| Config techos | `automation/persistence/config.py` |
| Compact catalog | `automation/catalog/local_db.py` `compact_catalog_idle` |
| Idle caller | `automation/workers/replication.py` |
| Disco host / CRITICAL | `automation/workers/metrics_sampler.py` |
| drop SM | `automation/workers/state_machine.py` |
| Tests hardening | `automation/tests/test_long_run_hardening.py` |
| HMI tile + pollHint | `hmi/src/pages/Performance.tsx`, locales |

---

### 12. Veredicto

Con R1–R5 en el checkout, el **edge** cumple la filosofía nuclear-industrial para 1000 días: RAM acotada, disco local autoregenerativo (journal + catalog + DLQ), CPU del hot path sin estas rutinas, configuración sin falsos techos.

Queda:

1. **Desplegar** wheel (+ HMI) en N1/N2.
2. **Observar** CA-LR-09 tras una outage o compact natural.
3. **Soak 24 h** (CA-LR-11).
4. **Retención PG** (CA-LR-10) — no es trabajo del edge.

El hueco visto en planta (cola vacía, disco alto) queda explicado y cerrado en código; la imagen en producción aún no lo refleja.


## Parte C — Puntos críticos de misión

> Fuente original: `AUDIT_MISSION_CRITICAL.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Productos** | PyAutomationIO (`github/PyAutomation`, rama de trabajo) + iDetectFugas (`gitlab/intelcon/idetectfugas`) |
| **Alcance** | Sincronización temporal, integridad ante cortes de energía, sesiones, redundancia, actualizaciones, monitorización, caos |
| **Estándar de referencia** | Grado nuclear industrial / 24/7/365 — **código + spec**, no certificación de planta |
| **Fecha** | 2026-08-28 |
| **Audiencia** | Ingeniería, operaciones, seguridad |
| **Fuentes** | [AUDIT_TIME.md](./AUDIT_TIME.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_DB.md](./AUDIT_DB.md), [docs/multi-edge.md](../docs/multi-edge.md), [docs/CHAOS_TESTING.md](../docs/CHAOS_TESTING.md) |

**Regla de veredicto:** PASS de código no es “grado nuclear alcanzado en planta”. Soak, caos OT y hardware PLP/UPS van como pendientes con plantilla, no como ejecutados.

---

### 1. Resumen ejecutivo

El stack ya era fuerte en SAF (WAL + ACK exact-once), NTP de aplicación, sesiones HMI auditadas y dashboard `/performance`. Esta ronda cierra los huecos **nombrados** por la spec CT (métrica `HOST_NTP_OFFSET_MS`, gate SAF a 1 s, `fsync` post-COMMIT, heartbeat de pares, runbook de caos, rollback documentado) **sin inventar** un failover que robe tags ni un restart &lt; 10 s.

| ID | Área | Nota | Estado código/spec | Planta |
|---|---|---|---|---|
| CT-01 | Tiempo | NTP + `ALM.PERF.NTP` + gate SAF | **A** | soak 2-edge pendiente |
| CT-02 | Energía | FULL + fsync + PLP documentado + T-01 | **A+** | soak 24 h / UPS pendiente |
| CT-03 | Sesiones | TTL por heartbeat, fail-closed token, audit Events | **A** | soak 2-edge pendiente |
| CT-04 | Failover | Circuit breaker + `ALM.PERF.NODE_DOWN`; **no** steal-tags | **B+** (diseño) | lab C-04 pendiente |
| CT-05 | Zero-DT | Volúmenes persistentes; rolling por línea; overlay ~30 s | **B** | procedimiento en deploy |
| CT-06 | Salud | `/performance` + `/lds-dashboard` + 16 `ALM.PERF.*` | **A−** | scrape Prometheus opcional |
| CT-07 | Caos | Runbook + plantilla + unitarios; campaña OT vacía | **B+** | [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) |

**Puntuación global (código):** **A− / B+**. No se declara “grado nuclear industrial alcanzado” mientras CT-04-A (I/O failover), CT-05-B (&lt; 10 s) y CT-07-D (campaña firmada) sigan fuera de contrato o pendientes.

---

### 2. Hallazgos por control

#### CT-01 Sincronización temporal

**Pregunta:** ¿Todos los nodos comparten fuente de tiempo y se monitorea el desfase?

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-01-A | NTP en nodos | ✅ PASS | `AUTOMATION_NTP_SERVERS`; chrony en [docs/ntp-deployment.md](../docs/ntp-deployment.md); comentarios en `compose/.env` y `deploy/.env` |
| CT-01-B | Deriva | ✅ PASS | `HOST_NTP_OFFSET_MS` / `HOST_NTP_ABS_OFFSET_MS` en sampler; `ALM.PERF.NTP` default **100 ms**; crítica `ALM.NTP.OutOfSync` **1000 ms** (`ntp_monitor.py`, `clock_alarms.py`) |
| CT-01-C | Timestamps UTC | ⚠️ CONDICIONAL | Wire UTC ([AUDIT_TIME.md](./AUDIT_TIME.md)); TagValue resolución **ms** (`TAGVALUE_TIMESTAMP_RESOLUTION = 3`), no µs — UNIQUE `(tag, timestamp)` |
| CT-01-D | Gate SAF | ✅ PASS | `clock_blocks_replication()`: si NTP enabled y `|offset| > 1000 ms`, no replica; PENDING intacto; no abre el circuit breaker |

**Gaps residuales**

- Precisión µs en TagValue: **no se cambia** (colapsaría UNIQUE y el ciclo de máquina).
- `ntp_fail_closed` sigue siendo opt-in (pausa adquisición); el gate SAF a 1 s aplica con el monitor activo aunque fail-closed esté en false.

#### CT-02 Integridad ante cortes de energía

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-02-A | `synchronous=FULL` | ✅ PASS | `journal.py` `_ensure_open_locked` |
| CT-02-B | fsync post-COMMIT | ✅ PASS | FD `O_RDONLY` + `os.fsync` en `_commit_locked` |
| CT-02-C | Hardware PLP | ✅ PASS spec | [HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md) § power-loss (UPS + SSD PLP) |
| CT-02-D | `data=ordered` | ✅ PASS | fstab documentado; `HOST_DISK_DATA_ORDERED`; warning en `healthcheck.py` (no tumba ping) |
| CT-02-E | SIGKILL | ✅ PASS tests | `TestT01Apocalypse`; plantilla soak [AUDIT_DB.md](./AUDIT_DB.md) |

#### CT-03 Sesiones y trazabilidad

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-03-A | TTL | ✅ PASS | No hay columna `expires_at`; TTL = `last_heartbeat` + 120 s (`hmi_session_cleanup.py`) |
| CT-03-B | Heartbeat | ✅ PASS | Socket ping/pong; `register_hmi_socket_heartbeat` |
| CT-03-C | Fail-closed auth | ⚠️ CONDICIONAL | Token inválido → rechazo. Store de sesión caído → **acepta** socket con `session_store_degraded` (autonomía de catálogo local). No se cambia: rompería HMI offline. |
| CT-03-D | Trazabilidad | ✅ PASS | Events HMI connect/disconnect/reject (`hmi_socket_audit.py`); login API en Events |
| CT-03-E | No reutilizar sid | ✅ PASS | sid Socket.IO único; logout/disconnect borra store |

Detalle: [AUDIT_HMI.md](./AUDIT_HMI.md) (A+ código).

#### CT-04 Redundancia y failover

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-04-A | Multi-edge steal-tags | ❌ FAIL de spec / ✅ diseño | **Edge B no asume tags de A.** Partición `owner_node` + rechazo SAF extranjero. Documentado en [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) y [docs/multi-edge.md](../docs/multi-edge.md). Implementar steal-tags sería split-brain de I/O. |
| CT-04-B | Circuit breaker | ✅ PASS | `replicator.py` `CircuitBreaker` |
| CT-04-C | Heartbeat pares | ✅ PASS | `Nodes.heartbeat` cada tick del sampler; `ALM.PERF.NODE_DOWN` |
| CT-04-D | Runbook + caos | ⚠️ CONDICIONAL | Runbook sí; campaña C-04 en [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) pendiente |
| CT-04-E | Split-brain | ✅ PASS | Single-writer por área; samples ajenos a SENT/descartados |

#### CT-05 Actualizaciones sin downtime

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-05-A | Estrategia | ⚠️ CONDICIONAL | Rolling **por línea**, no blue-green en el mismo puerto. iDetectFugas `deploy/README.md` |
| CT-05-B | Restart &lt; 10 s | ❌ FAIL | `_restart_eta_s` ≈ **30 s** (delay 2 + graceful 10 + boot 15 + recycle 3). LGBM ya no infla el overlay (hilo nativo). Sigue sin ser &lt; 10 s. iDetectFugas `audits/13-AUDIT_CONTAINER_STARTUP.md` |
| CT-05-C | Estado persistente | ✅ PASS | `data/db`, `data/configs`, `data/models` bind mounts |
| CT-05-D | Rollback | ✅ PASS docs | Restaurar `AUTOMATION_VERSION` + `./up.sh`; backup tar |
| CT-05-E | CI smoke deploy | ⚠️ CONDICIONAL | Unitarios sí; job de imagen+smoke de planta no es parte de este repo de framework |

Mitigación: overlay HMI durante el reciclo; la otra línea sigue adquiriendo.

#### CT-06 Monitorización proactiva

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-06-A | Salud sistema | ✅ PASS | `/api/health/system` y `/api/health/node` |
| CT-06-B | KPI negocio (fugas) | ✅ PASS | Dashboard `/lds-dashboard` + `GET /api/LDS/dashboard` (iDetectFugas `audits/14-AUDIT_LDS_DASHBOARD.md`). No vive en `/performance`. |
| CT-06-C | Alertas tempranas | ✅ PASS | `ALM.PERF.*` (16 specs) + NTP/SSD/NODE_DOWN |
| CT-06-D | Events de salud | ✅ PASS | Transiciones NTP, disco crítico, SSD, HMI |
| CT-06-E | Dashboard HMI | ✅ PASS | `/performance` chips NTP y nodo par |
| CT-06-F | Prometheus | ✅ PASS docs | [docs/observability.md](../docs/observability.md) — scrape JSON, sin exporter nativo |

#### CT-07 Pruebas de caos

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-07-A | Runbook | ✅ PASS | [docs/CHAOS_TESTING.md](../docs/CHAOS_TESTING.md) |
| CT-07-B | Simulación | ✅ PASS tests | T-01, disco lleno, circuit, catalog, `test_mission_critical.py` |
| CT-07-C | RTO/RPO | ⚠️ CONDICIONAL | Objetivos escritos; **no medidos en OT** |
| CT-07-D | Última campaña | ⚠️ CONDICIONAL | Plantilla [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) |
| CT-07-E | CI caos corto | ✅ PASS opcional | unittest listado en el runbook |

---

### 3. Plan de implementación (esta ronda)

| Pri. | Gap | Acción | Estado |
|---|---|---|---|
| P0 | CT-01-B/D | `HOST_NTP_*`, `ALM.PERF.NTP`, gate replicador 1 s | Hecho |
| P0 | CT-02-B/C/D | `os.fsync`, PLP doc, `data=ordered` en snapshot/healthcheck | Hecho |
| P0 | CT-04-C | Heartbeat `Nodes.last_seen` + `ALM.PERF.NODE_DOWN` | Hecho |
| P1 | CT-05-A/D | Rolling + rollback en `deploy/README.md` | Hecho |
| P1 | CT-07 | CHAOS runbook + plantilla | Hecho |
| P2 | CT-06-F | `docs/observability.md` | Hecho |
| P2 | CT-04-A | **No implementar** steal-tags | Documentado |
| P2 | CT-05-B | **No afirmar** restart &lt; 10 s | Documentado |
| P3 | CT-06-B | KPI fugas: dashboard `/lds-dashboard` (iDetect + HMI) | Hecho |
| P3 | CT-07-D | Ejecutar C-01…C-05 en lab y firmar `AUDIT_RELIABILITY.md` | Abierto |

---

### 4. Evidencia de implementación (código)

| Archivo | Cambio |
|---|---|
| `automation/persistence/journal.py` | FD durabilidad + `os.fsync` post-COMMIT |
| `automation/persistence/replicator.py` | `clock_blocks_replication` |
| `automation/dbmodels/nodes.py` | `heartbeat`, `stale_peer_ids` |
| `automation/managers/db.py` | wrappers |
| `automation/workers/metrics_sampler.py` | `HOST_NTP_*`, `_sample_peers` |
| `automation/utils/performance_alarms.py` | specs `ntp`, `node_down` |
| `automation/utils/performance_alarm_config.py` | umbrales 100 ms / bool |
| `automation/utils/disk_mount.py` | `HOST_DISK_DATA_ORDERED` |
| `healthcheck.py` | warning `data=ordered` |
| `hmi/src/pages/Performance.tsx` | chips NTP / peer |
| `automation/tests/test_mission_critical.py` | **nuevo** |
| `docs/CHAOS_TESTING.md`, `docs/observability.md` | **nuevos** |
| `audits/AUDIT_RELIABILITY.md` | plantilla |
| `docs/HARDWARE_REQUIREMENTS.md` | § power-loss |
| iDetectFugas `deploy/README.md` | update / rollback / NTP; overlay ~30 s |
| `automation/modules/health/resources/health.py` | `/liveness`, `/readiness` (Fase A; LGBM no bloquea) |

Tests: `test_mission_critical`, pragmas journal (`_durability_fd`), `test_disk_durability` `data=ordered`, catálogo PERF 16.

---

### 5. Checklist clase mundial (honesto)

| ID | Área | Criterio spec | Estado |
|---|---|---|---|
| CT-01 | Tiempo | NTP configurado, monitoreado, alarmado | ✅ PASS código (ms, no µs) |
| CT-02 | Energía | FULL + fsync + hardware spec + T-01 | ✅ PASS código/spec |
| CT-03 | Sesiones | TTL, heartbeat, audit; fail-closed token | ✅ PASS con fail-open store degradado |
| CT-04 | Failover | Multi-edge + breaker + heartbeat | ⚠️ CONDICIONAL (sin steal-tags) |
| CT-05 | Zero-DT | Docs + persistencia + rollback | ⚠️ CONDICIONAL (~30 s overlay, no &lt; 10 s) |
| CT-06 | Salud | Métricas, alarmas, dashboard | ✅ PASS; KPI fugas en `/lds-dashboard` |
| CT-07 | Caos | Runbook + RTO/RPO escritos + tests | ⚠️ CONDICIONAL (campaña OT vacía) |

**Veredicto final:** el sistema está **listo para operar 24/7 por línea con SAF y fail-closed de I/O**. No está certificado como planta nuclear hasta: (1) UPS/SSD PLP instalados, (2) `AUDIT_RELIABILITY.md` firmado, (3) soak 24 h 2-edge, (4) `AUTOMATION_NTP_SERVERS` en cada Moxa. El failover mágico de adquisición **no forma parte del producto**.


## Parte D — Plantilla campaña de caos CT-07

> Fuente original: `CHAOS_LAST_RUN.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO + iDetectFugas |
| **Estado** | **Pendiente de ejecución en planta / lab OT** |
| **Fecha de esta plantilla** | 2026-08-28 |
| **Runbook** | [docs/CHAOS_TESTING.md](../docs/CHAOS_TESTING.md) |

Esta campaña **no se simula en CI**. Rellenar tras C-01…C-05 reales. Los unitarios (T-01, disco lleno, gate NTP, heartbeat de nodos) viven en `automation/tests/` y no sustituyen esta tabla.

### Resultados (rellenar)

| Campaña | Fecha / operador | RPO | RTO medido | OK |
|---|---|---|---|---|
| C-01 SIGKILL / T-01 | _pendiente_ | 0 samples perdidos | replay inmediato | ☐ |
| C-02 PG down | | cola drena a 0 | | ☐ |
| C-03 Disco lleno | | sin WAL corrupto | | ☐ |
| C-04 Edge down | | 0 writes cruzados | `ALM.PERF.NODE_DOWN` ≤ 105 s | ☐ |
| C-05 NTP > 1 s | | PENDING conservado | réplica bloqueada | ☐ |

### Objetivos de contrato

| Métrica | Objetivo | Medido |
|---|---|---|
| RPO energía | 0 | |
| RTO contenedor | ≤ `_restart_eta_s` (~30 s overlay; LGBM en background) | |
| RTO detección par caído | ≤ 90 s + debounce | |
| Steal-tags A→B | **no aplica** (diseño) | n/a |

### Evidencia

Adjuntar: `GET /api/health/node` de ambos edges, Events `NTP` / `NODE_DOWN`, logs gunicorn, T-01 [AUDIT_DB.md](./AUDIT_DB.md).

Última corrida T-01 automatizada (no lab OT): ver `AUDIT_DB.md`.

