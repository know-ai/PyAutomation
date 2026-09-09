# Auditoría compacta: base de datos, conexiones, reconexión y timeout de red

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Ciclo de vida Peewee/libpq bajo Gunicorn + gevent; reconexión; freeze del hub; censo idle; RAM atribuible a sockets |
| **Fecha original** | 2026-08-14 … 2026-08-17 (seis auditorías) |
| **Compactación** | 2026-08-18 — evidencia de código actualizada |
| **Reapertura** | 2026-09-09 — incidente `too many clients already` en laboratorio (§1.5). El censo era **dueño** del socket |
| **Segunda reapertura** | 2026-09-09 (post-arreglo) — `sockets above alert threshold` crónico (§1.6). No había fuga: el presupuesto medía la concurrencia web y los workers de ciclo lento retenían el socket |
| **Fuentes absorbidas** | `AUDIT_DB_CONNECTIONS`, `AUDIT_DB_CONNECTIONS_ETERNAL`, `AUDIT_OPTIMAL_CONNECTIONS`, `AUDIT_DB_RECONNECT`, `AUDIT_NETWORK_TIMEOUT`, `AUDIT_DB_CONNECTION_MEMORY` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) (BE-H4, RSS), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) (PENDING no se toca), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (`application_name` con `node_id`) |
| **Veredicto vigente** | Un objeto `Database`. Población idle = **roster residente declarado** (3 por defecto), más ráfagas transitorias; techo duro **12** por proceso. Probes throwaway. Teardown HTTP. Reconnect owner-scoped + `SELECT 1` ligado. Pool Peewee **prohibido**. Historiador inalcanzable **no** puede congelar el hub ni `on.tag`. Ningún socket inactivo sobrevive al presupuesto del cliente, que va por delante del `idle_session_timeout` del servidor |
| **Clasificación** | Auditoría de arquitectura · conexiones · Confidencialidad interna |

---

## 0. Respuesta directa

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

## 1. Diagnóstico fusionado (evidencia de planta)

### 1.1 18 backends — Directiva de Conexiones Eternas (2026-08-17)

Un objeto `PostgresqlDatabase` **sí** era singleton. Las 18 conexiones eran **sockets por greenlet/hilo** sin `close()`, agravadas por probes Peewee en el threadpool del hub (`run_uncooperative_db_call(lambda: db.execute_sql("SELECT 1"))` asociaba el TCP al **hilo OS** del pool).

| Actor | ¿Socket persistente? |
|---|---|
| LoggerWorker | **Sí, 1** |
| Request Flask / REST | No: abrir al primer SQL, cerrar en teardown |
| Socket.IO `on.tag` | No toca PG (CVT + journal local) |
| Hub threadpool (probes) | **Nunca** Peewee; solo `ping_throwaway` |
| Health `/api/health/db` | Throwaway |

### 1.2 8 idle estables — Conexiones Estables (planta 2026-08-17 18:28, `idetect_db`)

Captura `pg_stat_activity` (host app `192.168.1.106`):

| pid | Última query (resumen) | Atribución |
|---|---|---|
| 50966 | `SELECT … FROM "opcua"` | Hidratación OPC UA; greenlet que no cerró |
| 51050–51060 | `Alarms` `name = 'alarm.{LDS,PPA,NPW,PFM}.leak'` | Hilos async **LDS / PPA / NPW / PFM** |
| 52115 | `SELECT 1` | Probe residual |
| 52659 | `SELECT 1` | **LoggerWorker** |

Ninguna fila en `idle in transaction`. El conteo **no crecía** (conjunto fijo que reabre). Objetivo idle: **1** (`:LoggerWorker`). Techo **CA-OPT-1: ≤ 4**.

`append_machine(..., mode='async')` es el default. Cada `SchedThread` que hace Peewee = 1 backend idle eterno hasta `ephemeral_historian`.

### 1.5 `too many clients already` — el censo era dueño del socket (planta 2026-09-09)

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

### 1.6 `sockets above alert threshold` — la alarma medía la plantilla, no la carga (planta 2026-09-09, post-§1.5)

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

### 1.3 `connection already closed` tras «Reconnection successfully» (17:47)

```
CRITICAL: Reconnection successfully
psycopg2.InterfaceError: connection already closed
SAF replication failed for domain tag | event | alarm_summary_update
```

Causa raíz: `previous.close_all()` llamaba `REGISTRY.close_tracked()` **sin owner** y mataba el socket del **candidato** recién abierto. El ping throwaway veía el host up → CRITICAL. Los modelos usaban un handle Peewee con TCP ya cerrado. El SAF **hizo lo correcto**: no ACK, filas PENDING.

Hipótesis «el proxy no se actualiza»: **falsa en el mecanismo**. Hay un solo `Proxy` (`automation/dbmodels/core.py`). `set_db` ya hacía `proxy.initialize(candidate)` antes de `connect()`.

### 1.4 HMI congelada solo con BD remota (timeout de red)

| Escenario | `connect()` / `SELECT 1` | Hub gevent | HMI | Journal |
|---|---|---|---|---|
| Postgres Docker `docker stop` | `Connection refused` inmediato | Casi no se bloquea | Tendencias vivas | PENDING → replica |
| Cable / `No route to host` | Timeout del **SO** (30–180 s) | Hub congelado en libpq | `on.tag` no se drena | PENDING sí se acumula |

`on.tag` **no** consulta PG (`CVTEngine.set_value` → `sio.emit`). El freeze es de **planificación del event loop**: `gevent.monkey.patch_all()` convierte `LoggerWorker` en greenlet; libpq no cede.

`@logging_error_handler` en `set_db` **no re-lanza**: `connect()` largo + `_historian_is_live()` contra el socket zombi = dos bloqueos encadenados.

---

## 2. Política vigente (quién abre, quién cierra)

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

## 3. Timeout de red vs hub (contrato extra al SAF)

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

## 4. Reconexión efectiva

### 4.1 Censo por owner

`ConnectionRegistry` (`automation/utils/db_connections.py`): `_by_owner: dict[owner_id, {conn_id: conn}]`. `close_all()` cierra el socket de **este** greenlet y luego `REGISTRY.close_tracked(owner=self)`. `close_tracked()` sin owner queda para tests / shutdown global.

Así `previous.close_all()` no mata el TCP del candidato.

### 4.2 `_historian_is_live`

Deja de fiarse solo del ping throwaway. Llama `ensure_bound_connection` sobre `db_manager.get_db()` / `self._db`. El throwaway queda para «¿el host responde?» sin tocar un socket medio-abierto.

### 4.3 Health post-reconnect

| Endpoint | Qué mide |
|---|---|
| `GET /api/health/system` → `is_db_connected` | Flag de proceso (`_db_live` + handle) **tras** `SELECT 1` ligado |
| `DB_ACTIVE_CONNECTIONS` | `pg_stat_activity` (verdad del servidor) |
| `GET /api/health/db` | Probe throwaway (¿el host responde?) |
| `GET /api/health/saf` | `PENDING_ROWS` debe **bajar** |

Un solo `Proxy`. Modelos que heredan `BaseModel` (Tags, TagValue, Alarms, AlarmSummary, Events, Logs, Users, Roles, Machines, OPCUA, Nodes, geo, …) usan el mismo placeholder. `logger/core.py` y `managers/db.py` **no** declaran otro `Proxy`.

---

## 5. Métricas (`GET /api/health/system`)

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

## 6. Memoria RAM ↔ conexiones (actualizado)

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

## 7. Criterios de aceptación (IDs conservados)

### Conexiones eternas / censo

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

### Fuga permanente (§1.5)

| ID | Criterio | Estado |
|---|---|---|
| **CA-DB-LEAK-1** | Un greenlet que muere sin `close()` no deja backend | `test_dead_greenlets_do_not_leave_idle_backends` (PG real) |
| **CA-DB-LEAK-2** | `reap_abandoned()` cierra el socket de un greenlet muerto y respeta el de uno vivo | `test_reap_abandoned_*` / `test_reap_keeps_socket_of_a_living_worker` |
| **CA-DB-LEAK-3** | El proceso nunca supera `DB_CONNECTIONS_MAX`; `connect()` falla rápido | `test_connect_refused_above_hard_ceiling` |
| **CA-DB-LEAK-4** | Cerrar con transacción abierta hace `rollback` primero | `test_close_rolls_back_open_transaction_first` |
| **CA-DB-LEAK-5** | PostgreSQL aplica `idle_session_timeout` / `idle_in_transaction_session_timeout` | `test_server_applies_idle_session_guards` |
| **CA-DB-LEAK-6** | Toda conexión (incluido LISTEN) lleva `application_name` | Revisión de código + SQL §5 |
| **CA-DB-LEAK-7** | Soak 7 días en planta: `DB_CONNECTIONS_REAPED = 0` y activas planas | **Pendiente planta** |

### Socket 24/7 (§1.6)

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

### Conteo óptimo

| ID | Criterio | Estado |
|---|---|---|
| **CA-OPT-1** | Idle ≤ 4 tras arranque | Código: `ephemeral_historian`. Planta: repetir SQL |
| **CA-OPT-2** | `application_name` descriptivo | Implementado |
| **CA-OPT-3** | Cero `idle in transaction` | Confirmado en captura 2026-08-17 |
| **CA-OPT-4** | Estable 24 h | Pendiente soak |
| **CA-OPT-5** | Reconnect no aumenta el conteo | Owner-scoped + cierre efímero; validar en planta |

### Reconexión

| ID | Criterio | Estado |
|---|---|---|
| **CA-REC-1** | Proxy + `SELECT 1` ligado post-reconnect | Código + tests. Planta: 10 min sin `already closed` |
| **CA-REC-2** | SAF (`tag`/`event`/`alarm_summary`) reanuda sin reiniciar proceso | Código. Planta: `PENDING_ROWS` baja |
| **CA-REC-3** | Cero `connection already closed` tras CRITICAL | Causa raíz eliminada |
| **CA-REC-4** | Health refleja `is_db_connected` y activas | Implementado |
| **CA-REC-5** | 10 ciclos outage/restore sin fuga | Pendiente soak planta |

### Memoria ↔ BD

| ID | Criterio |
|---|---|
| **CA-DBMEM-1** | Backends de la app se estabilizan tras warm-up |
| **CA-DBMEM-2** | `POOL_CONNECTIONS_USED` N/A/0 mientras no hay pool |
| **CA-DBMEM-3** | Δ RSS cientos de MB con PG plano **no** se atribuye a conexiones |
| **CA-DBMEM-4** | Reconnect fallido no deja el proceso sin handle previo |
| **CA-DBMEM-5** | No reintroducir pool sin teardown + soak gevent |

---

## 8. Pruebas y staging

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

## 9. Runbook (operación)

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

## 10. Residual

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

## 11. Archivos clave

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
