# Auditoría compacta: logs de runtime, eventos de usuario y bitácora operacional

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
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) §4.5, `docs/Developments_Guide/logs.md`, `docs/Users_Guide/OperationalLogs/index.md` |
| **Veredicto** | L1 infra **A+**; **Log aplicación ≠ Eventos** (dominios separados; falta pantalla HMI/runtime). Export store **C**. Eventos **A−** (§2, otro producto UI). Bitácora **A+** |
| **Clasificación** | Auditoría operativa · trazabilidad · confidencialidad interna |

---

## 0. Cuatro cosas distintas — no confundir nombres

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

Stdout: `StreamHandler` al **mismo nivel** que el archivo (`log_level` / env `AUTOMATION_LOG_TO_STDOUT=1` en Docker). Mismo formatter; en planta iDetectFugas suele ir todo a stdout del contenedor (`json-file` max 10m×3).

Métrica: `LOG_ERROR_RATE_PER_MIN` cuenta **intentos** (incl. suprimidos); `LOG_ERROR_ALERT` si > 5/min.

Error a 1 Hz → **1 línea escrita / 60 s**. Health sigue viendo ~60 intentos/min.

---

## 2. L3-E Eventos — trazabilidad de acciones (Trazabilidad Eterna)

> **No es log de aplicación.** Eventos registran acciones **modeladas** con contrato explícito (`@set_event`, auditores). Los ERROR/WARNING/tracebacks imprevistos del runtime van a **L1** (§1, §8) y a la pantalla **Log de aplicación** (§8.16), no a esta tabla.

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

## 8. Auditoría — estrategia de logs de **aplicación** (no persistencia de datos)

> **Alcance §8:** exclusivamente el **log de aplicación (L1)** — diagnóstico técnico, errores imprevistos, access HTTP. **No** es la tabla **Eventos** (§2), **no** es bitácora (§3), **no** es historiador TagValue.

### 8.1 Pregunta de auditoría

¿Puede mantenimiento ver en una **interfaz gráfica dedicada** (no la pantalla Eventos) los ERROR/WARNING/tracebacks del runtime — incluidos fallos **no previstos** que nunca pasaron por `@set_event` — con IP en access log, niveles DEBUG→CRITICAL, y sin abrir Docker/terminal?

### 8.2 Separación estricta: Log de aplicación ≠ Eventos

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

### 8.3 Modelo de planos (L1 vs L3-E)

| Plano | Destino | Qué captura | Fortaleza | Debilidad |
|---|---|---|---|---|
| **L1 — Log de aplicación** | `app.log` + stdout | Excepciones, I/O, workers, warnings no auditados | Rotación, dedupe ERROR | Sin GUI HMI hoy; sin access log completo |
| **L3-E — Eventos** | Tabla `Events` + `/events` | Login, socket HMI, CRUD, SAF resumido | Contrato industrial, IP en description | **No** captura bugs imprevistos |

**Conclusión:** Eventos cumplen auditoría de **acciones**. El **log de aplicación** cumple **salud técnica y bugs**. Faltan access log L1 (LOG-ACC-*) y **pantalla/consola propia** para L1 (LOG-GUI-* / LOG-EXP-*).

### 8.4 Niveles del log de aplicación (contrato DEBUG → CRITICAL)

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

### 8.5 HTTP REST — estado actual vs requisito nuclear

| Requisito | Implementación | Evidencia | Veredicto |
|---|---|---|---|
| Contar peticiones O(1) | `install_http_metrics` → `HTTP_REQUESTS_*`, `HTTP_5XX_*` en `/health/system` | `utils/http_metrics.py`, hook en `define_socketio` | **A** rendimiento |
| **Línea por petición** method + path + status + IP | **No existe** en L1 | Solo contadores; Flask/Werkzeug no configurado; gunicorn sin `accesslog` | **F gap** |
| IP del cliente | Helper `request_origin()` — **solo** auditores Events (login, etc.) | `system_event_audit.py` respeta `X-Forwarded-For` | **A** donde se usa; **C** cobertura |
| Usuario autenticado en log | Login/logout → Events `username=` + `origin=` | `user_session_audit.py` | **B** — no en access log general |
| Secretos fuera del log | Tokens nunca en message; clip 256 en Events | `hmi_socket_audit`, `Api.token_required` | **A+** |
| Errores 5xx trazables | Flask log + `@logging_error_handler`; contador 5xx | Traceback en L1 para excepciones no capturadas | **B+** — sin correlación request↔error |

**Qué sí genera línea L1 hoy:** excepciones no manejadas (p. ej. el `AttributeError` en `/api/history/backfill`), warnings de workers, CRITICAL de lifecycle. **Qué no:** `GET /api/health/system`, `POST /api/tags/…`, export CSV, etc.

### 8.6 Socket.IO — dónde va cada cosa (Eventos ≠ log aplicación)

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

Detalle Eventos socket: [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md).

### 8.7 Matriz «clase mundial» (solo log de aplicación)

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

### 8.8 Herencia — PyAutomationIO → iDetectFugas (y cualquier producto)

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

### 8.11 Consola operativa gráfica — requisito nuclear

El operador de planta y mantenimiento **no debe depender** de `docker logs`, SSH ni `grep` en el edge para vigilar la aplicación. El estándar exige:

| Requisito | Significado |
|---|---|
| **Vista unificada** | L1 runtime + (opcional) Events L3 auditables en una UI operativa (p. ej. Grafana Explore) |
| **Tiempo casi real** | Retraso ingestión → pantalla **≤ 5 s** (P95) en régimen normal |
| **Hot path intacto** | Emitir un log **nunca** espera red, disco remoto ni indexación |
| **Escala 1 → 100 M** | Insertar, exportar y consultar con coste **acotado por ventana/reciente**, no por tamaño total del historial |
| **Herencia** | iDetectFugas y cualquier producto PyAutomationIO heredan el mismo contrato sin código de export en la app |

**Principio de separación:** la aplicación **produce**; un **sidecar** o agente del host **transporta**; una **plataforma central** **indexa y sirve** la UI. Consultar 100 M de filas **nunca** ocurre dentro del worker gunicorn.

### 8.12 Arquitectura de referencia (patrón sidecar)

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

### 8.13 Contrato O(1) — insertar, exportar, consultar

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

### 8.14 Formato de exportación — JSON Lines + labels

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

### 8.15 Tres pantallas — responsabilidades separadas (no unificar)

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

### 8.16 Pantalla HMI «Log de aplicación» — diseño propuesto (LOG-GUI)

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

### 8.17 Estado actual vs estándar export + GUI log aplicación

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

### 8.18 Backlog — export store (LOG-EXP)

| ID | Prioridad | Entrega | CA |
|---|---|---|---|
| **LOG-EXP-1** | P0 | `JsonFormatter` + env `AUTOMATION_LOG_FORMAT=json`; labels `node_id`/`area`/`site` | CA-EXP-1: línea parseable `jq` |
| **LOG-EXP-2** | P0 | Sidecar Vector/Alloy → Loki; **cero** código en app | CA-EXP-2: store alimenta GUI |
| **LOG-EXP-3** | P1 | Dashboard Grafana **solo log de aplicación** (ERROR/WARNING/access) — **sin** Eventos | CA-EXP-3: filtros `level` + `node_id` |
| **LOG-EXP-4** | P1 | Backpressure sidecar cola ≤10 MB | CA-EXP-4: store caído → app OK |
| **LOG-EXP-5** | P2 | Runbook `docs/log-export-runbook.md` | CA-EXP-5: ops sin SSH |

Co-requisito pantalla HMI: **LOG-GUI-*** (§8.16). LOG-EXP alimenta Grafana y `/application-logs`.

### 8.19 CA de aceptación — export + GUI log aplicación

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

### 8.20 Runbook — log de aplicación en GUI (objetivo post LOG-EXP + LOG-GUI)

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

### 8.21 Backlog — access log HTTP (LOG-ACC)

| ID | Prioridad | Entrega | Criterio de aceptación |
|---|---|---|---|
| **LOG-ACC-1** | P0 | `AccessLogMiddleware` Flask: 1 línea INFO por petición `method path status duration_ms origin=` | CA-ACC-1: 100 GET `/api/health` → 100 líneas; IP visible tras proxy |
| **LOG-ACC-2** | P0 | Excluir ruido: `/static`, `/hmi/assets`, health probe opcional, Socket.IO long-poll | CA-ACC-2: soak RT HMI no multiplica líneas > umbral |
| **LOG-ACC-3** | P1 | `request_id` (UUID corto) en contexto + formatter L1 | CA-ACC-3: error 500 muestra mismo id en L1 y respuesta header |
| **LOG-ACC-4** | P1 | Mirror opcional DEBUG: Socket connect/disconnect en L1 (`AUTOMATION_LOG_SOCKET_L1=1`) | CA-ACC-4: grep `app.log` encuentra sid sin consultar Events |
| **LOG-ACC-5** | P2 | Spec `specs/12-APPLICATION-LOGGING.md` + tests CA-ACC | Herencia documentada; iDetectFugas sin config extra |

Ver también backlog export §8.18 (LOG-EXP-*).

**Implementación sugerida LOG-ACC-1:** módulo `automation/utils/access_log.py`; campos alineados con **LOG-EXP-FMT** (§8.14); alimenta **log de aplicación**, no Eventos.

### 8.23 CA de aceptación — access log (pendiente implementación)

| ID | Criterio | Estado |
|---|---|---|
| **CA-ACC-1** | Toda petición REST (excepto exclusiones §8.21) deja traza con IP en **L1/GUI log aplicación** | **Pendiente** |
| **CA-ACC-2** | Socket lifecycle en **Eventos**; mirror L1 solo con `AUTOMATION_LOG_SOCKET_L1=1` | **Parcial** |
| **CA-ACC-3** | Nivel DEBUG activable en caliente sin reinicio | **Cumple** (`update_log_level`) |
| **CA-ACC-4** | Producto hijo hereda config sin código duplicado | **Cumple** (iDetectFugas + env) |
| **CA-ACC-5** | Soak 24 h: `du logs/` acotado con access log INFO | **Pendiente** |

### 8.22 Runbook forense — terminal (solo emergencia; no sustituye GUI log aplicación)

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

## 9. Runbook rápido (L1 + métricas)

```bash
ls -lh logs/app.log*
curl -sS -H "X-API-KEY: $TOKEN" "$BASE/api/settings/"
curl -sS "$BASE/api/health/system" | jq '{LOG_ERROR_RATE_PER_MIN,LOG_ERROR_SUPPRESSED_PER_MIN,LOG_ERROR_ALERT,EVENTS_RATE_PER_MIN,EVENTS_RATE_ALERT,LOGS_RATE_PER_MIN,LOGS_RATE_ALERT,HTTP_REQUESTS_1M,HTTP_5XX_1M}'
```

Endurecer: `update_log_level(30)`; techo 5×5 MiB. Soak error controlado: `du logs/` acotado; rate intentos ≈ 60; suppressed ≈ 59; `LOG_ERROR_ALERT=true`.

Verificación planta Events: login/logout/superseded/ack/CRUD tag/force value/intervalo/transición máquina/`System started`/DB disconnect-reconnect.

Para log de aplicación en GUI vs Eventos, ver §8.20. Forense terminal: §8.22.
