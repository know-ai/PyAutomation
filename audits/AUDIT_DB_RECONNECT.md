# Auditoría: Operación «Reconexión Efectiva»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Ciclo de vida del handle Peewee tras outage de red: `set_db`, `database_proxy`, `close_all`, `_historian_is_live`, LoggerWorker, SAF |
| **Evidencia de planta** | `2026-08-17 17:47:28,836 CRITICAL: Reconnection successfully` seguido de `psycopg2.InterfaceError: connection already closed` y `SAF replication failed` (`tag`, `event`, `alarm_summary_update`) |
| **Fecha** | 2026-08-17 |
| **Complementa** | `AUDIT_NETWORK_TIMEOUT.md`, `AUDIT_DB_CONNECTIONS.md`, `AUDIT_DB_CONNECTIONS_ETERNAL.md`, `STORE_AND_FORWARD.md` |
| **Veredicto** | El SAF **acumuló PENDING correctamente**. El fallo no era «falta de reconexión» ni un proxy sin `initialize`. `set_db` sí apuntaba el `Proxy` al candidato; `previous.close_all()` cerraba **todos** los sockets del censo, incluido el del candidato recién abierto. El ping throwaway veía el host up y se marcaba éxito. Los modelos usaban un handle Peewee con TCP ya cerrado |
| **Clasificación** | Auditoría de arquitectura · ciclo de vida de conexiones · Confidencialidad interna |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Falló el Store-and-Forward? | **No.** El journal local conserva PENDING. La replicación falla porque la **escritura remota** usa un socket muerto |
| ¿El `database_proxy` se actualizaba? | **Sí.** Un solo `Proxy` (`automation/dbmodels/core.py`). `set_db` ya hacía `proxy.initialize(candidate)` **antes** de `connect()` |
| ¿Por qué entonces `connection already closed`? | `Tracked*.close_all()` llamaba `REGISTRY.close_tracked()` **sin owner** y mataba el socket del candidato. Peewee cree que el objeto está abierto; libpq ya está `closed` |
| ¿Por qué el log decía «Reconnection successfully»? | `_historian_is_live` / `check_connectivity` usaban un ping **throwaway**. El host responde → éxito. El handle ligado a los modelos no se validaba |
| ¿Hay varios proxies? | **No.** `Events`, `Alarms`, `Tags`, `Logs`, `AlarmSummary` y el resto heredan `BaseModel.Meta.database = proxy` |
| ¿Hace falta reiniciar el proceso? | Con este fix, **no**. Tras restaurar la red, el watchdog reconecta, prueba `SELECT 1` en el handle ligado y reanuda SAF |

---

## 1. Diagnóstico y evidencia

### 1.1 Log de planta (2026-08-17 17:47)

```
2026-08-17 17:47:28,836 CRITICAL: Reconnection successfully
psycopg2.InterfaceError: connection already closed
SAF replication failed for domain tag; those rows kept PENDING
SAF replication failed for domain event
SAF replication failed for domain alarm_summary_update
```

Interpretación:

1. `LoggerWorker.reconnect_to_db()` → `PyAutomation.reconnect_to_db()` → `set_db()` completó y el watchdog escribió el CRITICAL.
2. El ciclo siguiente (`replicate_once`) usa `Events.create`, `Tags.read_by_name`, `Alarms.read_by_name` sobre el **mismo** objeto `Database` que `set_db` acaba de instalar.
3. Ese objeto tiene el socket TCP cerrado → `InterfaceError`.
4. SAF hace lo correcto: no ACK, filas siguen PENDING.

### 1.2 Hipótesis original vs causa raíz

La hipótesis de trabajo («el proxy no se actualiza») es **parcialmente cierta en el síntoma** (los modelos ven una conexión inválida) y **incorrecta en el mecanismo**.

| Hipótesis | Hallazgo |
|---|---|
| `set_db` no llama `database_proxy.initialize(new_db)` | Falso. Ya lo hacía (línea previa a `connect`) |
| Los modelos guardan una referencia al objeto antiguo | Falso. `BaseModel.Meta.database` es el `Proxy`; `proxy.obj` pasa a ser el candidato |
| El candidato se conecta y luego alguien cierra **su** socket | **Cierto.** `previous.close_all()` → `REGISTRY.close_tracked()` global |
| El probe de salud mide el handle de los modelos | Falso. Medía un cliente `psycopg2` desechable |

### 1.3 Secuencia que mataba el handle nuevo

`automation/core.py` `set_db` (antes de esta operación):

1. `candidate = TrackedPostgresqlDatabase(...)`
2. `proxy.initialize(candidate)`
3. `candidate.connect()` → `_connect` registra el socket nuevo en `REGISTRY` (sin owner)
4. `previous.close_all()` → `REGISTRY.close_tracked()` **cierra todos los sockets del proceso**, incluido el del candidato
5. `self._db = candidate` (Peewee: abierto; libpq: closed)
6. `_historian_is_live()` abre un ping throwaway, el host responde, `_db_live = True`
7. LoggerWorker: `Reconnection successfully`

A partir de ahí, cualquier `Model.create` / `read_by_name` explota con `connection already closed` hasta reiniciar el proceso.

---

## 2. Mapa de dependencias del proxy

Un solo placeholder:

```
automation/dbmodels/core.py
    proxy = Proxy()
    BaseModel.Meta.database = proxy
```

Modelos que heredan `BaseModel` (todos usan el mismo proxy):

| Dominio | Modelos |
|---|---|
| Tags / CVT | `Manufacturer`, `Segment`, `Variables`, `Units`, `DataTypes`, `Tags`, `TagValue` |
| Alarmas | `AlarmTypes`, `AlarmStates`, `Alarms`, `AlarmSummary` |
| Eventos / logs | `Events`, `Logs` |
| Usuarios | `Users`, `Roles` |
| Máquinas / OPC | `Machines`, `TagsMachines`, `OPCUA`, `OPCUAServer`, `AccessType` |
| Geo | `LinearReferencingGeospatial` |

Propagación del handle (no hay segundo proxy):

| Componente | Cómo recibe la BD |
|---|---|
| Modelos Peewee | `bind_historian_proxy(candidate)` → `proxy.initialize` |
| `DBManager.set_db` | Asigna el **mismo** objeto a cada logger engine |
| `BaseLogger._db` | Referencia al handle; `check_connectivity` es ping throwaway (host up/down) |
| LoggerWorker | `app.reconnect_to_db()`; no tiene proxy propio |
| Flask / REST | Teardown cierra el socket **de ese** greenlet sobre `app._db` |

`automation/logger/core.py` y `automation/managers/db.py` **no** declaran otro `Proxy`. Actualizar el proxy único + `db_manager.set_db(candidate)` es suficiente.

---

## 3. Implementación

### 3.1 Censo por owner (`ConnectionRegistry`)

`automation/utils/db_connections.py`:

- `_by_owner: dict[owner_id, {conn_id: conn}]`
- `register(conn, owner=self)` / `unregister(conn, owner=self)` en `TrackedPostgresqlDatabase` y `TrackedMySQLDatabase`
- `close_all()` cierra el socket de **este** greenlet y luego `REGISTRY.close_tracked(owner=self)`
- `close_tracked()` sin owner sigue existiendo para tests / shutdown global

Así, `previous.close_all()` no puede matar el TCP del candidato.

### 3.2 `set_db` — reconexión efectiva

Orden nuevo:

1. Construir `candidate` y `REGISTRY.bind_instance(candidate)`
2. `bind_historian_proxy(candidate)`
3. `connect()` + `ensure_bound_connection(candidate)` (`SELECT 1` en el socket Peewee de este greenlet; si `InterfaceError`, `close` + `connect` + `SELECT 1`)
4. Si (3) falla: cerrar candidato, restaurar `previous` en el proxy, **no** marcar `_db_live`, relanzar. El watchdog **no** escribe «Reconnection successfully»
5. Solo entonces `previous.close_all()` (owner-scoped)
6. `self._db = candidate`, `db_manager.set_db(...)`, `_db_live = True`, `mark_remote_db_live()`

### 3.3 `_historian_is_live`

Deja de fiarse del ping throwaway. Llama `ensure_bound_connection` sobre `db_manager.get_db()` / `self._db`. El throwaway (`check_connectivity`) se reserva para «¿el host responde?» sin tocar un socket medio-abierto (eso sí puede colgar el hub; ver `AUDIT_NETWORK_TIMEOUT.md`).

### 3.4 LoggerWorker

Cuando el host es reachable:

```
bound_ok = app.is_db_connected() and app._historian_is_live()
if not bound_ok:
    reconnect_to_db()
```

Cubre el caso «host up + handle muerto» que antes se daba por bueno y nunca volvía a llamar `set_db`.

### 3.5 Health (`CA-REC-4`)

`GET /api/health/system` expone:

- `is_db_connected` — flag de proceso (`_db_live` + handle en el manager)
- `DB_ACTIVE_CONNECTIONS` — `pg_stat_activity` (verdad del servidor)
- `GET /api/health/db` — `connected` vía probe throwaway (¿el host responde?)

Tras una reconexión **efectiva**: `is_db_connected=true` y `DB_ACTIVE_CONNECTIONS` ≥ 1. Si el CRITICAL mintió (host up, handle muerto), `is_db_connected` puede ser true y aun así fallarían los modelos: ese es el bug que esta operación cierra. Tras el fix, `_db_live` solo se pone tras `SELECT 1` ligado.

---

## 4. Pruebas

### 4.1 Unitarias (esta sesión)

```bash
cd github/PyAutomation
/home/crivero/repo/gitlab/intelcon/idetectfugas/venv/bin/python3 -m unittest \
  automation.tests.test_db_io \
  automation.tests.test_database_health \
  automation.tests.test_connection_alarms -v
```

Cobertura nueva en `test_db_io.py`:

| Test | Criterio |
|---|---|
| `test_close_tracked_does_not_kill_other_owner` | Cerrar owner A no cierra sockets de B |
| `test_tracked_close_all_is_owner_scoped` | `TrackedPostgresqlDatabase.close_all` no mata al candidato |
| `test_ensure_bound_connection_reopens_closed_handle` | `is_closed` → `connect` + `SELECT 1` |
| `test_ensure_bound_connection_heals_already_closed` | `InterfaceError` → reopen + segundo `SELECT 1` |
| `test_bind_historian_proxy_points_models_at_new_handle` | `proxy.obj` pasa al candidato |

### 4.2 Validación de planta (pendiente de ejecución en sitio)

No se puede simular aquí un corte de cable hacia `192.168.1.95`. Procedimiento:

1. Baseline: `GET /api/health/system` y `GET /api/health/saf`. Anotar `is_db_connected`, `DB_ACTIVE_CONNECTIONS`, `PENDING_ROWS`.
2. Desconectar la red hacia PostgreSQL ≥ 5 min. Confirmar `PENDING_ROWS` crece y HMI viva (`on.tag`).
3. Restaurar la red. Esperar el CRITICAL `Reconnection successfully`.
4. Durante **10 min**: cero `connection already closed` en `logs/app.log`.
5. `PENDING_ROWS` baja a 0 (o a la cola residual de ruido). Dominios `tag`, `event`, `alarm_summary_update` replican.
6. `GET /api/health/system`: `is_db_connected=true`; `DB_ACTIVE_CONNECTIONS` estable (1–3 idle, 1 worker).
7. Soak `CA-REC-5`: 10 ciclos desconexión/reconexión. `DB_ACTIVE_CONNECTIONS` no crece monotónicamente; RSS estable.

---

## 5. Criterios de aceptación

| ID | Criterio | Estado |
|---|---|---|
| **CA-REC-1** | Tras reconexión, el proxy apunta al candidato y `SELECT 1` ligado funciona | Cubierto en código + tests de proxy / `ensure_bound_connection`. Planta: §4.2 paso 4 |
| **CA-REC-2** | SAF (`tag`, `event`, `alarm_summary`) reanuda sin reiniciar el proceso | Código: handle vivo + journal PENDING intacto. Planta: §4.2 paso 5 |
| **CA-REC-3** | Cero `connection already closed` tras «Reconnection successfully» | Causa raíz eliminada (`close_all` owner-scoped + probe ligado). Planta: §4.2 paso 4 |
| **CA-REC-4** | `/api/health/system` refleja `DB_ACTIVE_CONNECTIONS` e `is_db_connected` | Implementado |
| **CA-REC-5** | 10 ciclos outage/restore sin fugas de conexiones | Pendiente soak de planta. Censo por owner evita matar/reabrir mal; teardown HTTP y `release_ephemeral_historian` siguen vigentes |

---

## 6. Runbook post-reconexión

Ver `PERFORMANCE_RUNBOOK.md` §10. Resumen:

1. Buscar el CRITICAL `Reconnection successfully`.
2. Confirmar que **no** le siguen `connection already closed` ni `SAF replication failed`.
3. `GET /api/health/system` → `is_db_connected`, `DB_ACTIVE_CONNECTIONS`.
4. `GET /api/health/saf` → `PENDING_ROWS` descendente.
5. Si el CRITICAL aparece y los modelos siguen fallando: **no** es SAF. Es handle muerto (versión anterior a este patch) → reiniciar worker **una vez** y desplegar esta corrección.

---

## 7. Lo que no se tocó (a propósito)

| Tema | Motivo |
|---|---|
| `gevent.Timeout` alrededor de `psycopg2.connect` | No corta libpq (`AUDIT_NETWORK_TIMEOUT.md`) |
| Pool Peewee | BE-H4: no reintroducir |
| Borrar PENDING del journal | El SAF hizo su trabajo; el bug era la escritura remota |
| Segundo `Proxy` por logger | Innecesario; un proxy + `db_manager.set_db` |

---

## 8. Conclusión

El Store-and-Forward sobrevivió al outage. La vuelta a la normalidad fallaba porque «reconexión» era un mensaje de log, no un cambio de estado que los modelos pudieran usar.

Con el censo por owner, `initialize` + `SELECT 1` ligado **antes** de cerrar el handle anterior, y un watchdog que no se fía solo del ping throwaway, PyAutomation recupera la escritura remota sin reiniciar el proceso. Eso es grado nuclear.
