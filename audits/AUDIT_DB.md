# Auditoría compacta: base de datos, conexiones, reconexión y timeout de red

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Ciclo de vida Peewee/libpq bajo Gunicorn + gevent; reconexión; freeze del hub; censo idle; RAM atribuible a sockets |
| **Fecha original** | 2026-08-14 … 2026-08-17 (seis auditorías) |
| **Compactación** | 2026-08-18 — evidencia de código actualizada |
| **Fuentes absorbidas** | `AUDIT_DB_CONNECTIONS`, `AUDIT_DB_CONNECTIONS_ETERNAL`, `AUDIT_OPTIMAL_CONNECTIONS`, `AUDIT_DB_RECONNECT`, `AUDIT_NETWORK_TIMEOUT`, `AUDIT_DB_CONNECTION_MEMORY` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) (BE-H4, RSS), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) (PENDING no se toca), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (`application_name` con `node_id`) |
| **Veredicto vigente** | Un objeto `Database`. Idle 1 worker: **1–3** sockets (techo **≤ 4**). Probes throwaway. Teardown HTTP. Reconnect owner-scoped + `SELECT 1` ligado. Pool Peewee **prohibido**. Historiador inalcanzable **no** puede congelar el hub ni `on.tag` |
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
  ×  1 socket persistente (LoggerWorker / SafJournalFlusher)
  +  0 sockets HTTP al terminar el request
  +  0 sockets en hilos SM al salir de loop()
  +  0 sockets Peewee en el threadpool del hub
```

`application_name` (máx. 63):

- Multi-edge on: `PyAutomationIO:<node_id>:<rol>`
- Multi-edge off: `PyAutomationIO:<rol>` o `PyAutomationIO`
- Probes: `…:probe` (no entran en `DB_CONNECTIONS_COUNT`)

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

Regla: **quien abre, cierra**, salvo LoggerWorker / SafJournalFlusher.

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

# LoggerWorker.run, al stop
close_current_greenlet_connection(...)
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
| `DB_CONNECTIONS_EXPECTED_MAX` | `(workers × 2) + 2` → **4** con 1 worker |
| `DB_CONNECTIONS_ALERT_THRESHOLD` | default **6** (`AUTOMATION_DB_CONNECTIONS_ALERT`) |
| `DB_CONNECTIONS_ALERT` | activas > umbral |
| `DB_APPLICATION_NAME` | nombre de este greenlet |
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

Esperado: 1 idle `PyAutomationIO:<node>:LoggerWorker`. Cero `SM-*` idle más de un periodo de máquina. Cero `idle in transaction`.

Si tras deploy siguen `PyAutomationIO:SM-*` idle: ese módulo consulta Peewee **fuera** de `loop()`. Cazar por `application_name` + `query`. No matar backends a mano.

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

1. `GET /api/health/system` → `DB_CONNECTIONS_COUNT`, `DB_ACTIVE_CONNECTIONS`, `DB_NAMED_CONNECTIONS`, `DB_CONNECTIONS_ALERT`, `is_db_connected`.
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

**Cierre:** el circulatorio de PyAutomation es **un handle, sockets con dueño, probes desechables, reconexión que los modelos pueden usar, hub que no espera a libpq**. El día 1 y el día 1000 deben mostrar el mismo número de backends `PyAutomationIO` en idle.

---

## 11. Archivos clave

| Pieza | Ruta |
|---|---|
| Censo, Tracked*, teardown, throwaway, `application_name`, `ephemeral_historian` | `automation/utils/db_connections.py` |
| Timeouts libpq / threadpool de probes | `automation/utils/db_io.py` |
| Fábrica `set_db` / `_historian_is_live` / `release_ephemeral_historian` | `automation/core.py` |
| Watchdog | `automation/workers/logger.py` |
| Probe logger | `automation/logger/core.py` |
| `journal_then_remote` cierre efímero | `automation/persistence/outbox.py` |
| SM wrap | `automation/workers/state_machine.py`, `automation/state_machine.py` |
| Proxy único | `automation/dbmodels/core.py` |
| Health | `automation/health/service.py`, `automation/modules/health/resources/health.py` |
| `on.tag` (sin BD) | `automation/tags/cvt.py` |
| Tests | `automation/tests/test_db_io.py` |
