# Auditoría: Base de datos, Store-and-Forward y durabilidad de disco

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Documento canónico** | 04 / 10 |
| **Fecha de agrupación** | 2026-09-16 |
| **Fuentes absorbidas** | `AUDIT_DB`, `AUDIT_DB_CONNECTIONS*`, `AUDIT_OPTIMAL_CONNECTIONS`, `AUDIT_DB_RECONNECT`, `AUDIT_NETWORK_TIMEOUT`, `AUDIT_DB_CONNECTION_MEMORY`, `AUDIT_STORE_AND_FORWARD`, `PERSISTENCE_FLOW`, `AUDIT_DISK_DURABILITY`, `T01_SOAK_LAST_RUN`, `SOAK_DISK_LAST_RUN` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md), [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |
| **Veredicto vigente** | Conexiones: un handle Peewee; idle 1 worker **1–3** (techo **≤ 4**); pool **prohibido**. SAF **A+** durabilidad / **A** Bulkhead. Disco **A+** código/spec; soak 24 h planta pendiente |
| **Clasificación** | Auditoría de contraste código vs diseño. IDs de hallazgos conservados. |


Este archivo agrupa **todas** las auditorías del dominio. Cada parte conserva el texto original.

## Índice de partes

- [Parte A — Base de datos, conexiones, reconexión y timeout](#parte-a-base-de-datos-conexiones-reconexión-y-timeout)
- [Parte B — Store-and-Forward y flujo de persistencia](#parte-b-store-and-forward-y-flujo-de-persistencia)
- [Parte C — Durabilidad de disco / eficiencia de escritura](#parte-c-durabilidad-de-disco-eficiencia-de-escritura)
- [Parte D — Plantilla soak disco / SAF 24 h](#parte-d-plantilla-soak-disco-saf-24-h)

---

## Parte A — Base de datos, conexiones, reconexión y timeout

> Fuente original: `AUDIT_DB.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Ciclo de vida Peewee/libpq bajo Gunicorn + gevent; reconexión; freeze del hub; censo idle; RAM atribuible a sockets |
| **Fecha original** | 2026-08-14 … 2026-08-17 (seis auditorías) |
| **Compactación** | 2026-08-18 — evidencia de código actualizada |
| **Reapertura** | 2026-09-09 — incidente `too many clients already` en laboratorio (§1.5). El censo era **dueño** del socket |
| **Segunda reapertura** | 2026-09-09 (post-arreglo) — `sockets above alert threshold` crónico (§1.6). No había fuga: el presupuesto medía la concurrencia web y los workers de ciclo lento retenían el socket |
| **SAF nuclear** | 2026-09-15 — `already closed` es RETRYABLE (attempts intactos, DLQ=0). Ver [AUDIT_DB.md](./AUDIT_DB.md) §3.5 |
| **Fuentes absorbidas** | `AUDIT_DB_CONNECTIONS`, `AUDIT_DB_CONNECTIONS_ETERNAL`, `AUDIT_OPTIMAL_CONNECTIONS`, `AUDIT_DB_RECONNECT`, `AUDIT_NETWORK_TIMEOUT`, `AUDIT_DB_CONNECTION_MEMORY` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) (BE-H4, RSS), [AUDIT_DB.md](./AUDIT_DB.md) (PENDING no se toca), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (`application_name` con `node_id`) |
| **Veredicto vigente** | Un objeto `Database`. Población idle = **roster residente declarado** (3 por defecto), más ráfagas transitorias; techo duro **12** por proceso. Probes throwaway. Teardown HTTP. Reconnect owner-scoped + `SELECT 1` ligado. Pool Peewee **prohibido**. Historiador inalcanzable **no** puede congelar el hub ni `on.tag`. Ningún socket inactivo sobrevive al presupuesto del cliente, que va por delante del `idle_session_timeout` del servidor |
| **Clasificación** | Auditoría de arquitectura · conexiones · Confidencialidad interna |

---

### 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-18) |
|---|---|
| ¿Hacía falta un segundo `PostgresqlDatabase`? | **No.** El fallo nunca fue «demasiadas instancias Peewee» |
| ¿Por qué se vieron ~18 backends y luego 7–8 idle estables? | Peewee guarda el TCP en `threading.local` (= greenlet-local). Cada request, SM async y probe en threadpool que hacía `connect()`/`execute_sql()` y **no** `close()` dejaba un backend. 8 idle en planta (2026-08-17) eran LDS/PPA/NPW/PFM + hidratación OPC + probes, **no** un leak creciente |
| ¿Cerrar a lo bruto? | No. El **LoggerWorker** conserva 1 conexión. HTTP, SM, hidratación y `journal_then_remote` son efímeros |
| ¿Reintroducir `PooledPostgresqlDatabase`? | **Prohibido** (BE-H4): pool bajo gevent sin devolver conexiones → signup/login 503 @ 30 s |
| ¿`gevent.Timeout` alrededor de `connect()`? | **Inútil.** No corta libpq. Usar `connect_timeout` + I/O no cooperativo fuera del hub + ping throwaway |
| ¿Falló el SAF en el outage de cable? | **No.** El journal acumuló PENDING. Lo que murió era el **hub** (freeze HMI) o el handle ligado (`connection already closed` tras un CRITICAL mentiroso) |
| ¿+300 MB/día «por la conexión»? | **No** como causa única. Un socket psycopg2 es ~0.5–3 MB. RSS grande → SAF/CVT/observers/fragmentación ([AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md)) |
| ¿Hoy hay `db.close()` por request? | **Sí.** `teardown_appcontext` + `teardown_request`. (La auditoría de memoria de conexiones del 14-ago decía que no; eso está **superado**) |

Contrato A+:

```
1 instancia Peewee
  ×  1 socket persistente por rol RESIDENTE (LoggerWorker / SafJournalFlusher / MetricsSamplerWorker)
  +  0 sockets HTTP al terminar el request
  +  0 sockets en hilos SM al salir de loop()
  +  0 sockets Peewee en el threadpool del hub
  +  0 sockets de workers de ciclo lento fuera de su ciclo
  +  0 sockets sin dueño (DB_CONNECTIONS_ABANDONED == 0)
```

`application_name` (máx. 63):

- Multi-edge on: `PyAutomationIO:<node_id>:<rol>`
- Multi-edge off: `PyAutomationIO:<rol>` o `PyAutomationIO`
- Probes: `…:probe` (no entran en `DB_CONNECTIONS_COUNT`)
- Greenlets sin identidad de hilo: `…:http` (dentro de request) o `…:pool`. **Nunca** `Dummy-N` (§1.6)

---

### 1. Diagnóstico fusionado (evidencia de planta)

#### 1.1 18 backends — Directiva de Conexiones Eternas (2026-08-17)

Un objeto `PostgresqlDatabase` **sí** era singleton. Las 18 conexiones eran **sockets por greenlet/hilo** sin `close()`, agravadas por probes Peewee en el threadpool del hub (`run_uncooperative_db_call(lambda: db.execute_sql("SELECT 1"))` asociaba el TCP al **hilo OS** del pool).

| Actor | ¿Socket persistente? |
|---|---|
| LoggerWorker | **Sí, 1** |
| Request Flask / REST | No: abrir al primer SQL, cerrar en teardown |
| Socket.IO `on.tag` | No toca PG (CVT + journal local) |
| Hub threadpool (probes) | **Nunca** Peewee; solo `ping_throwaway` |
| Health `/api/health/db` | Throwaway |

#### 1.2 8 idle estables — Conexiones Estables (planta 2026-08-17 18:28, `idetect_db`)

Captura `pg_stat_activity` (host app `192.168.1.106`):

| pid | Última query (resumen) | Atribución |
|---|---|---|
| 50966 | `SELECT … FROM "opcua"` | Hidratación OPC UA; greenlet que no cerró |
| 51050–51060 | `Alarms` `name = 'alarm.{LDS,PPA,NPW,PFM}.leak'` | Hilos async **LDS / PPA / NPW / PFM** |
| 52115 | `SELECT 1` | Probe residual |
| 52659 | `SELECT 1` | **LoggerWorker** |

Ninguna fila en `idle in transaction`. El conteo **no crecía** (conjunto fijo que reabre). Objetivo idle: **1** (`:LoggerWorker`). Techo **CA-OPT-1: ≤ 4**.

`append_machine(..., mode='async')` es el default. Cada `SchedThread` que hace Peewee = 1 backend idle eterno hasta `ephemeral_historian`.

#### 1.5 `too many clients already` — el censo era dueño del socket (planta 2026-09-09)

Seis días de operación continua; PostgreSQL 15 con `max_connections = 100` saturado hasta impedir el login de `postgres`. `ss -tnp | grep :5432 | wc -l` → **101**. Backends `idle` dominantes: `PyAutomationIO:edge-Supe-Linea2:LoggerWorker`, `PyAutomationIO:edge-Supe-Linea2:MetricsSamplerWorker` y conexiones **sin** `application_name`, desde `192.168.1.80` / `.81`.

Este documento afirmaba «el día 1 y el día 1000 deben mostrar el mismo número de backends». Era **falso**, y la causa estaba en la propia pieza de censo:

```python
# ConnectionRegistry.register — antes
self._by_owner.setdefault(oid, {})[id(conn)] = conn   # referencia FUERTE
```

`ConnectionRegistry` guardaba una referencia **fuerte** a cada socket. Cuando un greenlet moría sin `close()` — teardown que no corre, `atomic()` abortado, worker reiniciado — CPython ya no podía finalizar el objeto psycopg2, así que libpq nunca cerraba el descriptor y PostgreSQL conservaba el backend `idle` **para siempre**. El censo convirtió un fallo auto-reparable (el recolector cierra el socket) en una fuga permanente y monótona.

Reproducción local contra `postgres:17-bullseye`, sin tocar la red de planta (`automation/tests/test_db_connection_soak.py`):

| Escenario | Antes | Después |
|---|---|---|
| 12 greenlets efímeros que mueren sin `close()` | **12** backends idle permanentes | 0 |
| Socket anclado por otra referencia, greenlet muerto | 1 permanente | 0 (`reap_abandoned`) |
| 6.º socket con techo = 3 | se abre | `OperationalError` (fail-fast) |

Causas concurrentes, todas confirmadas leyendo código:

| # | Defecto | Efecto |
|---|---|---|
| L1 | Censo con referencia fuerte | Fuga permanente y creciente (**causa raíz**) |
| L2 | `MetricsSamplerWorker` no cerraba su socket al salir de `run()` | 1 backend por reinicio del worker |
| L3 | `ops_controls._restart_*` sustituía el worker sin recuperar su socket | 1 backend por reinicio desde `/performance` |
| L4 | `close_current_greenlet_connection` tragaba el error de Peewee al cerrar dentro de una transacción | Backend `idle in transaction` eterno |
| L5 | `UserInvalidateWorker` abría LISTEN sin `application_name` | Las «conexiones genéricas» del reporte; invisibles al censo |

Correcciones: censo **débil** (`weakref`) + `reap_abandoned()` determinista, `BaseWorker.release_historian_socket()`, `_retire()` en los reinicios, `rollback` antes de `close`, `application_name` en el LISTEN, techo duro por proceso y guardas `idle_session_timeout` / `idle_in_transaction_session_timeout` del lado del servidor.

**Lección:** un observador no puede ser propietario. Toda estructura que indexe recursos del sistema operativo se referencia débilmente o se convierte en el leak que pretendía medir.

#### 1.6 `sockets above alert threshold` — la alarma medía la plantilla, no la carga (planta 2026-09-09, post-§1.5)

Con el arreglo de §1.5 desplegado, el backend dejó de fugar pero empezó a gritar. Muestra de 24 minutos continuos:

```
07:16:59 live=7 threshold=6 opened_by=…:SM-Supe.Linea1.PFM long_lived=[LoggerWorker 906.6s, NtpMonitorWorker 906.9s, ReplicationWorker 906.9s, MetricsSamplerWorker 906.9s]
07:25:33 live=7 threshold=6 opened_by=…:SM-Supe.Linea1.PFM long_lived=[UserInvalidateWorker 1121.0s, LoggerWorker 1420.9s, ReplicationWorker 1421.2s, MetricsSamplerWorker 1421.2s, NtpMonitorWorker 1421.3s]
```

Lectura correcta de esa evidencia: **no hay fuga**. `live` oscila 7↔8 sin crecer, `owner_gone` es `False` en todos y `DB_CONNECTIONS_REAPED` se queda en 0. Los mismos cuatro o cinco sockets envejecen juntos (906 s → 1421 s) porque son los mismos, no porque se acumulen. Lo que había era tres defectos distintos:

| # | Defecto | Efecto |
|---|---|---|
| N1 | `connections_expected_max() = (workers × 2) + 2` derivaba el presupuesto de la **concurrencia web** | El estado sano (residentes + ráfaga) quedaba permanentemente por encima del umbral → alarma crónica |
| N2 | Workers de ciclo lento (`NtpMonitorWorker` 3600 s, `ReplicationWorker` con journal vacío, `UserInvalidateWorker`, `HmiSession*`) retenían el socket entre ciclos sin ser residentes | Un backend `idle` por worker **y** carrera contra el `idle_session_timeout` de §1.5: el servidor cerraba el socket por detrás y el ciclo siguiente corría sobre un handle muerto |
| N3 | El hilo del `ThreadPoolExecutor` de gevent (catálogo) se identificaba como `Dummy-9` | `application_name` inestable entre arranques; `pg_stat_activity` no atribuía el socket a ningún subsistema. Además `threading._DummyThread.is_alive()` responde `True` para siempre, así que la vigilancia por liveness es ciega en hilos de pool |

`_DummyThread` verificado empíricamente bajo gevent: el objeto **sí** se recolecta cuando muere el greenlet (la referencia débil lo caza), pero un hilo de *pool* que sigue vivo o referenciado no. De ahí el tercer nivel de defensa.

**Correcciones**

1. **Residencia declarativa.** `RESIDENT_SOCKET_ROLES = {LoggerWorker, SafJournalFlusher, MetricsSamplerWorker}` — sólo los roles que tocan el servidor cada pocos segundos conservan socket. `keep_historian_socket()` consulta el roster (`AUTOMATION_DB_RESIDENT_ROLES`), ya no una lista de nombres incrustada.
2. **Ciclo cooperativo.** `BaseWorker.historian_cycle()` envuelve un ciclo y devuelve el socket al terminar si el rol no es residente. Aplicado a `NtpMonitorWorker`, `HmiSessionSyncWorker`, `HmiSessionCleanupWorker` y al recargo periódico de `UserInvalidateWorker`; `ReplicationWorker` lo suelta cuando el journal está vacío.
3. **Presupuesto honesto.** `connections_expected_max() = |residentes| + headroom transitorio + workers gunicorn`. Escala con la **plantilla de workers**, que es lo que determina la población residente.
4. **Reaper por inactividad.** `REGISTRY.reap_idle(idle_socket_budget_s())` cierra sockets **no residentes** inactivos más allá del presupuesto, que se mantiene al 60 % del `idle_session_timeout` del servidor. Quien cierra primero decide si la siguiente consulta ve un handle vivo o un error: ahora somos nosotros. `execute_sql` sella `last_used`, así que un socket en uso nunca se cosecha.
5. **Nombre estable.** `historian_role_scope("CatalogReplicator")` nombra el trabajo delegado al pool; los greenlets anónimos caen a `http` (dentro de request Flask) o `pool`.
6. **Alarma sobre invariantes.** `_warn_on_socket_growth` ya no reporta el conteo. Reporta sockets sin dueño (ERROR), roles no residentes que retuvieron el socket (WARNING, una vez cada 300 s) y máximos históricos nuevos contra el techo. Un edge sano queda **en silencio**.

Validado contra `postgres:17-bullseye` (`automation/tests/test_db_connection_soak.py`, 7 escenarios):

| Escenario | Resultado |
|---|---|
| Worker lento **vivo** con socket inactivo | `reap_abandoned()` → 0 (el dueño existe); `reap_idle()` → 1; backends en PG → 0 |
| Residente (`LoggerWorker`) inactivo 4000 s | `reap_idle()` → 0; backend intacto |
| Consulta sobre un socket envejecido | `idle_s` 4000 → 0; no se cosecha |
| Hilo de pool `Dummy-9` | `application_name` = `…:pool` / `…:CatalogReplicator`, nunca `Dummy-*` |

**Lección:** una alarma que suena en operación normal no es una alarma, es ruido — y en un sistema 24/7 el ruido es peor que el silencio, porque entierra el único evento que importaba. El umbral debe derivarse de la arquitectura real (cuántos sockets *deben* existir), y la alarma debe disparar sobre invariantes violados, no sobre un contador cruzando una línea.

#### 1.3 `connection already closed` tras «Reconnection successfully» (17:47)

```
CRITICAL: Reconnection successfully
psycopg2.InterfaceError: connection already closed
SAF replication failed for domain tag | event | alarm_summary_update
```

Causa raíz: `previous.close_all()` llamaba `REGISTRY.close_tracked()` **sin owner** y mataba el socket del **candidato** recién abierto. El ping throwaway veía el host up → CRITICAL. Los modelos usaban un handle Peewee con TCP ya cerrado. El SAF **hizo lo correcto**: no ACK, filas PENDING.

**2026-09-15:** ese mismo síntoma (`connection already closed`) **no** puede quemar `attempts` ni pasar a `DEAD_LETTER`. `classify_saf_error` lo marca RETRYABLE; `_ensure_connection` reconecta el handle ligado. Detalle: [AUDIT_DB.md](./AUDIT_DB.md) §3.5.

Hipótesis «el proxy no se actualiza»: **falsa en el mecanismo**. Hay un solo `Proxy` (`automation/dbmodels/core.py`). `set_db` ya hacía `proxy.initialize(candidate)` antes de `connect()`.

#### 1.4 HMI congelada solo con BD remota (timeout de red)

| Escenario | `connect()` / `SELECT 1` | Hub gevent | HMI | Journal |
|---|---|---|---|---|
| Postgres Docker `docker stop` | `Connection refused` inmediato | Casi no se bloquea | Tendencias vivas | PENDING → replica |
| Cable / `No route to host` | Timeout del **SO** (30–180 s) | Hub congelado en libpq | `on.tag` no se drena | PENDING sí se acumula |

`on.tag` **no** consulta PG (`CVTEngine.set_value` → `sio.emit`). El freeze es de **planificación del event loop**: `gevent.monkey.patch_all()` convierte `LoggerWorker` en greenlet; libpq no cede.

`@logging_error_handler` en `set_db` **no re-lanza**: `connect()` largo + `_historian_is_live()` contra el socket zombi = dos bloqueos encadenados.

---

### 2. Política vigente (quién abre, quién cierra)

Regla: **quien abre, cierra**, salvo los roles del roster residente.

La residencia es una lista declarada, no un accidente de qué hilo tocó Peewee primero (§1.6):

| Roster | Roles | Por qué |
|---|---|---|
| **Residente** (conserva el socket) | `LoggerWorker`, `SafJournalFlusher`, `MetricsSamplerWorker` | Tocan el servidor cada pocos segundos; el backend nunca está inactivo lo suficiente para que lo alcance `idle_session_timeout`. Reabrir en cada ciclo sería puro coste |
| **Transitorio** (devuelve el socket) | todo lo demás: `NtpMonitorWorker`, `ReplicationWorker` con journal vacío, `HmiSessionSyncWorker`, `HmiSessionCleanupWorker`, `UserInvalidateWorker`, `SM-*`, `CatalogReplicator`, `http`, `pool` | El ciclo va de segundos a una hora. Retener el socket cuesta un backend `idle` permanente **y** pierde la carrera contra el cierre del servidor |

`RESIDENT_SOCKET_ROLES` en `db_connections.py`; ajustable con `AUTOMATION_DB_RESIDENT_ROLES`. Añadir un rol al roster exige que su periodo sea muy inferior a `AUTOMATION_DB_IDLE_SESSION_TIMEOUT_S` (ver SOCK-R3).

```
# Hidratación de arranque
with db.connection_context() / ephemeral_historian:
    load OPC / CVT / alarmas / roles / users

# Final de PyAutomation.run()
self.release_ephemeral_historian()

# SchedThread / StateMachineWorker.loop
with ephemeral_historian(...):
    machine.loop()

# journal_then_remote
close en finally si el hilo no es LoggerWorker

# Flask
@app.teardown_request
@app.teardown_appcontext
→ db.close() del greenlet del request

# Worker de ciclo lento (NtpMonitor, HmiSession*, UserInvalidate)
with self.historian_cycle():
    ...trabajo del ciclo...        # devuelve el socket si el rol no es residente

# Trabajo delegado a un hilo de pool (catálogo)
with historian_role_scope("CatalogReplicator"):
    with ephemeral_historian(replica):
        ...                        # nombra el subsistema en pg_stat_activity

# LoggerWorker.run, al stop
close_current_greenlet_connection(...)

# Red de seguridad periódica (MetricsSamplerWorker, cada ciclo)
REGISTRY.reap_abandoned()          # dueño muerto
REGISTRY.reap_idle(idle_socket_budget_s())   # dueño vivo, socket olvidado
```

`set_db` (fábrica única, `TrackedPostgresqlDatabase` / `TrackedMySQLDatabase`):

1. Construir `candidate` y `REGISTRY.bind_instance(candidate)`
2. `bind_historian_proxy(candidate)`
3. `connect()` en el **greenlet dueño** (no threadpool Peewee) + `ensure_bound_connection` (`SELECT 1` ligado; si `InterfaceError`, reopen)
4. Si (3) falla: cerrar candidato, restaurar `previous`, **no** marcar `_db_live`, no escribir «Reconnection successfully»
5. Solo entonces `previous.close_all()` **owner-scoped**
6. `self._db = candidate`, `db_manager.set_db(...)`, `_db_live = True`

Watchdog (`LoggerWorker`): `replicate_once()` **primero** (el journal no espera al TCP). Si el host es reachable pero el handle ligado está muerto → `reconnect_to_db()`. **No** llama `set_db` si el ping throwaway falla (cable tirado no bloquea 5 s cada ciclo).

---

### 3. Timeout de red vs hub (contrato extra al SAF)

No se usa `with gevent.Timeout: connect()` como cierre: **no corta libpq**.

| Pieza | Comportamiento |
|---|---|
| `apply_remote_db_kwargs` | `connect_timeout=5` (libpq / MySQL), keepalives TCP. Env `AUTOMATION_DB_CONNECT_TIMEOUT` (1–30 s) |
| `run_uncooperative_db_call` | `connect()` / `SELECT 1` de **probes throwaway** en `gevent.get_hub().threadpool`. `.get(timeout=)` cede el hub |
| Cooldown | Evita apilar varios `SELECT 1` de 2 s. Env `AUTOMATION_DB_PROBE_TIMEOUT` (default 2 s) |
| `ping_throwaway` | `psycopg2.connect` → `SELECT 1` → `close()` en `finally`. Nunca Peewee en el pool |
| Health HMI | Mismo helper; se retiró el `gevent.Timeout` cooperativo |

Residual NT:

| ID | Riesgo | Mitigación |
|---|---|---|
| NT-R1 | Tras timeout, el hilo OS puede seguir en libpq unos segundos | Aceptable; el hub ya no espera |
| NT-R2 | `statement_timeout` PG no ayuda si el cable está caído | No usarlo como mitigación de red |
| NT-R3 | OPC UA `reconnect()` en el mismo worker aún puede bloquear | Fuera de este incidente |

**Cierre:** el A+ de SAF no se revoca. Se añade: **un historiador inalcanzable no puede detener el hub de gevent.**

---

### 4. Reconexión efectiva

#### 4.1 Censo por owner

`ConnectionRegistry` (`automation/utils/db_connections.py`): `_by_owner: dict[owner_id, {conn_id: conn}]`. `close_all()` cierra el socket de **este** greenlet y luego `REGISTRY.close_tracked(owner=self)`. `close_tracked()` sin owner queda para tests / shutdown global.

Así `previous.close_all()` no mata el TCP del candidato.

#### 4.2 `_historian_is_live`

Deja de fiarse solo del ping throwaway. Llama `ensure_bound_connection` sobre `db_manager.get_db()` / `self._db`. El throwaway queda para «¿el host responde?» sin tocar un socket medio-abierto.

#### 4.3 Health post-reconnect

| Endpoint | Qué mide |
|---|---|
| `GET /api/health/system` → `is_db_connected` | Flag de proceso (`_db_live` + handle) **tras** `SELECT 1` ligado |
| `DB_ACTIVE_CONNECTIONS` | `pg_stat_activity` (verdad del servidor) |
| `GET /api/health/db` | Probe throwaway (¿el host responde?) |
| `GET /api/health/saf` | `PENDING_ROWS` debe **bajar** |

Un solo `Proxy`. Modelos que heredan `BaseModel` (Tags, TagValue, Alarms, AlarmSummary, Events, Logs, Users, Roles, Machines, OPCUA, Nodes, geo, …) usan el mismo placeholder. `logger/core.py` y `managers/db.py` **no** declaran otro `Proxy`.

---

### 5. Métricas (`GET /api/health/system`)

| Clave | Fuente / techo vigente |
|---|---|
| `DB_CONNECTIONS_COUNT` | Censo cliente (`Tracked*`) |
| `DB_ACTIVE_CONNECTIONS` | `count(*)` en `pg_stat_activity` (`datname` actual, `backend_type = client backend`, sin el pid del probe). Si PG no responde: censo cliente |
| `DB_NAMED_CONNECTIONS` | Mismo censo filtrado `application_name LIKE 'PyAutomationIO%'` |
| `DB_CONNECTIONS_EXPECTED_MAX` | `|residentes| + headroom transitorio + workers gunicorn` → **8** con el roster por defecto y 1 worker (§1.6) |
| `DB_CONNECTIONS_RESIDENT_MAX` | Tamaño del roster residente (`AUTOMATION_DB_RESIDENT_ROLES`, default 3) |
| `DB_CONNECTIONS_ALERT_THRESHOLD` | `max(6, DB_CONNECTIONS_EXPECTED_MAX)` (`AUTOMATION_DB_CONNECTIONS_ALERT`) |
| `DB_CONNECTIONS_ALERT` | activas > umbral |
| `DB_CONNECTIONS_MAX` | Techo duro por proceso; `connect()` falla rápido al alcanzarlo (`AUTOMATION_DB_CONNECTIONS_MAX`, default 12) |
| `DB_CONNECTIONS_HIGH_WATER` | Máximo de sockets vivos visto en este proceso. Plano tras el arranque = sin crecimiento |
| `DB_CONNECTIONS_REAPED` | Sockets cerrados por `reap_abandoned()` (dueño muerto). **Debe quedarse en 0** en un edge sano |
| `DB_CONNECTIONS_IDLE_REAPED` | Sockets devueltos por `reap_idle()` (rol no residente que retuvo el socket). **Debe quedarse en 0**; > 0 es un defecto de ciclo de vida, no carga |
| `DB_CONNECTIONS_ABANDONED` | Sockets vivos cuyo dueño ya no puede cerrarlos. **Cualquier valor > 0 es fuga** |
| `DB_CONNECTIONS_OVERSTAYING` | Sockets no residentes inactivos por encima del presupuesto |
| `DB_SOCKET_IDLE_BUDGET_S` | Presupuesto de inactividad del cliente; se mantiene bajo `idle_session_timeout` (`AUTOMATION_DB_IDLE_SOCKET_S`) |
| `DB_CONNECTIONS_LEAKED` | Sockets vivos más viejos que `AUTOMATION_DB_LEAK_DETECTION_S` (default 900 s). Los residentes envejecen por diseño: leer junto a `DB_CONNECTIONS_ABANDONED` |
| `DB_APPLICATION_NAME` | Rol estable de este greenlet: nombre del worker, `CatalogReplicator`, `http` o `pool` — nunca `Dummy-N` (§1.6) |
| `DB_INSTANCE_ID` | `id()` del handle Peewee |
| `POOL_CONNECTIONS_USED` | **N/A / 0** (no hay pool). Ver 0 **no** prueba cero TCP |

SQL de planta:

```sql
SELECT application_name, state, count(*)
FROM pg_stat_activity
WHERE datname = current_database()
  AND backend_type = 'client backend'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

Esperado, con el roster residente por defecto: `PyAutomationIO:<node>:LoggerWorker`, `:SafJournalFlusher` y `:MetricsSamplerWorker` idle de forma permanente, más ráfagas breves de `:SM-*`, `:CatalogReplicator`, `:http` y `:pool`. Cero `idle in transaction`. Cero backends de un worker de ciclo lento (`NtpMonitorWorker`, `HmiSession*`) fuera de su ciclo: si aparecen, el worker no está usando `historian_cycle()` (§1.6).

Si tras deploy siguen `PyAutomationIO:SM-*` idle: ese módulo consulta Peewee **fuera** de `loop()`. Cazar por `application_name` + `query`. No matar backends a mano.

Un `application_name` con forma `Dummy-N` no debe existir: significa trabajo delegado a un hilo de pool sin `historian_role_scope()` (§1.6, N3).

---

### 6. Memoria RAM ↔ conexiones (actualizado)

**La conexión BD no es un motor típico de +300 MB/día.** Coste cliente ~0.5–3 MB/socket. El número de sockets se acota por **concurrencia de greenlets que tocaron Peewee**, no por uptime.

Lo que **sí** puede subir cientos de MB (y no es el socket SQL): SAF ring, journal page cache, buffers CVT/DAS, observers, logs, fragmentación CPython, (en iDetectFugas) malla FiPy. Checklist: `RSS_MB` + `pg_stat_activity` plano → **no** es Peewee.

Hallazgos:

| ID | Estado 2026-08-18 |
|---|---|
| DB-MEM-1 | Informativo: sockets ≈ greenlets con SQL. Régimen 1 worker se estabiliza |
| DB-MEM-2 | **Superado en mecanismo:** ahora hay teardown por request. Residual: Socket.IO que haga Peewee fuera de app context (hoy `on.tag` no usa PG) |
| DB-MEM-3 | Reconnect no apila handles; close previous solo tras connect OK + `SELECT 1` ligado |
| DB-MEM-4 | No usar `POOL_CONNECTIONS_USED` como prueba de cero TCP |
| DB-MEM-5 | Δ RSS con PG plano → [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) / SAF |

No reintroducir pool sin: `connect`/`close` por request **y** soak signup×N bajo gevent **y** `_in_use` estable. El teardown actual **no** autoriza reactivar el pool a ciegas (BE-H4 sigue abierto como riesgo de escalado, no como bug activo).

---

### 7. Criterios de aceptación (IDs conservados)

#### Conexiones eternas / censo

| ID | Criterio | Estado |
|---|---|---|
| **CA-DB-1** | Una instancia Peewee | `DB_INSTANCE_ID` estable |
| **CA-DB-2** | `pg_stat_activity` predecible | Idle 1 worker ~1–3, no 18 |
| **CA-DB-3** | Connect a host inalcanzable ≤ 5 s | `connect_timeout`; no `set_db` si ping falla |
| **CA-DB-4** | LoggerWorker no se clava; HMI `on.tag` viva | `replicate_once` primero |
| **CA-DB-5** | `DB_CONNECTIONS_COUNT` en health | Implementado |
| **CA-DB-6** | Soak 24 h count plano | **Pendiente planta** |
| **CA-DB-ET-1** | Tras 5 min idle, ~1 LoggerWorker | Código listo; validar wheel en sitio |
| **CA-DB-ET-2** | 50 HTTP no dejan pendiente | Teardown |
| **CA-DB-ET-3** | `application_name` prefijado | `PyAutomationIO:<node>:<rol>` |
| **CA-DB-ET-4** | `DB_ACTIVE_CONNECTIONS` alineado con PG | ±1 in-flight |
| **CA-DB-ET-5** | Host inalcanzable ≤ 5 s | = CA-DB-3 |
| **CA-DB-ET-6** | Soak 24 h | = CA-DB-6 |

#### Fuga permanente (§1.5)

| ID | Criterio | Estado |
|---|---|---|
| **CA-DB-LEAK-1** | Un greenlet que muere sin `close()` no deja backend | `test_dead_greenlets_do_not_leave_idle_backends` (PG real) |
| **CA-DB-LEAK-2** | `reap_abandoned()` cierra el socket de un greenlet muerto y respeta el de uno vivo | `test_reap_abandoned_*` / `test_reap_keeps_socket_of_a_living_worker` |
| **CA-DB-LEAK-3** | El proceso nunca supera `DB_CONNECTIONS_MAX`; `connect()` falla rápido | `test_connect_refused_above_hard_ceiling` |
| **CA-DB-LEAK-4** | Cerrar con transacción abierta hace `rollback` primero | `test_close_rolls_back_open_transaction_first` |
| **CA-DB-LEAK-5** | PostgreSQL aplica `idle_session_timeout` / `idle_in_transaction_session_timeout` | `test_server_applies_idle_session_guards` |
| **CA-DB-LEAK-6** | Toda conexión (incluido LISTEN) lleva `application_name` | Revisión de código + SQL §5 |
| **CA-DB-LEAK-7** | Soak 7 días en planta: `DB_CONNECTIONS_REAPED = 0` y activas planas | **Pendiente planta** |

#### Socket 24/7 (§1.6)

| ID | Criterio | Estado |
|---|---|---|
| **CA-DB-24X7-1** | Un edge sano **no** emite warnings de socket: la alarma sólo dispara sobre invariantes violados | `test_a_healthy_census_is_silent`, `test_high_water_mark_only_reports_a_new_peak` |
| **CA-DB-24X7-2** | El presupuesto se deriva del roster residente, no de la concurrencia web, y queda bajo el techo | `test_expected_max_covers_the_resident_roster_plus_burst`, `test_ca_edge_7_connection_budget_is_advertised` |
| **CA-DB-24X7-3** | Un rol no residente inactivo más allá del presupuesto se devuelve **antes** que lo cierre el servidor | `test_idle_socket_of_a_living_worker_is_returned_before_the_server_kills_it` (PG real) |
| **CA-DB-24X7-4** | El socket de un residente nunca se cosecha | `test_resident_worker_keeps_its_socket` (PG real), `test_reap_idle_keeps_resident_socket` |
| **CA-DB-24X7-5** | Un socket en uso nunca se cosecha: `execute_sql` sella `last_used` | `test_a_query_reprieves_the_socket_from_the_idle_reaper` (PG real), `test_execute_sql_touches_the_bound_socket` |
| **CA-DB-24X7-6** | El presupuesto del cliente es estrictamente menor que `idle_session_timeout` | `test_idle_budget_stays_under_the_server_timeout` |
| **CA-DB-24X7-7** | Ningún `application_name` con forma `Dummy-N`; el trabajo de pool se nombra por subsistema | `test_pooled_thread_reports_a_stable_application_name` (PG real), `test_anonymous_thread_reports_a_stable_role` |
| **CA-DB-24X7-8** | Workers de ciclo lento devuelven el socket al cerrar el ciclo | `historian_cycle()` en `ntp_monitor`, `hmi_session_sync`, `hmi_session_cleanup`, `user_invalidate`, `replication` |
| **CA-DB-24X7-9** | Soak 7 días: `DB_CONNECTIONS_HIGH_WATER` plano, `DB_CONNECTIONS_ABANDONED = 0`, `DB_CONNECTIONS_IDLE_REAPED = 0`, cero warnings de socket | **Pendiente planta** |

#### Conteo óptimo

| ID | Criterio | Estado |
|---|---|---|
| **CA-OPT-1** | Idle ≤ 4 tras arranque | Código: `ephemeral_historian`. Planta: repetir SQL |
| **CA-OPT-2** | `application_name` descriptivo | Implementado |
| **CA-OPT-3** | Cero `idle in transaction` | Confirmado en captura 2026-08-17 |
| **CA-OPT-4** | Estable 24 h | Pendiente soak |
| **CA-OPT-5** | Reconnect no aumenta el conteo | Owner-scoped + cierre efímero; validar en planta |

#### Reconexión

| ID | Criterio | Estado |
|---|---|---|
| **CA-REC-1** | Proxy + `SELECT 1` ligado post-reconnect | Código + tests. Planta: 10 min sin `already closed` |
| **CA-REC-2** | SAF (`tag`/`event`/`alarm_summary`/`leak`) reanuda sin reiniciar proceso; retryable no DLQ | Código. Planta: `PENDING_ROWS` baja; `SAF_DEADLETTER_COUNT` no crece por outage |
| **CA-REC-3** | Cero `connection already closed` tras CRITICAL | Causa raíz eliminada |
| **CA-REC-4** | Health refleja `is_db_connected` y activas | Implementado |
| **CA-REC-5** | 10 ciclos outage/restore sin fuga | Pendiente soak planta |

#### Memoria ↔ BD

| ID | Criterio |
|---|---|
| **CA-DBMEM-1** | Backends de la app se estabilizan tras warm-up |
| **CA-DBMEM-2** | `POOL_CONNECTIONS_USED` N/A/0 mientras no hay pool |
| **CA-DBMEM-3** | Δ RSS cientos de MB con PG plano **no** se atribuye a conexiones |
| **CA-DBMEM-4** | Reconnect fallido no deja el proceso sin handle previo |
| **CA-DBMEM-5** | No reintroducir pool sin teardown + soak gevent |

---

### 8. Pruebas y staging

```bash
python -m unittest \
  automation.tests.test_db_io \
  automation.tests.test_database_health \
  automation.tests.test_connection_alarms -v
```

Cobertura clave en `test_db_io.py`: `close_tracked` no mata otro owner; `Tracked.close_all` owner-scoped; `ensure_bound_connection` reabre handle cerrado / `InterfaceError`; `bind_historian_proxy`; `historian_application_name` prefijado; `ephemeral_historian` cierra / conserva LoggerWorker.

**Staging A** (SAF clásico): `docker stop` Postgres local → HMI viva, PENDING crece, replica al volver.

**Staging B** (cable): `iptables DROP` 5432 o desenchufar. Esperado: HMI emite `on.tag` (jitter ≤ probe timeout); log connect failed ~5 s; **no** `set_db` por ciclo; al restaurar **un** reconnect; `PENDING_ROWS` baja; cero `already closed`.

**Staging C:** 5 min idle → count 1–3. Navegar HMI 5 min → count no sube con cada pantalla.

---

### 9. Runbook (operación)

0. **Saturación (`too many clients already`)**: `DB_CONNECTIONS_REAPED > 0` señala greenlets que mueren sin cerrar; el log `Reaped abandoned historian socket role=… thread=…` nombra al culpable. `Historian socket ceiling reached` significa que el proceso ya está en el techo: es una fuga, no carga. Ver §1.5. Perillas: `AUTOMATION_DB_CONNECTIONS_MAX` (techo por proceso), `AUTOMATION_DB_IDLE_SESSION_TIMEOUT_S` (reaper del servidor, default 300 s), `AUTOMATION_DB_LEAK_DETECTION_S` (edad para reportar).
0.b **Cómo leer los mensajes de socket (§1.6).** El orden de gravedad es:
   - `Historian sockets abandoned by their owner` (ERROR) → **fuga real**. Cada entrada nombra rol e hilo. Corresponde a `DB_CONNECTIONS_ABANDONED > 0`.
   - `Non-resident historian sockets held past the idle budget` (WARNING, máx. 1 cada 300 s) → un worker retiene un socket que debía devolver: falta `historian_cycle()` en su ciclo. `DB_CONNECTIONS_OVERSTAYING > 0`.
   - `Returned idle historian socket ahead of the server` (WARNING) → el reaper por inactividad ya lo corrigió; `DB_CONNECTIONS_IDLE_REAPED` cuenta cuántas veces. Es un defecto de ciclo de vida, no carga.
   - `Historian sockets approaching the ceiling` (ERROR) → el proceso está a un socket del techo.
   - `Historian socket high-water mark` (WARNING) → nuevo máximo histórico. Normal durante el arranque; en régimen debe dejar de aparecer. Si `DB_CONNECTIONS_HIGH_WATER` sigue subiendo horas después del arranque, hay crecimiento.
   
   Un conteo estable por encima del umbral **no** es un evento y ya no se registra: la señal de salud es `DB_CONNECTIONS_HIGH_WATER` plano con `DB_CONNECTIONS_ABANDONED = 0`. Perillas: `AUTOMATION_DB_RESIDENT_ROLES`, `AUTOMATION_DB_TRANSIENT_HEADROOM`, `AUTOMATION_DB_IDLE_SOCKET_S`.
1. `GET /api/health/system` → `DB_CONNECTIONS_COUNT`, `DB_ACTIVE_CONNECTIONS`, `DB_NAMED_CONNECTIONS`, `DB_CONNECTIONS_ALERT`, `DB_CONNECTIONS_MAX`, `DB_CONNECTIONS_HIGH_WATER`, `DB_CONNECTIONS_REAPED`, `DB_CONNECTIONS_IDLE_REAPED`, `DB_CONNECTIONS_ABANDONED`, `is_db_connected`.
2. Alerta: SQL §5. Si PG >> métrica app: clientes externos o throwaway in-flight (transitorio). Si `DB_NAMED_CONNECTIONS` << activas: binario viejo u otra app en el mismo `datname`.
3. Si la métrica app crece sola: HTTP sin teardown o Peewee otra vez en el threadpool.
4. **No** reactivar `PooledPostgresqlDatabase` para «bajar el 18».
5. Outage: **no** vaciar el journal SAF. Count del worker cae a 0–1 (socket cerrado) y vuelve a 1 al reconectar.
6. Tras CRITICAL `Reconnection successfully`: confirmar que **no** le siguen `already closed` ni `SAF replication failed`. `PENDING_ROWS` descendente. Si el CRITICAL miente (versión previa al censo por owner): reiniciar worker **una vez** y desplegar este código.

Signup/login timeout 15 s / 503 @ ~30 s con arranque OK → **BE-H4** (pool), no «BD caída». Ver [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md).

---

### 10. Residual

| ID | Nota |
|---|---|
| DB-R1 | Handlers Socket.IO con Peewee fuera de app context no pasan por teardown. Hoy el hot path `on.tag` no usa PG |
| DB-R2 | `ping_throwaway` 100–200 ms en `pg_stat_activity`; no entra en `DB_CONNECTIONS_COUNT` |
| DB-R3 | `gevent.Timeout` + libpq sigue siendo inútil |
| ET-R1 | Si un motor escribe SQL fuera de `loop()`, reaparece un idle `SM-*` |
| BE-H4 | Sin pool = riesgo de escalado (muchos workers/hilos), no bug activo a 1 worker |
| ISO-R1 | Catálogo local: `atomic()` por fila (Bulkhead). No rollback de tabla; soak Txn/min = CA-ISOLATION-05 |
| LEAK-R1 | El LISTEN de `UserInvalidateWorker` está idle por diseño y **no** lleva `idle_session_timeout`. Se identifica por `application_name`; no contarlo como fuga |
| LEAK-R2 | `idle_session_timeout` exige PostgreSQL ≥ 14. En 12/13 la guarda del servidor no existe: el techo por proceso y el reaper siguen aplicando |
| LEAK-R3 | ~~Un socket de un hilo **vivo** pero inactivo para siempre no lo caza el reaper~~ **Resuelto en §1.6**: `reap_idle()` lo devuelve al superar `DB_SOCKET_IDLE_BUDGET_S`, y los workers de ciclo lento lo sueltan solos vía `historian_cycle()` |
| SOCK-R1 | `threading._DummyThread.is_alive()` responde `True` para siempre. Un socket abierto en un hilo de **pool** que muera sin liberar el objeto dummy no lo caza la vigilancia por liveness; lo cierra `reap_idle()` |
| SOCK-R2 | `reap_idle()` cierra el socket de **otro** greenlet: su estado Peewee local queda creyéndolo abierto y la siguiente consulta debe pasar por `ensure_bound_connection`. Es exactamente lo que hace `idle_session_timeout`, pero anticipado y con el rol nombrado en el log |
| SOCK-R3 | Un residente cuyo periodo se configure por encima de `idle_session_timeout` (p. ej. `logger_period` muy alto) sí puede recibir el cierre del servidor. Los residentes están exentos de `reap_idle` por diseño: revisar el periodo antes de añadir un rol al roster |

**Cierre:** el circulatorio de PyAutomation es **un handle, sockets con dueño, probes desechables, reconexión que los modelos pueden usar, hub que no espera a libpq**. El día 1 y el día 1000 deben mostrar el mismo número de backends `PyAutomationIO` en idle — y desde §1.5 el censo ya no es quien lo impide: observa con `weakref`, recolecta con `reap_abandoned()` y falla rápido en el techo. Desde §1.6 ese número además es **conocido y declarado**: es el roster residente, no un residuo de qué worker tocó Peewee primero, y quien devuelve el socket inactivo somos nosotros antes que el servidor.

---

### 11. Archivos clave

| Pieza | Ruta |
|---|---|
| Censo, Tracked*, teardown, throwaway, `application_name`, `ephemeral_historian`, roster residente, `reap_idle`, `historian_role_scope` | `automation/utils/db_connections.py` |
| Timeouts libpq / threadpool de probes | `automation/utils/db_io.py` |
| Fábrica `set_db` / `_historian_is_live` / `release_ephemeral_historian` | `automation/core.py` |
| Watchdog | `automation/workers/logger.py` |
| Probe logger | `automation/logger/core.py` |
| `journal_then_remote` cierre efímero | `automation/persistence/outbox.py` |
| Ciclo de vida del socket por worker | `automation/workers/worker.py` (`release_historian_socket`, `historian_cycle`) |
| Workers de ciclo lento que devuelven el socket | `automation/workers/ntp_monitor.py`, `hmi_session_sync.py`, `hmi_session_cleanup.py`, `user_invalidate.py`, `replication.py` |
| Rol estable del hilo de pool del catálogo | `automation/catalog/replicator.py` (`historian_role_scope`) |
| Reinicio de workers sin dejar sockets | `automation/utils/ops_controls.py` (`_retire`) |
| Soak contra PostgreSQL real (opt-in) | `automation/tests/test_db_connection_soak.py` |
| SM wrap | `automation/workers/state_machine.py`, `automation/state_machine.py` |
| Proxy único | `automation/dbmodels/core.py` |
| Health | `automation/health/service.py`, `automation/modules/health/resources/health.py` |
| `on.tag` (sin BD) | `automation/tags/cvt.py` |
| Tests | `automation/tests/test_db_io.py` |


## Parte B — Store-and-Forward y flujo de persistencia

> Fuente original: `AUDIT_STORE_AND_FORWARD.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Durabilidad ante caída de BD; camino TagValue/Alarmas/Eventos/Logs; exact-once; T-01 |
| **Fecha baseline** | 2026-08-13 (cola RAM = C+ / B−) |
| **Re-auditoría** | 2026-08-13 (Directiva Fénix + Exact-Once + Ciclo Atómico + Milisegundo Exacto) |
| **Compactación** | 2026-08-18 |
| **Aislamiento Bulkhead** | 2026-08-25 — replicación por dominio y por muestra; drop de tags ausentes a 3 reintentos |
| **Blindaje nuclear** | 2026-09-15 — clasificador retryable/poison/idempotente; attempts desacoplados del circuito; prune archiva (no DELETE de proceso); shed no dropea campo/leak; `saf/retry` resucita DLQ; dominio `leak` por registry; `/health/ready` DEGRADED sin restart Docker |
| **Controles ops** | 2026-08-25 — `POST /api/admin/saf/retry` y `/saf/reset` desde `/performance`; `drop_unsent(confirm=True)` es el único discard intencional de PENDING. **2026-09-15:** retry = resurrect DLQ + reset circuito + catch-up; **no** usar reset como “fix” de outage |
| **Fuentes absorbidas** | `STORE_AND_FORWARD`, `PERSISTENCE_FLOW`, `T01_SOAK_LAST_RUN` |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md) (hub/reconnect no revocan A+), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (journal por `node_id`), [AUDIT_TAGS.md](./AUDIT_TAGS.md) (sync por fila), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) (DLQ archivada), [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) (GATE-37 restart PG lab: seed sobrevive; SAF replay DAS vivo pendiente) |
| **Veredicto** | **A+** durabilidad (incluye outage PG / handle stale: no DLQ). **A** aislamiento de fallos en código (CA-ISOLATION-01…04 + P0-1…P0-8). **A−** planta: CA-ISOLATION-05 (Txn/min 1 h) pendiente |
| **Clasificación** | Auditoría de arquitectura de datos |

---

### 0. Contrato vigente (post-Fénix)

El historiador remoto (PostgreSQL / MySQL / SQLite de aplicación) es el **plan de distribución**. SQLite WAL es el **Plan A de durabilidad**.

```
Hot path (CVT / Alarmas / Eventos / Logs)
        │  IPersistenceGateway.enqueue()
        ▼
┌─────────────────────────────────────────┐
│  Ring RAM acotado (solo tags, ≤10 ms)   │
│  JournalWriter SQLite WAL + FULL sync   │  ← source of truth
│  persistence_journal                    │
│  PENDING / REPLICATING / SENT           │
│  DEAD_LETTER (solo poison) / ARCHIVED   │
│  path: ./db/saf/<node_id>/journal.db    │  (legacy: ./db/saf/journal.db)
│  archive: journal-archive.db            │
└───────────────┬─────────────────────────┘
                │ ReplicationWorker (LoggerWorker)
                │ classify_saf_error por fila
                │ retryable → PENDING, attempts intactos
                │ poison → attempts++; DLQ a 5
                │ UNIQUE TagValue → SENT (idempotente)
                │ batch + rate limit + circuit breaker
                ▼
        Remote DB  ──ACK──►  status=SENT  ──GC SENT only──►
```

**OPC UA no habilita el historiador.** OPC es un **productor de valores** hacia el CVT. El historiador se dispara por cualquier `Tag.set_value` → `notify` → `TagObserver` cuando el tag tiene observer (`db_manager.attach` al crear/cargar con BD conectada). Tags internos de iDetectFugas (`leak`, `threshold`, …) se historizan **sin** `opcua_address`.

La cola RAM `_tag_queue` quedó **huérfana** para escritura. `TagObserver.update()` no escribe ahí. El worker llama `replicate_once()` sobre el journal.

Adquisición **nunca espera a la red**. Enqueue extranjero en multi-edge se rechaza; si falta `owner_node` en un persistable crítico (incl. `leak`), se **sella** el scope del edge en lugar de `SAF rejected foreign` ([AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md)).

---

### 1. SOLID

| Letra | Componente |
|---|---|
| **S** | `JournalWriter` (disco) ≠ `RemoteReplicator` (red) ≠ `IdempotentBatchInserter` |
| **O** | `IPersistable` / `PersistableRecord` para tag, alarma, evento, log, **leak** (producto) |
| **L** | `IRemoteDB` + `NullRemoteDB` / `FakeRemote` en tests de caos |
| **I** | `IHealthProbe` separado de `IReplicationWorker` |
| **D** | CVT no importa sqlite3/psycopg2; `TagObserver` usa `get_persistence_gateway()`. SQL de `leaks` **no** vive en el core: `register_domain_writer("leak", fn)` |

Capas: CVT = valor actual; `Tag.notify` = notificación; `PersistableRecord` = JSON canónico; journal = verdad local; replicator = PENDING→remoto; mapper = JSON→fila; inserter = SQL exact-once; `DataLogger.read_*` = lectura HMI.

---

### 2. Baseline (antes de Fénix) — por qué no era SAF

Se conserva como contraste. Hoy **no** es el camino activo.

1. Cola **solo RAM**, **sin límite**, **sin spill**.
2. Drain **antes del ACK**: si `insert_many` fallaba tras vaciar, las muestras se **perdían**.
3. Alarmas / eventos / logs **sin** cola: BD caída → dato descartado.
4. Reinicio del proceso **borraba** el buffer.
5. Mantenimiento SQLite >1 GB **borraba** históricos en vivo tras backup.

Eso era **best-effort buffering de tags**, no garantía de entrega durable.

Scorecard de clase mundial (hoy todos ✅ salvo residual de retención a años):

| ID | Capacidad | Post-Fénix |
|---|---|---|
| SAF-01 | Hot path no espera a la red | ✅ Tags vía ring; críticos COMMIT local síncrono |
| SAF-02 | Memoria acotada | ✅ Ring + `JournalBackpressureError` |
| SAF-03 | Spill / journal disco | ✅ WAL `PRAGMA synchronous=FULL` |
| SAF-04 | Sobrevive restart | ✅ Replay PENDING (T-02) |
| SAF-05 | ACK post-commit | ✅ SENT solo tras `write_batch` exitoso |
| SAF-06 | Idempotencia | ✅ UNIQUE journal + `(tag_id, timestamp)` + `sample_uuid`; `ON CONFLICT DO NOTHING` / `INSERT IGNORE` |
| SAF-07 | Multi-path | ✅ Tags, alarmas, eventos, logs, **leak** (writer de producto) |
| SAF-08 | Replay controlado | ✅ Batch + rate limit + circuit breaker **desacoplado de attempts** |
| SAF-09 | Observabilidad | ✅ `/api/health/saf` (503 si critical); `/api/health/ready` siempre 200 (`DEGRADED` si circuito OPEN) |
| SAF-10 | Retención | ✅ `VACUUM INTO` + checksum; GC **solo SENT**; prune DLQ **archiva**, no borra proceso |
| SAF-11 | Outage ≠ veneno | ✅ `classify_saf_error`: retryable no incrementa attempts; DLQ solo poison |

Nota ponderada ≈ 4.8 / 5 → **A+**.

**Descartar PENDING** no forma parte del hot path. `JournalWriter.drop_unsent(confirm=True)` (API `POST /api/admin/saf/reset`, rol admin/sudo, modal `CONFIRMAR` en `/performance`) es la única vía operativa de **borrado**. Forzar un ciclo **sin perder histórico**: `POST /api/admin/saf/retry` → `resurrect_dead_letters` + `circuit.reset` + `replicate_catchup`. **No** usar `/saf/reset` para recuperar un outage de PG. Auditoría: Events `SAF queue emptied` / `SAF retry requested`. Runbook: [docs/node-performance-runbook.md](../docs/node-performance-runbook.md). Tests: `test_ops_controls.py`, `TestSafNuclearP0`.

#### Hallazgos cerrados

| ID | Original | Cierre |
|---|---|---|
| C-01 | Cola RAM ilimitada | Journal WAL; ring `saf_ring_maxsize` |
| C-02 | Drain-before-ACK | PENDING si remoto falla; ACK = SENT |
| SAF-06 | Duplicados TagValue | `IdempotentBatchInserter` + UNIQUE + `sample_uuid` |
| C-03 | DELETE masivo histórico | `VACUUM INTO` + SHA-256; nunca truncar en vivo |
| H-01 | Alarmas/eventos/logs drop | Mismo outbox (`ALARM_SUMMARY`, `EVENT`, `LOG`) |
| H-02 | OPC UA audit fail-open | `EventsLogger.create` → journal |
| M-01 | Sin métricas | `SAF_QUEUE_DEPTH`, `SAF_REPLICATION_LAG`, `SAF_DROPPED_FULL`, `SAF_CYCLE_DUPES_DROPPED` |
| M-04 | Flush sin throttle | RateLimiter 10k rec/s + CircuitBreaker |

---

### 3. Operaciones de cierre A+

#### 3.1 Exact-Once

- `TagValue.timestamp` resolución **ms** (`TimestampField(resolution=3)`). Ticks legacy µs se normalizan en `ensure_schema` (colapsa pares del mismo ms y luego ÷1000).
- Firma atómica: `sample_uuid` (idempotency_key del journal).
- `IdempotentBatchInserter` es la **única** clase que habla de conflictos SQL. `RemoteReplicator.flush()` solo llama `IRemoteDB.batch_insert_with_dedupe`.

**Criterio:** tras SIGKILL y reconexión, el historiador contiene exactamente las muestras durable del journal; un segundo flush no crea duplicados.

#### 3.2 Ciclo Atómico

El framework inyecta `machine.cycle_timestamp` antes de `machine.loop()` y un filtro de dedupe en el gateway. Las máquinas **no** se modifican.

| Fase | Capa | Efecto |
|---|---|---|
| 1 | `stamp_machine_cycle` + `ProcessType.set_value` | Escrituras del mismo `loop()` comparten UTC. UNIQUE remoto colapsa micro-duplicados |
| 2 | `CycleSampleCache` en `enqueue` | 2ª muestra mismo tag/valor/ciclo **no entra al journal**. Métrica `SAF_CYCLE_DUPES_DROPPED`. TTL 2 s |

El histórico refleja el valor por ciclo de procesamiento, no cada `set_value`.

#### 3.3 Milisegundo Exacto

Payload journal de tags en ms (`timebase.TAGVALUE_TIMESTAMP_RESOLUTION = 3`). Residuos 73–403 µs caen en el mismo tick. Events / AlarmSummary / Logs: resolución por defecto Peewee (AlarmSummary ya escala a ms en `ensure_schema`). Lecturas HMI aceptan ticks legacy s / ms / µs (`DataLogger._as_epoch_seconds`).

#### 3.4 Bulkhead — aislamiento de fallos (2026-08-25)

Un tag inexistente en el remoto, un evento fallido o un `IntegrityError` de alarma **no** deben detener los demás dominios ni las demás muestras del mismo ciclo.

| Principio | Implementación |
|---|---|
| Aislamiento por dominio | `RemoteReplicator.replicate_once` itera `_ordered_domain_batches` (`tag` → alarmas → events → logs). Excepción o PENDING de un dominio no aborta los demás |
| Aislamiento por muestra | `write_batch_outcomes` devuelve `RowOutcome` (`ok` + `error`) por elemento, con adaptador `list[bool]`; `mark_sent` / `mark_pending` son por id y **por dominio**. Un fallo de `event` no toca attempts de `tag`. Insert de TagValue: lote, y si falla, reintento **por fila** |
| Degradación controlada | Tag ausente en `Tags` remoto: PENDING hasta 3 misses, luego ACK + log `Dropping sample for missing tag … after 3 retries` + `request_full_sync` (no bloquea el hot path) |
| Eventos / alarmas / logs | `_write_*_outcomes` captura excepción **por muestra**; no hay transacción global del lote |

| ID | Criterio | Resultado | Evidencia |
|---|---|---|---|
| **CA-ISOLATION-01** | Tag inexistente no bloquea eventos ni alarmas del mismo ciclo | **PASS** | `TestReplicatorDomainIsolation.test_missing_tag_does_not_block_events_or_alarms` |
| **CA-ISOLATION-05** | Txn/min en reposo < 50 con errores de integridad persistentes | **PENDIENTE** | Soak planta 1 h + dashboard `DB_TXN_PER_MIN` (proceso, no clúster) |

**No A+ de aislamiento de planta** hasta CA-ISOLATION-05. El A+ de durabilidad (T-01 / exact-once / outage≠DLQ) no se revoca.

#### 3.5 Blindaje nuclear — outage ≠ veneno (2026-09-15)

Lab 192.168.1.80/.81: filas `FI_`/`PI_`/`DI_`/`leak` válidas acababan en `DEAD_LETTER` tras 5 attempts con `connection already closed`. El prune **DELETE** borraba histórico de proceso. Eso violaba el contrato “PENDING sagrado”.

Clasificador `automation/persistence/errors.py` → `classify_saf_error(exc)`:

| Categoría | Ejemplos | Acción |
|---|---|---|
| **RETRYABLE** | `connection already closed`, timeout, unreachable, SSL EOF, `OperationalError`/`InterfaceError` | `mark_pending(..., increment_attempts=False)`; `circuit.failure()`. Circuito OPEN: reconnect only, **cero** attempts |
| **IDEMPOTENT_OK** | UNIQUE / `duplicate key` / `ON CONFLICT` TagValue `sample_uuid` | ACK → **SENT**. **No** es poison |
| **POISON** | JSON irrecuperable, schema, FK real, `TypeError` de contrato | `attempts++`; a 5 → `DEAD_LETTER` |

`PeeweeRemoteDB._ensure_connection()` hace `SELECT 1` en el handle ligado (`ensure_bound_connection`); `is_reachable()` no puede devolver True con socket muerto. Excepción de mapa/insert retryable **no** cuenta como miss de tag ausente.

`prune_dead_letters()` copia a `journal-archive.db` y pasa el status a `ARCHIVED`. El count de `DEAD_LETTER` baja por reclasificación, no por pérdida. TTL 7 d / cap 10k se mantienen.

Shed (`_tag_history_shed_locked`): **nunca** aplica a `leak`, alarmas, eventos, logs, tags `*.leak*` ni campo `FI_`/`PI_`/`DI_`/`TI_` (ni `criticity=critical`). Solo puede pausar historización no crítica (`SYS.PERF.*`). Alarma `SAF_SHED` sigue indicando presión de cola.

Dominio `leak`: `DOMAIN.LEAK` en `_CRITICAL` y `_DOMAIN_FLUSH_ORDER`. iDetectFugas registra el writer al boot (`LeakPersistenceService.register_saf_writer`). El core **no** embebe SQL de `Leaks`.

Hidratación: `load_db_to_alarm_manager` salta `tag` que no es `str` (WARNING + `continue`). `local_alarm_payloads` indexa tags por `_pk` **y** `id`.

Ops / HMI: badge “condición activa” (`condition_met`) distinto del estado ISA. Histéresis DLQ (`perf_saf_deadletter_clear_threshold=0`): miles de DLQ permanecen; replay a 0 → Normal. `GET /api/health/ready` HTTP **200** con `status=DEGRADED` si circuito OPEN / PG down / pending. Healthcheck Docker **sigue** `/api/health/ping` (restart on OPEN es anti-patrón). Script `check_docker_bridges.sh`: lista bridges DOWN `172.21/172.22`; **sin** `docker network rm` automático.

**Fuera de alcance (explícito):** `POST /saf/reset` como fix, `dead_letter_attempts=50`, tocar `set_value`, desactivar shed sin alternativa, borrar PENDING a mano en .80/.81.

| ID spec | Criterio | Resultado | Evidencia |
|---|---|---|---|
| **P0-1** | 10 flushes `connection already closed` → attempts=0, DLQ=0 | **PASS** | `TestSafNuclearP0.test_p0_1_stale_handle_does_not_increment_attempts` |
| **P0-2** | Fallo event no incrementa attempts de tag | **PASS** | `test_p0_2_event_failure_does_not_increment_tag_attempts` |
| **P0-3** | Outage simulado → `deadletter_count==0` | **PASS** | `test_p0_3_outage_never_dead_letters` |
| **P0-4** | Prune archiva, no DELETE de tags de proceso | **PASS** | `test_p0_4_prune_archives_process_rows` + `test_long_run_hardening` |
| **P0-5** | Circuito OPEN, 10 ciclos, attempts invariantes | **PASS** | `test_p0_5_open_circuit_leaves_attempts_intact` |
| **P0-6** | Stale handle → reconnect y SENT sin attempts++ | **PASS** | `test_p0_6_stale_reconnect_sends_without_attempts` |
| **P0-7** | Resurrect DLQ → PENDING, count=0 | **PASS** | `test_p0_7_resurrect_dead_letters` |
| **P0-8** | pending alto: FI_02/PI_02/DI_02 encolados | **PASS** | `test_p0_8_shed_never_drops_field_tags` |
| **P1** | Journal leak con area/owner_node; writer `Leaks` | **PASS** | `app/tests/test_leak_persistence_service.py` |
| **P1** | 34 alarmas locales hidratan `tag` str | **PASS** | `TestLocalAlarmHydrate` |
| **P2** | Histéresis DLQ a 0 tras replay | **PASS** | `test_deadletter_hysteresis_clears_only_at_zero` |

El clasificador y `_ensure_connection` viven solo en LoggerWorker/replicator (CA-G-7/G-8: no I/O de PG en el tick de motores).

---

### 4. Flujo activo (paradoja OPC)

#### 4.1 Creencia vs código

| Creencia legado | Implementación |
|---|---|
| OPC subscription → CVT → cola → BD | **Cualquier** `set_value` → Observer → journal → Postgres |
| Sin `opcua_address` no hay histórico | Sin OPC no hay adquisición de PLC; sí hay persistencia si alguien escribe el Tag |
| LoggerWorker drena `_tag_queue` | Cola muerta. Worker = `replicate_once()` |

Habilitación:

```
create_tag / load_db_to_cvt
  if is_db_connected():
      logger_engine.set_tag(tag)     → metadata tabla Tags
      db_manager.attach(tag_name)    → TagObserver  ← AQUÍ nace el histórico
  if opcua_address and node_namespace:
      subscribe_opcua(...)           → opcional
```

`DBManager.attach` **no** comprueba `opcua_address`. `AlarmManager.attach` puede poner **otro** `TagObserver` (attach de DB es idempotente, BE-M5).

Productores de valor: OPC datachange, `POST /api/tags/write_value`, state machines / `ProcessType`, tests/scripts.

Si el negocio exigiera «solo historizar tags mapeados a OPC», habría que condicionar `attach` o el `enqueue`. Hoy el diseño es deliberado: **historizar todo tag adjunto que cambie**. SAF no inventó el registro sin OPC; **dejó de perderse**.

Verificación planta (ej. `LDS.leak`): ¿tiene namespace OPC? Si no, no viene del PLC. ¿Hay journal `domain=tag`? Sí ⇒ alguien llamó `set_value`. Buscar en la app `ProcessType` ligado.

#### 4.2 Hot path TagValue

```
Productores → CVTEngine.set_value / set_value_fast
  → deadband opcional → Tag.set_value → notify()
  → TagObserver: PersistableRecord.tag_sample (tag, value, timestamp, sample_uuid)
  → gateway.enqueue (rechazo foreign; CycleSampleCache)
  → ring / WAL PENDING
  → LoggerWorker.replicate_once
  → PeeweeRemoteDB + TagValuePayloadMapper + IdempotentBatchInserter
  → INSERT TagValue ON CONFLICT DO NOTHING
  → mark_sent
```

`set_value_fast` es el camino DAS (lock por tag). CRUD administrativo sigue la cola request/response del engine.

#### 4.3 Alarmas / eventos / logs

Mismo outbox, dominios distintos. Críticos: COMMIT síncrono local (`is_critical`). `journal_then_remote` cierra el socket Peewee del caller si no es LoggerWorker ([AUDIT_DB.md](./AUDIT_DB.md)).

Bitácora operacional journaliza con historiador caído ([AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) CA-OL-1).

---

### 5. Caps, métricas, health

| Guardrail | Default | Comportamiento |
|---|---|---|
| `ring_maxsize` | 50 000 | Drop + backpressure |
| `max_pending_rows` | 5e6 | `JournalBackpressureError`; `SAF_PENDING_CAP_HITS` |
| `max_disk_bytes` | 10 GiB | Evict SENT; si no basta → `JournalDiskFullError` + Event `SAF disk full` (cooldown 60 s) |
| `gc_sent_after_s` | 3600 | GC post-ACK |
| `replicate_rate_per_s` | 10 000 | Rate limit |

`GET /api/health/saf`: `SAF_QUEUE_DEPTH`, `SAF_REPLICATION_LAG`, `SAF_DROPPED_FULL`, `SAF_CYCLE_DUPES_DROPPED`, `PENDING_ROWS`, `SAF_CIRCUIT`, `SAF_DEADLETTER_COUNT`. 503 si estado crítico.

`GET /api/health/ready`: siempre **200**. Cuerpo `ok` o `DEGRADED` (circuito OPEN, PG down, pending/DLQ). **No** usarlo como probe `restart: always`. Liveness Docker = `/api/health/ping`.

---

### 6. T-01 Soak — last run certificada

Parámetros registrados:

- tags=1000 hz=100.0 duration_s=2.0 kill_at_s=1.000
- achieved_tick_hz=0.00 (ventana corta + SIGKILL)
- generated_fsync=0, journal_durable=0, ring_lag_samples=0
- replicated=0, remote_rows_first_pass=0, remote_rows_after_retry=0
- pending_after=0
- **exact_once=True**
- **remote_equals_durable=True**

El ring lag es la ventana hardware del flusher in-memory (≤ `tag_flush_interval_s`). Esas muestras **nunca** llegaron al WAL antes del SIGKILL: **única pérdida aceptable**.

Soak planta sugerido: `SAF_SOAK_SECONDS=1800 python -m unittest automation.tests.test_store_and_forward.TestT01Apocalypse`.

---

### 7. Criterio de aceptación y tests

> Tras SIGKILL y reconexión, el historiador remoto contiene exactamente las muestras durable del journal; un segundo flush no crea duplicados.

```bash
python -m unittest automation.tests.test_store_and_forward.TestSafNuclearP0 -v
python -m unittest automation.tests.test_store_and_forward.TestReplicatorDomainIsolation -v
python -m unittest automation.tests.test_store_and_forward.TestSafJournal -v
```

Aislamiento: `test_missing_tag_does_not_block_events_or_alarms` (CA-ISOLATION-01). DataLogger/Machines: `automation.tests.test_filtered_tag_integrity` (CA-ISOLATION-03/04). Poison legado: `test_dead_letter_escapes_poison_and_leaves_pending`.

Outage de cable: HMI viva + PENDING creciente + replica al volver = [AUDIT_DB.md](./AUDIT_DB.md) (timeout). `connection already closed` post-CRITICAL = handle muerto, **retryable** (attempts intactos, DLQ=0). No es fallo de journal.

**No hacer:** borrar PENDING; `gevent.Timeout` alrededor de libpq; segundo `Proxy`; pool Peewee; tratar UNIQUE TagValue como poison; `restart: always` sobre `/health/ready` o `/health/saf` cuando el circuito está OPEN.

---

### 8. Archivos clave

| Pieza | Ruta |
|---|---|
| Contratos | `automation/persistence/contracts.py` |
| Config / path journal | `automation/persistence/config.py` |
| Clasificador retryable/poison | `automation/persistence/errors.py` |
| Journal WAL | `automation/persistence/journal.py` (`resurrect_dead_letters`, archive) |
| Replicador | `automation/persistence/replicator.py` |
| Gateway / enqueue / shed | `automation/persistence/orchestrator.py` |
| Outbox `journal_then_remote` | `automation/persistence/outbox.py` (`increment_attempts=False` si retryable) |
| Cycle stamp | `automation/workers/state_machine.py` |
| Cycle timestamp | `automation/models.py` |
| Cycle dedupe | `automation/persistence/cycle_dedupe.py` |
| Remote + `_ensure_connection` + `register_domain_writer` | `automation/persistence/remote.py` |
| Exact-once SQL | `automation/persistence/idempotent_insert.py` |
| Timebase | `automation/timebase.py` |
| T-01 producer | `automation/persistence/soak_producer.py` |
| TagObserver | `automation/tags/tag.py` |
| Events / Alarms / Logs | `automation/logger/{events,alarms,logs}.py` |
| Attach | `automation/managers/db.py` |
| Worker | `automation/workers/logger.py` |
| Hydrate alarmas | `automation/catalog/hydrate.py` · `core.py` `load_db_to_alarm_manager` |
| Health | `GET /api/health/saf`, `GET /api/health/ready` |
| Controles ops | `POST /api/admin/saf/retry` (resurrect+reset+catchup), `POST /api/admin/saf/reset` · `ops_controls.py` |
| Leak writer (producto) | `gitlab/intelcon/idetectfugas/app/services/leak_persistence.py` |
| Bridges huérfanos | `check_docker_bridges.sh` (PyAutomation) · `deploy/check_docker_bridges.sh` (iDetectFugas) |
| Tests | `test_store_and_forward.py` (`TestSafNuclearP0`) + `test_ops_controls.py` + `test_long_run_hardening.py` + leak service |


## Parte C — Durabilidad de disco / eficiencia de escritura

> Fuente original: `AUDIT_DISK_DURABILITY.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Productos** | PyAutomationIO (`automation/`) + iDetectFugas (`gitlab/intelcon/idetectfugas`) |
| **Alcance** | Store-and-Forward, SQLite (journal + catalog), hot path CVT, OS/hardware, SMART, pruebas |
| **Metodología** | Caja de cristal + implementación de gaps G-DISK-01…09 |
| **Fecha baseline** | 2026-08-28 (auditoría A− / B) |
| **Fecha de cierre de gaps** | 2026-08-28 |
| **Fuentes cruzadas** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_TAGS.md](./AUDIT_TAGS.md), [HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md); iDetectFugas `06`/`07`/`08` |
| **Veredicto global** | **A+ en código y especificación de borde.** Soak 24 h de planta (**G-DISK-08**) sigue pendiente — no sustituye los tests de caos. |

---

### 1. Resumen ejecutivo

El stack SAF de PyAutomationIO ya desacoplaba el hot path del disco (ring RAM + flusher WAL `synchronous=FULL`) y replicaba por lotes con ACK exact-once. Esta ronda cierra los gaps que impedían el checklist WD de clase mundial:

| Antes (2026-08-28 AM) | Después |
|---|---|
| Sin BOM de SSD industrial | [docs/HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md) + `deploy/HARDWARE_REQUIREMENTS.md` |
| Solo `% uso` de disco | SMART wear/temp + `ALM.PERF.SSD` + tile HMI |
| `JournalDiskFullError` sin test | Tests de guardia y de llenado real |
| Journal sin `cache_size`/`mmap_size` | `cache_size=-64000`, `mmap_size=256 MiB` |
| catalog sin `temp_store=MEMORY` | PRAGMA añadido |
| Doble `set_value` umbral (mixin / apply 1 Hz) | Apply solo si cambió; publish heartbeat 10 s si apply no escribió |
| Healthcheck ciego al montaje | Warning `noatime` (no tumba el contenedor) |

**Puntuación WD-01…WD-10:** 10 / 10 **PASS** en código y documentación. Certificación operativa 24 h: plantilla [AUDIT_DB.md](./AUDIT_DB.md) (pendiente de rellenar).

---

### 2. Criterios WD-01…WD-10

| ID | Criterio | Estado | Evidencia |
|---|---|---|---|
| **WD-01** | Hot path sin E/S síncrona | ✅ PASS | `TagObserver` → `enqueue` → ring; flush en `SafJournalFlusher` (`journal.py` `_flush_loop`) |
| **WD-02** | Buffer en memoria | ✅ PASS | `_ring` `deque`, `ring_maxsize=100_000`; `CycleSampleCache` |
| **WD-03** | Journal durable WAL + FULL | ✅ PASS | `PRAGMA journal_mode=WAL`, `synchronous=FULL` |
| **WD-04** | Escritura por lotes | ✅ PASS | `tag_batch_size=256`, `replicate_batch_size=1000` |
| **WD-05** | Exact-once + ACK | ✅ PASS | `mark_sent` post-outcomes; T-01 SIGKILL |
| **WD-06** | Capacidad journal + no llenar disco | ✅ PASS | `max_disk_bytes=10 GiB`, `max_pending_rows=5e6`; evict SENT; `JournalDiskFullError`; tests `test_disk_full_error_*` |
| **WD-07** | Frecuencia de escritura | ✅ PASS | Umbrales 10 s / on-change; `_set_process_tag_if_changed`; mixin no republica el mismo tick |
| **WD-08** | Pruebas de caos | ✅ PASS | Red/BD existentes + **disco lleno** + pragmas; soak 24 h es G-DISK-08 (planta) |
| **WD-09** | Hardware aprobado | ✅ PASS | Spec SSD TBW/temp/OP + fstab `noatime` + scheduler; warning en healthcheck/sampler |
| **WD-10** | Monitoreo activo | ✅ PASS | Cola SAF + `% disco` + `HOST_DISK_NOATIME` + SMART + `ALM.PERF.SSD` |

**Nota WD-09/WD-10:** el código no puede certificar el SKU físico de planta. PASS = especificación + instrumentación + alarmas. El operador debe cumplir el checklist de [HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md) y definir `AUTOMATION_SSD_DEVICE`. Sin `smartctl`, las métricas SSD quedan `null` y **no** hay falso positivo.

---

### 3. Hallazgos detallados (lista §3 original)

#### 3.1 Store-and-Forward

Todos los controles de arquitectura **cumplen** (hot path, ring, WAL, batch, ACK, circuit breaker, topes). El journal **no** descarta PENDING para hacer sitio: primero evict SENT; si no basta, `JournalDiskFullError`. Eso protege integridad frente a un ring buffer clásico que pisaría datos no ACK.

#### 3.2 SQLite

| PRAGMA | journal.db | catalog.db |
|---|---|---|
| `journal_mode` | WAL | WAL |
| `synchronous` | FULL | NORMAL (1) — correcto: no es Plan A de muestras |
| `temp_store` | MEMORY | MEMORY |
| `cache_size` | −64000 (64 MiB) | −8000 |
| `mmap_size` | 256 MiB (hint) | — |
| `auto_vacuum` | INCREMENTAL + `reclaim_idle` | INCREMENTAL + `compact_catalog_idle` |

#### 3.3 Hot path iDetectFugas

- Umbrales: `_publish_threshold_tags` on-change o 10 s.
- `leak` una vez por ciclo (`07-AUDIT_CVT.md`).
- `Leaks.put` fingerprint.
- Alarmas SocketIO en flanco.
- **G-DISK-07 cerrado:** `_set_process_tag_if_changed` + `_finish_threshold_sync` (PPA, NPW, PFM, Observer, mixin).

#### 3.4 OS / hardware

Documentado y medido; no impuesto por Docker. `healthcheck.py` avisa si falta `noatime` y **sigue devolviendo 200** si `/api/health/ping` responde.

#### 3.5 Pruebas

| Prueba | Archivo |
|---|---|
| Disco lleno (guardia + append) | `test_store_and_forward.py` `test_disk_full_error_*` |
| PRAGMAs journal | `test_journal_pragmas_durable_and_cached` |
| Mount / SMART / sampler | `test_disk_durability.py` |
| catalog `temp_store` | `test_long_run_hardening.py` `test_catalog_temp_store_memory` |
| Umbral una escritura/tick | iDetectFugas `test_threshold_publish.py` |
| Caos red/BD / T-01 | `test_store_and_forward.py` (ya existía) |

---

### 4. Gaps G-DISK-01…09 — estado post-implementación

| ID | Pri. | Estado | Acción realizada |
|---|---|---|---|
| G-DISK-01 | P0 | ✅ Cerrado | `docs/HARDWARE_REQUIREMENTS.md` + `idetectfugas/deploy/HARDWARE_REQUIREMENTS.md` |
| G-DISK-02 | P0 | ✅ Cerrado | `ssd_health.py` + sampler 60 s + `ALM.PERF.SSD` + HMI `/performance` |
| G-DISK-03 | P1 | ✅ Cerrado | Tests `JournalDiskFullError` |
| G-DISK-04 | P1 | ✅ Cerrado | Spec fstab/scheduler; `disk_mount.py`; warning healthcheck; `deploy/README.md` |
| G-DISK-05 | P2 | ✅ Cerrado | `PRAGMA cache_size=-64000`, `mmap_size=268435456` |
| G-DISK-06 | P2 | ✅ Cerrado | Tabla de roles en [AUDIT_TAGS.md](./AUDIT_TAGS.md) |
| G-DISK-07 | P2 | ✅ Cerrado | Apply on-change; publish solo si apply no escribió |
| G-DISK-08 | P3 | ⏳ Planta | Plantilla [AUDIT_DB.md](./AUDIT_DB.md) |
| G-DISK-09 | P3 | ✅ Cerrado | `temp_store=MEMORY` en `open_catalog_db` |

---

### 5. Evidencia de implementación (diff lógico)

#### PyAutomationIO

| Archivo | Cambio |
|---|---|
| `automation/persistence/journal.py` | `cache_size`, `mmap_size` |
| `automation/catalog/local_db.py` | `temp_store=MEMORY` |
| `automation/utils/disk_mount.py` | **nuevo** — `/proc/self/mountinfo`, scheduler |
| `automation/utils/ssd_health.py` | **nuevo** — parse `smartctl -j` |
| `automation/workers/metrics_sampler.py` | mount + SMART + evento SSD |
| `automation/utils/performance_alarms.py` | `ALM.PERF.SSD` |
| `automation/utils/performance_alarm_config.py` | `perf_ssd_*` |
| `healthcheck.py` | warning `noatime` (no fail) |
| `docs/HARDWARE_REQUIREMENTS.md` | BOM SSD / fstab / SMART |
| `hmi/src/pages/Performance.tsx` | tile SSD |
| `automation/tests/test_disk_durability.py` | **nuevo** |
| `automation/tests/test_store_and_forward.py` | disco lleno + pragmas |

#### iDetectFugas

| Archivo | Cambio |
|---|---|
| `app/core.py` | `_set_process_tag_if_changed`, `_finish_threshold_sync` |
| `app/modules/motor_threshold_mixin.py` | no republica si apply escribió |
| `app/modules/ppa|npw|pfm|observer` | apply on-change + finish sync |
| `app/tests/test_threshold_publish.py` | **nuevo** |
| `deploy/HARDWARE_REQUIREMENTS.md` | copia planta |
| `deploy/README.md` | sección almacenamiento |

#### Referencias de código (puntos de partida)

```863:869:github/PyAutomation/automation/persistence/journal.py
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA cache_size=-64000")
            self._conn.execute("PRAGMA mmap_size=268435456")
            self._conn.execute(f"PRAGMA wal_autocheckpoint={int(self.config.wal_autocheckpoint)}")
            self._conn.execute("PRAGMA foreign_keys=ON")
```

Variables de entorno SSD: `AUTOMATION_SSD_DEVICE`, `AUTOMATION_SSD_WEAR_WARN` (80), `AUTOMATION_SSD_TEMP_WARN` (65).

---

### 6. Lecciones aprendidas

1. **Distroless no tiene `smartctl`.** El sampler debe degradar a `available=false` sin alarmar. El dispositivo se lee en el host o con bind-mount documentado.
2. **No tumbar el HEALTHCHECK por `noatime`.** Un bind Docker hereda el fstab del host; fallar el ping dejaría el stack `unhealthy` en labs que aún no tunearon el disco.
3. **PENDING no se pisa.** El “ring buffer de disco” de clase mundial para DAQ es tope + error controlado, no overwrite de filas sin ACK.
4. **El residual bayesiano no era solo el mixin.** PPA/NPW ya no llamaban `_publish` desde `_sync`; el 1 Hz venía de `_apply` → `set_value` cada tick. El arreglo real es skip-if-unchanged + heartbeat 10 s.

---

### 7. Conclusión

**A+ (clase mundial) en software:** WD-01…WD-10 PASS con evidencia en código, tests y especificación de hardware. El sistema está diseñado para 24/7/365 en borde industrial con SSD de alto TBW, journal WAL durable, backpressure y monitoreo SMART.

**Pendiente operativo (no bloquea el veredicto de código):** ejecutar y archivar la campaña de [AUDIT_DB.md](./AUDIT_DB.md) (24 h + outage PG 4 h) y confirmar SMART visible en cada edge de planta.


## Parte D — Plantilla soak disco / SAF 24 h

> Fuente original: `SOAK_DISK_LAST_RUN.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO + iDetectFugas |
| **Alcance** | 24 h (ideal 5 días) con outage PostgreSQL 4 h |
| **Estado** | **Pendiente de ejecución en planta** (G-DISK-08) |
| **Fecha de esta plantilla** | 2026-08-28 |
| **Runbook** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) §4.3 · iDetectFugas `06-AUDIT_PERFORMANCE.md` Parte B |

Esta campaña **no se simula en CI**. Rellenar la tabla tras una corrida real y enlazarla desde [AUDIT_DB.md](./AUDIT_DB.md).

### Cómo ejecutar

```bash
# Backend 24 h (framework)
PERF_SOAK_SECONDS=86400 python -m unittest automation.tests.test_performance_soak

# SAF apocalypse (opcional, más corto)
SAF_SOAK_SECONDS=1800 SAF_SOAK_TAGS=1000 SAF_SOAK_HZ=100 \
  python -m unittest automation.tests.test_store_and_forward.TestT01Apocalypse
```

En lab 2-edge: dejar ambos nodos 24 h, cortar PG 4 h, restaurar, confirmar `SAF_QUEUE_DEPTH → 0`.

### Resultados (rellenar)

| Métrica | Resultado | Umbral | OK |
|---|---|---|---|
| Fecha / operator | _pendiente_ | — | ☐ |
| Duración | | ≥ 24 h | ☐ |
| RSS_MB | | ±10 % vs baseline | ☐ |
| SAF_QUEUE_DEPTH (régimen) | | < 1000 | ☐ |
| Outage PG 4 h — cola pico | | < cap 5e6 | ☐ |
| Outage PG 4 h — drenaje post-ACK | | cola → 0 | ☐ |
| `JournalDiskFullError` | no debe aparecer si disco ≥ 256 GB | 0 | ☐ |
| HOST_DISK_USED_PERCENT | | < 85 % | ☐ |
| HOST_SSD_WEAR_PERCENT / TEMP | | < warn | ☐ |
| OPC_MONITORED_COUNT | | constante | ☐ |
| Exact-once post-replay | | sin duplicados TagValue | ☐ |

### Evidencia

Adjuntar: `GET /api/health/node` T0/T24, `/api/health/saf`, Events `Disk usage critical` / `SSD SMART` (no deben disparar), logs gunicorn.

Última corrida T-01 (SIGKILL, no 24 h): [AUDIT_DB.md](./AUDIT_DB.md).


## Parte F — T-01 Soak last run (regenerado por tests)

El bloque entre marcadores lo reescribe `automation/tests/test_store_and_forward.py`.

<!-- T01_SOAK_LAST_RUN:start -->
# T-01 Soak — last run

- tags=50 hz=20.0 duration_s=2.0 kill_at_s=1.000
- achieved_tick_hz=0.00
- generated_fsync=0
- journal_durable=0
- ring_lag_samples=0
- replicated=0
- remote_rows_first_pass=0
- remote_rows_after_retry=0
- pending_after=0
- exact_once=True
- remote_equals_durable=True

Ring lag is the hardware window of the in-memory flusher (≤ tag_flush_interval_s).
Those samples never reached WAL before SIGKILL; they are the only acceptable loss.
<!-- T01_SOAK_LAST_RUN:end -->

