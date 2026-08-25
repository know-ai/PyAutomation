# Auditoría compacta: Store-and-Forward y flujo de persistencia

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Durabilidad ante caída de BD; camino TagValue/Alarmas/Eventos/Logs; exact-once; T-01 |
| **Fecha baseline** | 2026-08-13 (cola RAM = C+ / B−) |
| **Re-auditoría** | 2026-08-13 (Directiva Fénix + Exact-Once + Ciclo Atómico + Milisegundo Exacto) |
| **Compactación** | 2026-08-18 |
| **Aislamiento Bulkhead** | 2026-08-25 — replicación por dominio y por muestra; drop de tags ausentes a 3 reintentos |
| **Controles ops** | 2026-08-25 — `POST /api/admin/saf/retry` y `/saf/reset` desde `/performance`; `drop_unsent(confirm=True)` es el único discard intencional de PENDING |
| **Fuentes absorbidas** | `STORE_AND_FORWARD`, `PERSISTENCE_FLOW`, `T01_SOAK_LAST_RUN` |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md) (hub/reconnect no revocan A+), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (journal por `node_id`), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md) (sync por fila) |
| **Veredicto** | **A+** durabilidad. **A** aislamiento de fallos en código (CA-ISOLATION-01…04). **A−** planta: CA-ISOLATION-05 (Txn/min 1 h) pendiente |
| **Clasificación** | Auditoría de arquitectura de datos |

---

## 0. Contrato vigente (post-Fénix)

El historiador remoto (PostgreSQL / MySQL / SQLite de aplicación) es el **plan de distribución**. SQLite WAL es el **Plan A de durabilidad**.

```
Hot path (CVT / Alarmas / Eventos / Logs)
        │  IPersistenceGateway.enqueue()
        ▼
┌─────────────────────────────────────────┐
│  Ring RAM acotado (solo tags, ≤10 ms)   │
│  JournalWriter SQLite WAL + FULL sync   │  ← source of truth
│  persistence_journal (PENDING/SENT)     │
│  path: ./db/saf/<node_id>/journal.db    │  (legacy: ./db/saf/journal.db)
└───────────────┬─────────────────────────┘
                │ ReplicationWorker (LoggerWorker)
                │ batch + rate limit + circuit breaker
                ▼
        Remote DB  ──ACK──►  status=SENT  ──GC SENT only──►
```

**OPC UA no habilita el historiador.** OPC es un **productor de valores** hacia el CVT. El historiador se dispara por cualquier `Tag.set_value` → `notify` → `TagObserver` cuando el tag tiene observer (`db_manager.attach` al crear/cargar con BD conectada). Tags internos de iDetectFugas (`leak`, `threshold`, …) se historizan **sin** `opcua_address`.

La cola RAM `_tag_queue` quedó **huérfana** para escritura. `TagObserver.update()` no escribe ahí. El worker llama `replicate_once()` sobre el journal.

Adquisición **nunca espera a la red**. Enqueue extranjero en multi-edge se rechaza ([AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md)).

---

## 1. SOLID

| Letra | Componente |
|---|---|
| **S** | `JournalWriter` (disco) ≠ `RemoteReplicator` (red) ≠ `IdempotentBatchInserter` |
| **O** | `IPersistable` / `PersistableRecord` para tag, alarma, evento, log |
| **L** | `IRemoteDB` + `NullRemoteDB` / `FakeRemote` en tests de caos |
| **I** | `IHealthProbe` separado de `IReplicationWorker` |
| **D** | CVT no importa sqlite3/psycopg2; `TagObserver` usa `get_persistence_gateway()` |

Capas: CVT = valor actual; `Tag.notify` = notificación; `PersistableRecord` = JSON canónico; journal = verdad local; replicator = PENDING→remoto; mapper = JSON→fila; inserter = SQL exact-once; `DataLogger.read_*` = lectura HMI.

---

## 2. Baseline (antes de Fénix) — por qué no era SAF

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
| SAF-07 | Multi-path | ✅ Tags, alarmas, eventos, logs |
| SAF-08 | Replay controlado | ✅ Batch + rate limit + circuit breaker |
| SAF-09 | Observabilidad | ✅ `/api/health/saf` (503 si critical) |
| SAF-10 | Retención | ✅ `VACUUM INTO` + checksum; GC **solo SENT** |

Nota ponderada ≈ 4.8 / 5 → **A+**.

**Descartar PENDING** no forma parte del hot path. `JournalWriter.drop_unsent(confirm=True)` (API `POST /api/admin/saf/reset`, rol admin/sudo, modal `CONFIRMAR` en `/performance`) es la única vía operativa. Forzar un ciclo: `POST /api/admin/saf/retry`. Auditoría: Events `SAF queue emptied` / `SAF retry requested`. Runbook: [docs/node-performance-runbook.md](../docs/node-performance-runbook.md). Tests: `test_ops_controls.py`.

### Hallazgos cerrados

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

## 3. Operaciones de cierre A+

### 3.1 Exact-Once

- `TagValue.timestamp` resolución **ms** (`TimestampField(resolution=3)`). Ticks legacy µs se normalizan en `ensure_schema` (colapsa pares del mismo ms y luego ÷1000).
- Firma atómica: `sample_uuid` (idempotency_key del journal).
- `IdempotentBatchInserter` es la **única** clase que habla de conflictos SQL. `RemoteReplicator.flush()` solo llama `IRemoteDB.batch_insert_with_dedupe`.

**Criterio:** tras SIGKILL y reconexión, el historiador contiene exactamente las muestras durable del journal; un segundo flush no crea duplicados.

### 3.2 Ciclo Atómico

El framework inyecta `machine.cycle_timestamp` antes de `machine.loop()` y un filtro de dedupe en el gateway. Las máquinas **no** se modifican.

| Fase | Capa | Efecto |
|---|---|---|
| 1 | `stamp_machine_cycle` + `ProcessType.set_value` | Escrituras del mismo `loop()` comparten UTC. UNIQUE remoto colapsa micro-duplicados |
| 2 | `CycleSampleCache` en `enqueue` | 2ª muestra mismo tag/valor/ciclo **no entra al journal**. Métrica `SAF_CYCLE_DUPES_DROPPED`. TTL 2 s |

El histórico refleja el valor por ciclo de procesamiento, no cada `set_value`.

### 3.3 Milisegundo Exacto

Payload journal de tags en ms (`timebase.TAGVALUE_TIMESTAMP_RESOLUTION = 3`). Residuos 73–403 µs caen en el mismo tick. Events / AlarmSummary / Logs: resolución por defecto Peewee (AlarmSummary ya escala a ms en `ensure_schema`). Lecturas HMI aceptan ticks legacy s / ms / µs (`DataLogger._as_epoch_seconds`).

### 3.4 Bulkhead — aislamiento de fallos (2026-08-25)

Un tag inexistente en el remoto, un evento fallido o un `IntegrityError` de alarma **no** deben detener los demás dominios ni las demás muestras del mismo ciclo.

| Principio | Implementación |
|---|---|
| Aislamiento por dominio | `RemoteReplicator.replicate_once` itera `_ordered_domain_batches` (`tag` → alarmas → events → logs). Excepción o PENDING de un dominio no aborta los demás |
| Aislamiento por muestra | `write_batch_outcomes` devuelve `list[bool]` por elemento; `mark_sent` / `mark_pending` son por id. Insert de TagValue: lote, y si falla, reintento **por fila** |
| Degradación controlada | Tag ausente en `Tags` remoto: PENDING hasta 3 misses, luego ACK + log `Dropping sample for missing tag … after 3 retries` + `request_full_sync` (no bloquea el hot path) |
| Eventos / alarmas / logs | `_write_*_outcomes` captura excepción **por muestra**; no hay transacción global del lote |

| ID | Criterio | Resultado | Evidencia |
|---|---|---|---|
| **CA-ISOLATION-01** | Tag inexistente no bloquea eventos ni alarmas del mismo ciclo | **PASS** | `TestReplicatorDomainIsolation.test_missing_tag_does_not_block_events_or_alarms` |
| **CA-ISOLATION-05** | Txn/min en reposo < 50 con errores de integridad persistentes | **PENDIENTE** | Soak planta 1 h + dashboard `DB_TXN_PER_MIN` (proceso, no clúster) |

**No A+ de aislamiento de planta** hasta CA-ISOLATION-05. El A+ de durabilidad (T-01 / exact-once) no se revoca.

---

## 4. Flujo activo (paradoja OPC)

### 4.1 Creencia vs código

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

### 4.2 Hot path TagValue

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

### 4.3 Alarmas / eventos / logs

Mismo outbox, dominios distintos. Críticos: COMMIT síncrono local (`is_critical`). `journal_then_remote` cierra el socket Peewee del caller si no es LoggerWorker ([AUDIT_DB.md](./AUDIT_DB.md)).

Bitácora operacional journaliza con historiador caído ([AUDIT_LOGGING.md](./AUDIT_LOGGING.md) CA-OL-1).

---

## 5. Caps, métricas, health

| Guardrail | Default | Comportamiento |
|---|---|---|
| `ring_maxsize` | 50 000 | Drop + backpressure |
| `max_pending_rows` | 5e6 | `JournalBackpressureError`; `SAF_PENDING_CAP_HITS` |
| `max_disk_bytes` | 10 GiB | Evict SENT; si no basta → `JournalDiskFullError` + Event `SAF disk full` (cooldown 60 s) |
| `gc_sent_after_s` | 3600 | GC post-ACK |
| `replicate_rate_per_s` | 10 000 | Rate limit |

`GET /api/health/saf`: `SAF_QUEUE_DEPTH`, `SAF_REPLICATION_LAG`, `SAF_DROPPED_FULL`, `SAF_CYCLE_DUPES_DROPPED`, `PENDING_ROWS`. 503 si estado crítico.

---

## 6. T-01 Soak — last run certificada

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

## 7. Criterio de aceptación y tests

> Tras SIGKILL y reconexión, el historiador remoto contiene exactamente las muestras durable del journal; un segundo flush no crea duplicados.

```bash
python -m unittest automation.tests.test_store_and_forward -v
python -m unittest automation.tests.test_store_and_forward.TestReplicatorDomainIsolation -v
```

Aislamiento: `test_missing_tag_does_not_block_events_or_alarms` (CA-ISOLATION-01). DataLogger/Machines: `automation.tests.test_filtered_tag_integrity` (CA-ISOLATION-03/04).

Outage de cable: HMI viva + PENDING creciente + replica al volver = [AUDIT_DB.md](./AUDIT_DB.md) (timeout). `connection already closed` post-CRITICAL = handle muerto, no fallo de journal.

**No hacer:** borrar PENDING; `gevent.Timeout` alrededor de libpq; segundo `Proxy`; pool Peewee.

---

## 8. Archivos clave

| Pieza | Ruta |
|---|---|
| Contratos | `automation/persistence/contracts.py` |
| Config / path journal | `automation/persistence/config.py` |
| Journal WAL | `automation/persistence/journal.py` |
| Replicador | `automation/persistence/replicator.py` |
| Gateway / enqueue foreign | `automation/persistence/orchestrator.py` |
| Outbox `journal_then_remote` | `automation/persistence/outbox.py` |
| Cycle stamp | `automation/workers/state_machine.py` |
| Cycle timestamp | `automation/models.py` |
| Cycle dedupe | `automation/persistence/cycle_dedupe.py` |
| Remote + `_write_logs` | `automation/persistence/remote.py` |
| Exact-once SQL | `automation/persistence/idempotent_insert.py` |
| Timebase | `automation/timebase.py` |
| T-01 producer | `automation/persistence/soak_producer.py` |
| TagObserver | `automation/tags/tag.py` |
| Events / Alarms / Logs | `automation/logger/{events,alarms,logs}.py` |
| Attach | `automation/managers/db.py` |
| Worker | `automation/workers/logger.py` |
| Health | `GET /api/health/saf` |
| Controles ops | `POST /api/admin/saf/retry`, `POST /api/admin/saf/reset` · `ops_controls.py` |
| Tests | `automation/tests/test_store_and_forward.py` + `test_ops_controls.py` |
