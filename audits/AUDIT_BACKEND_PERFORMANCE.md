# Auditoría de Performance Backend (Python) — Operación «Rendimiento Eterno»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Núcleo 24/7: CPU/RAM estables, colas acotadas, complejidad O(1)/O(log n) en hot paths |
| **Clasificación** | Auditoría de rendimiento backend · Confidencialidad interna |
| **Fecha** | 2026-08-13 (actualizado tras Engranaje Perfecto + **reversión BE-H4**) |
| **Metodología** | Revisión estática CVT, SAF, Buffer, OPC UA, workers, índices DB, health |
| **Principios guía** | SOLID + complejidad algorítmica garantizada en path caliente |
| **Veredicto** | **A−** — P0/P1/P2 cerrados salvo **BE-H4** (pool PG revertido tras incidente signup/login). P3 (soak 24h/7d en planta) pendiente. Ver §3.2 BE-H4 y `PERFORMANCE_RUNBOOK.md` §5.1. |
| **Dependencias** | `audits/STORE_AND_FORWARD.md`, `audits/PERSISTENCE_FLOW.md` |

---

## 1. Resumen ejecutivo

El backend ya tiene una capa SAF madura: ring RAM acotado (`ring_maxsize=50_000`), journal SQLite con GC de SENT, circuit breaker, métricas `/api/health/saf`, índice único `TagValue(tag_id, timestamp)`, rotación de logs. Eso protege la **durabilidad**. Esta auditoría mira la **eficiencia eterna** del camino caliente:

```
OPC UA datachange → DAS → CVTEngine.set_value [LOCK GLOBAL]
  → Tag.set_value → Buffer.insert(0) O(n)
  → TagObserver → CycleSampleCache → JournalWriter
  → Alarm MachineObserver → SocketIO serialize/emit
```

**Hallazgos dominantes:**

1. **CVTEngine serializa todas las lecturas/escrituras** con un par request/response locks → contención O(Q) bajo carga de tags.
2. **Lookups de tag por nombre/namespace son O(n)** bajo ese lock.
3. **Bug de dedupe en `DAS.subscribe`**: compara `Node` vs claves `str` → re-subscribe sin unsubscribe en reconnect 24/7.
4. **`Buffer` usa `list.insert(0)`** → O(n) por muestra (n hasta ~600 en DAS).
5. **Alarmas: scan O(n_alarms)** y comparación tag str vs objeto; observers no se detach al borrar.

**Objetivo de aceptación:** tras 30 días de planta, RSS del worker gunicorn ±15 % vs baseline; p99 de `set_value` estable; `SAF_QUEUE_DEPTH` y `DAS.monitored_items` sin crecimiento monotónico.

---

## 1.1 Estado de implementación (2026-08-13)

Cirugía P0/P1/P2 aplicada en `automation/`. BE-C1, BE-C2, BE-H1–H3, BE-H5 y BE-M1–M7 **cerrados**. **BE-H4 revertido** (incidente de pool; ver detalle abajo).

| ID | Estado | Qué se hizo |
|---|---|---|
| **BE-C1** | Hecho | `CVTEngine.set_value` / `set_value_fast` escriben en `self._cvt` con lock **por tag** (`Tag._lock`). CRUD (set/update/delete tag) sigue en request/response. |
| **BE-C2** | Hecho | Clave `nodeid.to_string()`; unsubscribe del handle previo; **una** `create_subscription` por `client_name` (`DAS.get_or_create_subscription`); `reset_client` en reconnect. |
| **BE-H1** | Hecho | `_name_index` / `_namespace_index`; `get_tag` / `get_tag_by_name` / `get_tag_by_node_namespace` / `is_tag_defined` en O(1) sin cola global. |
| **BE-H2** | Hecho | `Buffer` con `collections.deque(maxlen)` + `appendleft` + lock local. |
| **BE-H3** | Hecho | `_by_name` / `_by_tag_name`; `get_alarm_by_tag` compara `alarm.tag.name`; `delete_alarm` hace `detach_from_tag` + detach del observer de cola. |
| **BE-H4** | **Revertido** 2026-08-13 | Intento `PooledPostgresqlDatabase(max_connections=8, timeout=30)` → incidente signup/login. Código actual: `PostgresqlDatabase` (sin pool). Reintento solo con connect/close por request. |
| **BE-H5** | Hecho | Reconnect itera `iter_tags_for_opcua_client` (sin `get_tags()` serialize). |
| **BE-M1** | Hecho | `max_pending_rows=5_000_000`; alerta + `JournalBackpressureError` (no borra PENDING). |
| **BE-M2** | Hecho | Cache name→tag / unit por batch en `TagValuePayloadMapper.to_rows`. |
| **BE-M3** | Hecho | Prune de `CycleSampleCache` cada 0.5 s, no en cada `should_drop`. |
| **BE-M4** | Hecho | `_tag_queue = Queue(maxsize=1)` en DBManager y AlarmManager (código residual acotado). |
| **BE-M5** | Hecho | `DBManager.attach` idempotente (no duplica `TagObserver`). |
| **BE-M6** | Hecho | `require_producer_timestamp` en `ProcessType.set_value`; `set_value_fast` no usa `datetime.now()`. |
| **BE-M7** | Hecho | `Tag.serialize_socket()` → `{name,value,timestamp,unit}`. |
| **Health** | Hecho | `GET /api/health/system` → RSS, threads, OPC, CVT, `PENDING_ROWS`, `ALARM_COUNT`, `POOL_CONNECTIONS_USED` (N/A sin pool), `SAF_PENDING_CAP_HITS`, `CVT_LOCK_CONTENTION`. |
| Tests | Hecho | `test_performance_hotpath.py`, `test_performance_soak.py` (`PERF_SOAK_SECONDS`) |
| Runbook | Hecho | `audits/PERFORMANCE_RUNBOOK.md` |

**Soak operativo (aún a ejecutar en planta, no en CI):** 24 h / 7 d × 100 tags @ 10 Hz; reconnect OPC cada 5 min; RSS y `OPC_MONITORED_COUNT` planos.

---

## 2. Principios SOLID aplicados al backend

| Letra | Aplicación | Violación detectada |
|---|---|---|
| **S** | CVT = valores actuales; SAF = durabilidad; DAS = adquisición | Reconnect OPC mezcla connect + serialize-all-tags + resubscribe |
| **O** | Estructuras con política de tamaño/TTL | PENDING SAF en disco puede crecer hasta `max_disk_bytes` (10 GB) sin cap de filas |
| **L** | Colas/cachés deben comportarse igual a cualquier tamaño | `queue.Queue` residual sin `maxsize` (hoy muerto, peligro al reactivar) |
| **I** | No cargar estructuras completas para un campo | `get_tags()` en reconnect serializa buffers enteros |
| **D** | Abstracciones (`IPersistenceGateway`) | Hot path aún acoplado a locks globales del Singleton CVT |

---

## 3. Hallazgos (por módulo)

### 3.1 Crítico

#### BE-C1 — Contención global en `CVTEngine`

| | |
|---|---|
| **Severidad** | Crítico — **remediado 2026-08-13** |
| **Módulo** | `tags/cvt.py` |
| **Evidencia** | `_request_lock` + `_response_lock`: cada `set_value` / `get_*` pasa por cola request/response. Hot path DAS y alarmas compiten. |
| **Complejidad** | Amortizada O(1) por op, pero **serialización total** → throughput ~1/latency_lock bajo N productores. |
| **Impacto 24/7** | Latencia de adquisición crece con #tags y #observers; jitter industrial. |

```791:792:automation/tags/cvt.py
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()
```

**Recomendación quirúrgica:**

```python
# Fast-path sin request/response para hot path:
def set_value_fast(self, id: str, value, timestamp):
    tag = self._tags.get(id)  # dict O(1)
    if tag is None:
        return
    with tag._lock:  # lock por tag
        return tag.set_value(value=value, timestamp=timestamp)
```

Mantener el mecanismo request/response solo para CRUD administrativo.

---

#### BE-C2 — Re-suscripción OPC UA sin dedupe efectivo (fuga de handles)

| | |
|---|---|
| **Severidad** | Crítico — **remediado 2026-08-13** |
| **Módulo** | `opcua/subscription.py`, `opcua/models.py` (`reconnect`), `workers/logger.py` |
| **Evidencia** | Claves del dict = `node_id.get_display_name().Text` (str), pero el check es `if node_id not in self.monitored_items[client_name]` (**Node vs str → siempre True**). Cada subscribe crea `subscribe_data_change` y sobrescribe el dict **sin unsubscribe** del handle anterior. Reconnect llama `create_subscription` + re-subscribe de tags. |
| **Complejidad** | Local O(1); **crecimiento server-side** de monitored items en el servidor OPC. |
| **Impacto 24/7** | Después de días de watchdog: CPU/red en el servidor de campo y callbacks duplicados. |

```186:199:automation/opcua/subscription.py
            if node_id not in self.monitored_items[client_name]:
                
                monitored_item = subscription.subscribe_data_change(
                    node_id
                )

                self.monitored_items[client_name].update({
                    node_id.get_display_name().Text: {
```

**Recomendación:**

```python
key = node_id.nodeid.to_string()
existing = self.monitored_items.get(client_name, {}).get(key)
if existing:
    try:
        existing["subscription"].unsubscribe(existing["monitored_item"])
    except Exception:
        pass
# then subscribe and store under `key`
# Prefer ONE Client.create_subscription shared per client, not per tag
```

Backoff exponencial en `reconnect`; no llamar `app.get_tags()` completo — filtrar por `opcua_client_name`.

---

### 3.2 Alto

#### BE-H1 — Lookups CVT O(n) bajo lock

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Módulo** | `tags/cvt.py` |
| **Evidencia** | `get_tag` itera `_tags` aunque la clave del dict **es** el id; `get_tag_by_name` / `get_tag_by_node_namespace` scan lineal. DAS llama `get_tag_by_node_namespace` en cada datachange. |
| **Complejidad** | O(n_tags) por muestra. |
| **Bug adicional** | `is_tag_defined`: `name in self._tags` compara contra **ids**, no nombres. |

```270:274:automation/tags/cvt.py
        for _id, tag in self._tags.items():
            if _id==id:
                return tag
```

**Recomendación:**

```python
self._tags: dict[str, Tag]           # id → Tag
self._by_name: dict[str, str]        # name → id
self._by_namespace: dict[str, str]   # namespace → id

def get_tag(self, id: str):
    return self._tags.get(id)
```

Actualizar índices en `set_tag` / `update_tag` / `delete_tag`.

---

#### BE-H2 — `Buffer.insert(0)` O(n) por muestra

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Módulo** | `buffer.py` |
| **Evidencia** | Roll `forward`: `insert(0, value)` + `pop()` al llenar. DAS puede usar size ~600. Dos buffers (timestamp + values) por tag. |
| **Complejidad** | O(size) por escritura → O(600) × 2 × rate. |

```147:163:automation/buffer.py
        if self.roll.lower()=='forward':
            # ...
            super(Buffer, self).insert(0, value)
```

**Recomendación:**

```python
from collections import deque

class Buffer:
    def __init__(self, size=10):
        self._data = deque(maxlen=size)
    def __call__(self, value):
        self._data.appendleft(value)  # O(1)
        return self
```

---

#### BE-H3 — AlarmManager scans O(n) y comparación incorrecta por tag

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Módulo** | `managers/alarms.py` |
| **Evidencia** | `get_alarm_by_name` / `execute` escanean todas las alarmas. `get_alarm_by_tag` compara `tag == alarm.tag` (str vs `Tag`) → casi siempre falso. `delete_alarm` no hace `detach` del `MachineObserver`. |
| **Complejidad** | O(n_alarms) por evaluación / lookup. |
| **Impacto** | CPU en cambios de tag; observers huérfanos tras delete/reload. |

**Hecho:** mapas `_by_name` y `_by_tag_name`; comparación por `alarm.tag.name`; `detach_from_tag` en `delete_alarm`.

---

#### BE-H4 — PostgreSQL sin pool de conexiones

| | |
|---|---|
| **Severidad** | Alto — **intento fallido; revertido 2026-08-13** |
| **Módulo** | `core.py` `set_db` |
| **Estado código** | `PostgresqlDatabase(...)` (sin pool). `_close_existing_db()` sigue cerrando el handle previo en reconnect. |
| **Hallazgo original** | Sin pool Peewee; al escalar workers/hilos, riesgo de muchas conexiones nativas o reconnect costoso. |
| **Remedio propuesto (P2)** | `PooledPostgresqlDatabase(max_connections=8, timeout=30, stale_timeout=300)`. |

##### Incidente de regresión (2026-08-13) — auditoría de reversión

| Campo | Detalle |
|---|---|
| **Síntoma HMI** | Signup / login: `timeout of 15000ms exceeded` (axios `timeout: 15000` en `hmi/src/services/api.ts`). Sin error visible en UI más allá del timeout. |
| **Síntoma backend** | `POST /api/users/signup` → **HTTP 503** tras **~30.2 s** (`app.log`: `503 … 30.196218`). Coincide con `timeout=30` del pool. |
| **Falso negativo** | Arranque OK (tags/alarmas cargan); `is_db_connected()` True; PG vivo en `127.0.0.1:32800`. El problema **no** era BD caída ni credenciales. |
| **Causa raíz** | Runtime = gunicorn `GeventWebSocketWorker` + greenlets + hilos de máquinas/logger/SAF. Peewee pool asigna **una conexión por greenlet/hilo** y este proceso **no hace `db.close()`** al final de cada request/query → conexiones retenidas en `_in_use` hasta `max_connections=8` → nuevas checkouts esperan `timeout` → `MaxConnectionsExceeded` / error de conexión → signup mapea a **503**. |
| **Por qué no se vio en tests unitarios** | Suite usa SQLite / proceso corto sin gevent + carga concurrente de greenlets. |
| **Acción** | Revertir a `PostgresqlDatabase` en `set_db`. Documentar en código: no reintroducir pool sin ciclo connect/close por request. |
| **Criterio de reintento** | Middleware Flask `before_request`/`teardown_request` (o equivalente) que haga `db.connect(reuse_if_open=True)` / `db.close()`; soak con signup×N concurrente bajo gevent; métrica `_in_use` estable. |
| **Lección** | Pool Peewee + gevent sin teardown = anti-patrón en este producto. Escalabilidad horizontal ≠ pool acotado a ciegas. |

**Estado abierto:** BE-H4 permanece como **riesgo de escalado** (sin pool), no como bug activo. Prioridad baja mientras haya 1 worker gunicorn.

---

#### BE-H5 — Reconnect OPC serializa todos los tags

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Módulo** | `opcua/models.py` `reconnect` |
| **Evidencia** | `tags = app.get_tags()` (serialize con buffers) y loop de `subscribe_opcua`. |
| **Complejidad** | O(n_tags × serialize) por ciclo de watchdog. |

**Recomendación:** iterar solo tags con `opcua_client_name == self.name`; no serializar para filtrar.

---

### 3.3 Medio

| ID | Módulo | Hallazgo | Complejidad | Recomendación | Estado |
|---|---|---|---|---|---|
| BE-M1 | `persistence/journal.py` | PENDING crece hasta `max_disk_bytes` (10 GB) si PG cae días | O(disk) | Alerta lag; cap de filas PENDING + runbook | **Hecho** — cap 5e6, no borra |
| BE-M2 | `persistence/remote.py` | `_lookup_tag` por fila en batch | O(batch × DB) | Cache name→Tags por batch | **Hecho** |
| BE-M3 | `persistence/cycle_dedupe.py` | `_prune_locked` escanea todo `_last` en cada `should_drop` | O(n_tags)/muestra | Prune cada N ms o heap TTL | **Hecho** — 0.5 s |
| BE-M4 | `managers/db.py`, `alarms.py` | `queue.Queue()` sin maxsize; **sin consumidor** en LoggerWorker | Residual | Eliminar o `maxsize` + documentar dead code | **Hecho** — maxsize=1 |
| BE-M5 | `managers/db.py` `attach` | Múltiples `TagObserver` si attach repetido | Leak suave | Attach idempotente | **Hecho** |
| BE-M6 | `tag.py` / `cvt.py` | Fallback `datetime.now()` si falta timestamp | Coste menor | Exigir timestamp del productor | **Hecho** |
| BE-M7 | SocketIO emit en `set_value` | `serialize()` puede incluir buffers | CPU/red | Payload mínimo `{name,value,timestamp,unit}` | **Hecho** |

### 3.4 Bajo / OK

| ID | Estado |
|---|---|
| BE-OK1 | Índice único `TagValue(tag, timestamp)` + `sample_uuid` — **OK** |
| BE-OK2 | SAF ring, circuit breaker, rate limit, métricas health — **OK** |
| BE-OK3 | `RotatingFileHandler` maxBytes + backupCount — **OK** |
| BE-OK4 | `DatabaseHealthService` timeout 2 s + cache 1.5 s — **OK** |
| BE-OK5 | OPC UA variables cache TTL 300 s, max 12 keys — **OK** |
| BE-OK6 | DB audit pending cap 8 — **OK** |
| BE-OK7 | Cycle stamp compartido en state machines — **OK** |

---

## 4. Complejidad algorítmica — mapa objetivo

| Operación | Antes | Ahora |
|---|---|---|
| `CVT.get_tag(id)` | O(n) | **O(1)** |
| `CVT.get_tag_by_name` | O(n) | **O(1)** |
| `CVT.get_tag_by_node_namespace` | O(n) | **O(1)** |
| `CVT.set_value` | O(1) + lock global | **O(1)** + lock por tag |
| `Buffer.__call__` | O(size) | **O(1)** deque |
| `AlarmManager.get_alarm_by_name` | O(n) | **O(1)** |
| `AlarmManager` eval por tag | O(n_alarms) | **O(k)** alarmas del tag |
| `DAS.subscribe` dedupe | roto (siempre insert) | **O(1)** por namespace |
| `JournalWriter.enqueue` | O(1) acotado | mantener |
| `IdempotentBatchInserter` | O(batch) fijo | mantener |
| TagValue range query | O(log n + k) con índice | mantener |

---

## 5. Recomendaciones con ejemplo de código

### 5.1 Índice secundario CVT (mínimo viable)

```python
class CVT:
    def __init__(self):
        self._tags = {}
        self._name_index = {}
        self._namespace_index = {}

    def _index_tag(self, tag: Tag):
        self._name_index[tag.name] = tag.id
        ns = tag.node_namespace
        if ns:
            self._namespace_index[ns] = tag.id

    def get_tag_by_name(self, name: str):
        tid = self._name_index.get(name)
        return self._tags.get(tid) if tid else None
```

### 5.2 Endpoint `/api/health/system` (monitoreo continuo)

Exponer RSS, hilos, profundidad de colas residuales, conteo de monitored items OPC:

```python
import os, resource, threading
def system_snapshot():
    return {
        "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,  # Linux: KB
        "threads": threading.active_count(),
        "cvt_tags": len(CVTEngine()._cvt._tags),
        "opcua_monitored": sum(len(v) for v in DAS().monitored_items.values()),
        "saf": PersistenceHealth().snapshot(),  # ya existe vía /health/saf
    }
```

Alertar si RSS crece > 20 %/día o `opcua_monitored` crece sin cambio de configuración.

### 5.3 Cap de PENDING (política explícita)

```python
# Además de max_disk_bytes:
max_pending_rows: int = 5_000_000
# Si se excede: métrica SAF_PENDING_CAP + backpressure (no borrar PENDING sin política)
```

---

## 6. Plan de acción priorizado

| Prioridad | Plazo sugerido | Ítems | Criterio de hecho |
|---|---|---|---|
| **P0** | Hecho 2026-08-13 | BE-C2, BE-C1 fast-path | Código + `test_performance_hotpath` |
| **P1** | Hecho 2026-08-13 | BE-H1 índices, BE-H2 deque, BE-H5 filtro reconnect | Lookups O(1); Buffer O(1); reconnect sin serialize |
| **P2** | Parcial 2026-08-13 | BE-H3 + BE-M1…M7 **hechos**; **BE-H4 revertido** | Alarmas O(1); cap PENDING; payload SocketIO; **sin** pool PG hasta teardown por request |
| **P3** | Continuo (planta) | Soak 24h/7d + alertas | `test_performance_soak.py` + `PERFORMANCE_RUNBOOK.md`; métricas en `/health/system` |

### Pruebas de envejecimiento sugeridas

1. **Soak adquisición 24 h / 7 d:** N tags @ 1–10 Hz; graficar RSS, `SAF_QUEUE_DEPTH`, `opcua_monitored`.
2. **Watchdog reconnect storm:** forzar disconnect OPC cada 60 s × 24 h; verificar no crecimiento de subscriptions.
3. **Outage PG 4 h:** PENDING crece; al recuperar, lag baja a 0; SENT se GC; RSS no se dispara.
4. **tracemalloc diff** al inicio vs T+24h en objetos `Tag`, `Alarm`, `Buffer`, callbacks socket.

```bash
# Ejemplo local
SAF_SOAK_SECONDS=3600 ./venv/bin/python -m unittest automation.tests.test_store_and_forward
# + script de carga CVT/OPC a añadir en automation/tests/perf/
```

---

## 7. Monitoreo continuo

| Señal | Fuente | Umbral sugerido |
|---|---|---|
| `SAF_QUEUE_DEPTH` | `/api/health/saf` | > 10k sostenido |
| `SAF_REPLICATION_LAG` | health SAF | > 60 s |
| `SAF_DROPPED_FULL` / backpressure | health SAF | cualquier incremento → alerta |
| RSS worker | `/api/health/system` | +20 %/24 h |
| `PENDING_ROWS` / `SAF_QUEUE_DEPTH` | `/api/health/system` + `/saf` | > 10k sostenido |
| `ALARM_COUNT` | `/api/health/system` | salto sin cambio de config |
| `POOL_CONNECTIONS_USED` | `/api/health/system` | **N/A** con `PostgresqlDatabase` (campo queda 0). Reactivar alerta solo si se reintroduce pool + teardown |
| `CVT_LOCK_CONTENTION` | `/api/health/system` | crecimiento monotónico |
| `opcua_monitored` count | `/api/health/system` `OPC_MONITORED_COUNT` | crecimiento sin cambio de config |
| p99 `set_value` | histograma interno / logs sampleados | deriva > 2× baseline |

---

## 8. Relación con auditorías previas

| Documento | Qué cubre | Qué añade esta auditoría |
|---|---|---|
| `STORE_AND_FORWARD.md` | Durabilidad exact-once, journal, soak T-01 | Eficiencia del path caliente y fugas OPC |
| `PERSISTENCE_FLOW.md` | Flujo de persistencia | Complejidad y contención |
| Esta | CPU/RAM/algoritmos 24/7 | — |

La durabilidad puede ser A+ y aun así el proceso degradarse por handles OPC y locks CVT. Ambas dimensiones son necesarias para «Rendimiento Eterno».

---

## 9. Conclusión

El núcleo es **robusto en datos** y el hot path de adquisición ya no serializa el CVT ni re-suscribe OPC a ciegas. P0/P1 y el grueso de P2 viven en código. **BE-H4 quedó abierto a propósito**: el pool Peewee bajo gevent sin teardown por request provocó timeouts de signup/login (503 @ 30 s / axios 15 s) y se revirtió a `PostgresqlDatabase`. La certificación eterna (P3) es el soak 24/7 en planta contra `/api/health/system` y el runbook `audits/PERFORMANCE_RUNBOOK.md` (§5.1 incidente BE-H4).
