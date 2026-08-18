# Auditoría compacta: rendimiento backend, memoria y runbook 24/7

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Hot path 24/7 (CPU/RAM/colas O(1)), ciclo de vida de observers, runbook operativo de deriva |
| **Fecha original** | 2026-08-13 / 14 |
| **Compactación** | 2026-08-18 |
| **Fuentes absorbidas** | `AUDIT_BACKEND_PERFORMANCE`, `AUDIT_MEMORY`, `PERFORMANCE_RUNBOOK` |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md) (BE-H4, sockets), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) |
| **Veredicto** | Hot path **A−** (P0/P1/P2 cerrados; **BE-H4 revertido**). Ciclo de vida observers **cerrado** (A− estático). Certificado RSS 24 h (**CA-MEM-1**) y soak 24 h/7 d **pendientes de planta** |
| **Clasificación** | Auditoría de rendimiento · memoria · operación |

---

## 0. Resumen ejecutivo

La durabilidad (SAF) y el hot path de adquisición son problemas distintos. El camino caliente:

```
OPC UA datachange → DAS → CVTEngine.set_value_fast [lock por tag]
  → Tag.set_value → Buffer deque O(1)
  → TagObserver → CycleSampleCache → JournalWriter
  → Alarm MachineObserver → SocketIO serialize_socket mínimo
```

**Objetivo de aceptación 30 días:** RSS del worker gunicorn ±15 % vs baseline; p99 de `set_value` estable; `SAF_QUEUE_DEPTH` y `DAS.monitored_items` / `OPC_MONITORED_COUNT` sin crecimiento monotónico; `TAG_OBSERVER_COUNT` estable con catálogo fijo.

BE-H4 (pool PG) se **revirtió** el 2026-08-13 tras signup/login 503 @ 30 s. No reintroducir. Detalle y teardown posterior: [AUDIT_DB.md](./AUDIT_DB.md).

---

## 1. SOLID en el backend (hot path)

| Letra | Aplicación | Violación original | Estado |
|---|---|---|---|
| **S** | CVT = valores actuales; SAF = durabilidad; DAS = adquisición | Reconnect OPC mezclaba connect + serialize-all + resubscribe | **Cerrado** (`iter_tags_for_opcua_client`) |
| **O** | Colecciones con tamaño/TTL | PENDING sin cap de filas | **Cerrado** (`max_pending_rows=5e6`) |
| **L** | Colas iguales a cualquier tamaño | `Queue` residual sin maxsize | **Cerrado** (`maxsize=1`) |
| **I** | No cargar estructuras enteras para un campo | `get_tags()` en reconnect | **Cerrado** |
| **D** | `IPersistenceGateway` | Locks globales CVT en hot path | **Cerrado** (lock por tag) |

Memoria: cada attach tiene detach (`delete_tag` → `detach_all_observers`; `unsubscribe_to` → `detach_machine`; `delete_alarm` → `detach_from_tag`). No hay `__del__` en Tag/observers: los ciclos Tag ↔ Observer son recolectables **si no queda raíz**.

---

## 2. Hallazgos backend (IDs conservados)

### 2.1 Crítico — remediados 2026-08-13

#### BE-C1 — Contención global en `CVTEngine`

`_request_lock` + `_response_lock` serializaban **todas** las lecturas/escrituras. Throughput ~1/latency_lock.

**Hecho:** `set_value` / `set_value_fast` escriben en `self._cvt` con `Tag._lock`. CRUD (alta/baja de tags) sigue request/response.

#### BE-C2 — Re-suscripción OPC UA sin dedupe

Claves del dict = `str` (display name) pero el check era `if node_id not in …` (**Node vs str → siempre True**). Cada subscribe sobrescribía **sin unsubscribe**. Crecimiento server-side de monitored items.

**Hecho:** clave `nodeid.to_string()`; unsubscribe del handle previo; **una** `create_subscription` por `client_name`; `reset_client` en reconnect.

### 2.2 Alto — remediados salvo BE-H4

| ID | Hallazgo | Complejidad | Estado |
|---|---|---|---|
| **BE-H1** | Lookups CVT O(n); `is_tag_defined` comparaba contra ids | O(n_tags)/muestra | **Hecho** — `_name_index` / `_namespace_index` O(1) |
| **BE-H2** | `Buffer.insert(0)` | O(size) × 2 buffers × rate | **Hecho** — `deque(maxlen)` + `appendleft` |
| **BE-H3** | AlarmManager scan O(n); `get_alarm_by_tag` comparaba str vs `Tag`; `delete_alarm` no detach | O(n_alarms) + observers huérfanos | **Hecho** — `_by_name` / `_by_tag_name`; comparación `alarm.tag.name`; `detach_from_tag` |
| **BE-H4** | Sin pool PG (riesgo de escala) / intento `PooledPostgresqlDatabase(max=8, timeout=30)` | Incidente signup/login | **Revertido**. Pool prohibido. Ver [AUDIT_DB.md](./AUDIT_DB.md) |
| **BE-H5** | Reconnect OPC `get_tags()` serializaba buffers | O(n × serialize)/watchdog | **Hecho** — `iter_tags_for_opcua_client` |

##### Incidente BE-H4 (2026-08-13) — no borrar

| Campo | Detalle |
|---|---|
| HMI | Signup/login `timeout of 15000ms exceeded` (axios 15 s) |
| Backend | `POST /api/users/signup` **503** @ **~30.2 s** = `timeout=30` del pool |
| Falso negativo | Arranque OK; `is_db_connected` True; PG vivo |
| Causa | GeventWebSocketWorker: Peewee pool = 1 conexión por greenlet; **entonces** no había `db.close()` por request → 8 slots llenos → espera 30 s |
| Acción | Revertir a `PostgresqlDatabase`. Hoy hay teardown HTTP, **pero el pool sigue prohibido** hasta soak signup×N + métrica `_in_use` estable |
| Lección | Escalabilidad horizontal ≠ pool acotado a ciegas bajo gevent |

### 2.3 Medio — todos hechos

| ID | Hallazgo | Estado |
|---|---|---|
| **BE-M1** | PENDING hasta 10 GB disco | Cap 5e6 + `JournalBackpressureError` (no borra PENDING) |
| **BE-M2** | `_lookup_tag` por fila | Cache name→tag / unit por batch |
| **BE-M3** | Prune CycleSampleCache en cada `should_drop` | Prune cada 0.5 s |
| **BE-M4** | `Queue()` sin maxsize, sin consumidor | `maxsize=1` |
| **BE-M5** | `attach` duplicaba `TagObserver` | Idempotente |
| **BE-M6** | Fallback `datetime.now()` | `require_producer_timestamp`; `set_value_fast` no usa now() |
| **BE-M7** | `serialize()` con buffers en socket | `serialize_socket()` → `{name,value,timestamp,unit}` ISO UTC |

### 2.4 OK (no tocar)

BE-OK1 índice único `TagValue(tag, timestamp)` + `sample_uuid`. BE-OK2 ring/circuit breaker/health SAF. BE-OK3 `RotatingFileHandler`. BE-OK4 health timeout 2 s + cache 1.5 s. BE-OK5 cache OPC variables TTL 300 s, máx. 12 keys. BE-OK6 DB audit pending cap 8. BE-OK7 cycle stamp en state machines.

### 2.5 Complejidad objetivo (mapa)

| Operación | Antes | Ahora |
|---|---|---|
| `CVT.get_tag(id)` / by name / by namespace | O(n) | **O(1)** |
| `CVT.set_value` | lock global | **O(1)** + lock por tag |
| `Buffer.__call__` | O(size) | **O(1)** |
| `AlarmManager.get_alarm_by_name` | O(n) | **O(1)** |
| Eval alarmas por tag | O(n_alarms) | **O(k)** del tag |
| `DAS.subscribe` dedupe | roto | **O(1)** por namespace |

Health: `GET /api/health/system` → RSS, threads, OPC, CVT, `PENDING_ROWS`, `ALARM_COUNT`, `POOL_CONNECTIONS_USED` (N/A), `SAF_PENDING_CAP_HITS`, `CVT_LOCK_CONTENTION`, `TAG_OBSERVER_COUNT`, `MACHINE_OBSERVER_COUNT`.

Tests: `test_performance_hotpath.py`, `test_performance_soak.py` (`PERF_SOAK_SECONDS`).

---

## 3. Memoria — ciclo de vida (Operación «Memoria Eterna» / «Ciclo de Vida Perfecto»)

### 3.1 Colecciones acotadas (régimen estable)

- `Buffer` → `deque(maxlen)`. DAS ~600 s / `scan_time`, `pop` al borrar tag.
- SAF: ring 50 000, `max_pending_rows=5e6`, `CycleSampleCache` TTL 2 s.
- Alarm/DB managers: `Queue(maxsize=1)`.
- Logs: `DedupeFilter` LRU `max_entries=1000`.
- HMI: historial 720 puntos × 64 tags (LRU). **No se vacía en logout** (política de producto, CA-MEM-8).
- Health: `RSS_MB`, `CVT_TAG_COUNT`, `ALARM_COUNT`, `PENDING_ROWS`, `THREAD_COUNT`, `OPC_MONITORED_COUNT`, `TAG_OBSERVER_COUNT`, `MACHINE_OBSERVER_COUNT`.

iDetectFugas (LDS/PPA/NPW/PFM/Observer/RTTM/FiPy) se audita en el repo de aplicación, no aquí.

### 3.2 Hallazgos memoria

| ID | Sev. | CA | Hallazgo | Estado |
|---|---|---|---|---|
| **MEM-PY-1** | Cerrado | CA-MEM-3 | `delete_tag` no detach | `detach_all_observers()` antes del `pop`. `test_observer_lifecycle` |
| **MEM-PY-2** | Cerrado | CA-MEM-3 | `unsubscribe_to` no detach `MachineObserver` | `detach_machine` + `release()`. Rama `default_tag_name` corregida |
| **MEM-PY-3** | Baja | CA-MEM-4 | CycleSampleCache solo TTL, no `tag.exists` | Tras `delete_tag` muere ≤ 2 s. PASS práctico / FAIL literal |
| **MEM-PY-4** | Baja | CA-MEM-6 | `AsyncStateMachineWorker.drop` no quita de `_machines` | Residual P2: `self._machines.remove(machine)` |
| **MEM-PY-5** | Política | CA-MEM-8 | `tagHistory` persiste en logout | Acotado 720×64; **no** es unbounded |
| **MEM-PY-6** | Baja | CA-MEM-5 | `beforeunload` + `visibilitychange` en `store.ts` sin remove | Vida = pestaña. Aceptable |
| **MEM-PY-7** | Baja | CA-MEM-5 | `setTimeout` Login/Signup sin cleanup | ms. No soak |
| **MEM-PY-8** | Info | CA-MEM-6 | `LoggerWorker` `while True`; `stop_event` después de replicate+sleep | Parada = periodo. Log dice «Alarm worker» (cosmético) |

Lo que está bien (no hallazgos): DAS `reset_client` / `unsubscribe_all`; Buffer `maxlen`; SAF caps; DedupeFilter LRU; `useSocket` limpia maps/intervalos al logout; mayoría de intervalos HMI con cleanup.

### 3.3 Tabla de vida

| Objeto | Debe morir | ¿Muere? |
|---|---|---|
| `Tag` | `delete_tag` | Sale CVT/DAS; observers detach. Vive si `ProcessType.tag` sigue (config, no observer huérfano) |
| `TagObserver` | `delete_tag` | Sí |
| `MachineObserver` | `unsubscribe_to` | Sí |
| `Alarm` | `delete_alarm` | Sí |
| Subscription OPC | `unsubscribe` / `reset_client` | Sí |
| Journal PENDING | ACK / cap | Acotado (backlog, no leak) |
| `SchedThread` | `scheduler.stop()` | Daemon; sí al acabar `run()` |

### 3.4 CA-MEM

| ID | Criterio | Resultado |
|---|---|---|
| **CA-MEM-1** | RSS < 5 % en 24 h (tras warmup 1 h) | **Pendiente soak** |
| **CA-MEM-2** | Conteos Tag/Alarm/Buffer estables | Pendiente soak / OK estático |
| **CA-MEM-3** | Detach al eliminar | **PASS** |
| **CA-MEM-4** | CycleSampleCache poda | PASS práctico |
| **CA-MEM-5** | Intervals/listeners con cleanup | PASS con MEM-PY-6/7 |
| **CA-MEM-6** | Workers paran en `stop()` | PASS (MEM-PY-4/8 menores) |
| **CA-MEM-7** | objgraph: `Tag` vivos ≈ catálogo | Pendiente soak |
| **CA-MEM-8** | Política tagHistory 720×64 | **PASS (política)** |
| **CA-MEM-9/10** | Observer counts instrumentados | `TAG_OBSERVER_COUNT` es **suma** (puede ser > `CVT_TAG_COUNT`). Invariante: estable si catálogo fijo |

Opcional no expuesto: `DAS_BUFFER_KEYS`, `CYCLE_CACHE_SIZE`, `ASYNC_SCHEDULER_COUNT`. Residual P2: `drop()` remove; `CycleSampleCache.invalidate` desde `delete_tag`; opcional rechazar `delete_tag` si una máquina aún apunta al tag.

Soak no ejecutado: gunicorn 1 worker, catálogo real, HMI RT abierta; tracemalloc + objgraph T+0/1h/24h; Chrome heap login / 4 h / logout / re-login.

---

## 4. Runbook de deriva — Operación «Engranaje Perfecto»

Fuente: `GET /api/health/system` y `GET /api/health/saf`.

### 4.1 Señales y umbrales

| Métrica | Umbral | Acción |
|---|---|---|
| `RSS_MB` | +20 % en 24 h vs baseline | Soak + tracemalloc; observers/DAS/SAF |
| `TAG_OBSERVER_COUNT` | Crece con `CVT_TAG_COUNT` fijo | Attach sin detach |
| `MACHINE_OBSERVER_COUNT` | Crece sin cambio de máquinas | `unsubscribe_to` incompleto |
| `OPC_MONITORED_COUNT` | Crece sin cambio de config | `DAS.reset_client`; una subscription por cliente |
| `SAF_QUEUE_DEPTH` / `PENDING_ROWS` | > 10 000 sostenido | Historiador caído o replicador lento; **no** borrar PENDING |
| `SAF_PENDING_CAP_HITS` | Cualquier incremento | Backpressure 5e6; restaurar PG |
| `ALARM_COUNT` | Salto inexplicable | Reload duplicando / attach no idempotente |
| `POOL_CONNECTIONS_USED` | N/A | Si vuelve >0: pool reintroducido — § BE-H4 |
| `DB_CONNECTIONS_*` | Idle 1–3; techo 4; alerta 6 | [AUDIT_DB.md](./AUDIT_DB.md) |
| `CVT_LOCK_CONTENTION` | Crecimiento monotónico | Tasa `set_value` |
| `LOG_ERROR_RATE_PER_MIN` | **> 5** | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) |
| Heap HMI | > 512 MB (`useMemoryWatchdog`) | Toast + `POST /logs/add`; StripCharts |
| Socket listeners DEV | `window.__pyaSocketListeners()` | 1 nativo / evento |
| Long task Trends RT | > 50 ms | Throttle Plotly |

Prometheus (orquestador):

```
(pya_rss_mb / pya_rss_mb offset 24h) > 1.20
delta(pya_tag_observer_count[1h]) > 0 AND delta(pya_cvt_tag_count[1h]) == 0
delta(pya_opc_monitored_count[1h]) > 0 AND config_hash unchanged
pya_saf_queue_depth > 10000 for 15m
pya_log_error_rate_per_min > 5
```

### 4.2 Diagnóstico

1. Capturar health system + saf (T0) vs baseline del mismo worker.
2. `OPC_MONITORED_COUNT` crece → dump keys `DAS.monitored_items`; confirmar `nodeid.to_string()`.
3. `PENDING_ROWS` crece → lag, circuit breaker, PG.
4. RSS crece y OPC/SAF planos → observer counts; si también planos, tracemalloc (`Tag`, `Alarm`, `Buffer`).
5. HMI: DevTools Memory; navegación ×500; `socket.listeners("on.tag").length`.
6. Signup/login timeout con arranque OK → BE-H4, no «BD caída».

```bash
PERF_SOAK_SECONDS=86400 python -m unittest automation.tests.test_performance_soak
python -m unittest automation.tests.test_observer_lifecycle -v
```

### 4.3 Soak operativo

| Prueba | Carga | Éxito |
|---|---|---|
| Backend 24 h / 7 d | 100 tags @ 10 Hz; reconnect OPC cada 5 min; outage PG 4 h | RSS ±15 %; OPC count plano; cola SAF → 0 tras PG; `DB_CONNECTIONS_COUNT` plano ≤ umbral |
| HMI 24 h | 8 StripCharts + 500 cambios de ruta | Heap < 512 MB; listeners nativos constantes |

### 4.4 Corrección típica

| Síntoma | Causa | Fix |
|---|---|---|
| RSS + handles OPC | Re-subscribe sin unsubscribe | `DAS.subscribe` por namespace + `reset_client` |
| CPU alarmas | Scan O(n) | Índices `_by_name` / `_by_tag_name` |
| Disco SAF | Outage largo | Cap 5e6; no borrar PENDING |
| Footer lento | Hidratar 10k alarmas | Preview de 3 |
| Charts acoplados | Selector global `tagHistory` | Selector por `tagNames` + throttle 300 ms |
| Heap HMI | Historial 10k / listeners | 720×64 + EventBus; **no vaciar** historial en logout |
| Signup 503 @ 30 s | Pool + gevent | No reintroducir pool |

### 4.5 Logs, stdout, retención (extracto; detalle [AUDIT_LOGGING.md](./AUDIT_LOGGING.md))

- L1: `RotatingFileHandler` techo `log_max_bytes × (1+backup)` (default ≤ 40 MiB). Dedupe ERROR 60 s.
- Docker/gunicorn: el framework **no** rota el journal del contenedor. Driver `json-file` `max-size=10m` `max-file=3`.
- `VACUUM INTO db/backups/` si SQLite local > 1 GiB. Ops debe podar (`find -mtime +14`).
- Tablas PG **sin TTL** en el framework. Retención = DBA (particiones). No `DELETE` masivo desde la app.

### 4.6 Huso de planta

`AUTOMATION_TIMEZONE` = presentación. Storage UTC. Detalle: [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md).

### 4.7 Post-reconexión de red

Ver [AUDIT_DB.md](./AUDIT_DB.md) §9. Resumen: CRITICAL no basta; `PENDING_ROWS` descendente; cero `already closed`; idle 1–3.

### 4.8 Conteo óptimo de conexiones

Idle persistente 1 worker: **1** (`…:LoggerWorker`). Techo **≤ 4**. Detalle y SQL: [AUDIT_DB.md](./AUDIT_DB.md) §5.

---

## 5. Archivos clave

| Área | Ruta |
|---|---|
| CVT hot path / índices | `automation/tags/cvt.py` |
| Tag lock / observers / serialize_socket | `automation/tags/tag.py` |
| Buffer | `automation/buffer.py` |
| DAS | `automation/opcua/subscription.py` |
| Alarmas | `automation/managers/alarms.py` |
| Attach idempotente | `automation/managers/db.py` |
| `set_db` / sin pool | `automation/core.py` |
| Health | `automation/modules/health/resources/health.py` |
| Tests | `test_performance_hotpath.py`, `test_performance_soak.py`, `test_observer_lifecycle.py` |
| HMI historial / socket | `hmi/src/store/slices/tagsSlice.ts`, `hmi/src/services/socket.ts` |
