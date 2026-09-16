# Auditoría compacta: Store-and-Forward y flujo de persistencia

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
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md) (hub/reconnect no revocan A+), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (journal por `node_id`), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md) (sync por fila), [AUDIT_LONG_RUN_CONTINUITY.md](./AUDIT_LONG_RUN_CONTINUITY.md) (DLQ archivada) |
| **Veredicto** | **A+** durabilidad (incluye outage PG / handle stale: no DLQ). **A** aislamiento de fallos en código (CA-ISOLATION-01…04 + P0-1…P0-8). **A−** planta: CA-ISOLATION-05 (Txn/min 1 h) pendiente |
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

## 1. SOLID

| Letra | Componente |
|---|---|
| **S** | `JournalWriter` (disco) ≠ `RemoteReplicator` (red) ≠ `IdempotentBatchInserter` |
| **O** | `IPersistable` / `PersistableRecord` para tag, alarma, evento, log, **leak** (producto) |
| **L** | `IRemoteDB` + `NullRemoteDB` / `FakeRemote` en tests de caos |
| **I** | `IHealthProbe` separado de `IReplicationWorker` |
| **D** | CVT no importa sqlite3/psycopg2; `TagObserver` usa `get_persistence_gateway()`. SQL de `leaks` **no** vive en el core: `register_domain_writer("leak", fn)` |

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
| SAF-07 | Multi-path | ✅ Tags, alarmas, eventos, logs, **leak** (writer de producto) |
| SAF-08 | Replay controlado | ✅ Batch + rate limit + circuit breaker **desacoplado de attempts** |
| SAF-09 | Observabilidad | ✅ `/api/health/saf` (503 si critical); `/api/health/ready` siempre 200 (`DEGRADED` si circuito OPEN) |
| SAF-10 | Retención | ✅ `VACUUM INTO` + checksum; GC **solo SENT**; prune DLQ **archiva**, no borra proceso |
| SAF-11 | Outage ≠ veneno | ✅ `classify_saf_error`: retryable no incrementa attempts; DLQ solo poison |

Nota ponderada ≈ 4.8 / 5 → **A+**.

**Descartar PENDING** no forma parte del hot path. `JournalWriter.drop_unsent(confirm=True)` (API `POST /api/admin/saf/reset`, rol admin/sudo, modal `CONFIRMAR` en `/performance`) es la única vía operativa de **borrado**. Forzar un ciclo **sin perder histórico**: `POST /api/admin/saf/retry` → `resurrect_dead_letters` + `circuit.reset` + `replicate_catchup`. **No** usar `/saf/reset` para recuperar un outage de PG. Auditoría: Events `SAF queue emptied` / `SAF retry requested`. Runbook: [docs/node-performance-runbook.md](../docs/node-performance-runbook.md). Tests: `test_ops_controls.py`, `TestSafNuclearP0`.

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
| Aislamiento por muestra | `write_batch_outcomes` devuelve `RowOutcome` (`ok` + `error`) por elemento, con adaptador `list[bool]`; `mark_sent` / `mark_pending` son por id y **por dominio**. Un fallo de `event` no toca attempts de `tag`. Insert de TagValue: lote, y si falla, reintento **por fila** |
| Degradación controlada | Tag ausente en `Tags` remoto: PENDING hasta 3 misses, luego ACK + log `Dropping sample for missing tag … after 3 retries` + `request_full_sync` (no bloquea el hot path) |
| Eventos / alarmas / logs | `_write_*_outcomes` captura excepción **por muestra**; no hay transacción global del lote |

| ID | Criterio | Resultado | Evidencia |
|---|---|---|---|
| **CA-ISOLATION-01** | Tag inexistente no bloquea eventos ni alarmas del mismo ciclo | **PASS** | `TestReplicatorDomainIsolation.test_missing_tag_does_not_block_events_or_alarms` |
| **CA-ISOLATION-05** | Txn/min en reposo < 50 con errores de integridad persistentes | **PENDIENTE** | Soak planta 1 h + dashboard `DB_TXN_PER_MIN` (proceso, no clúster) |

**No A+ de aislamiento de planta** hasta CA-ISOLATION-05. El A+ de durabilidad (T-01 / exact-once / outage≠DLQ) no se revoca.

### 3.5 Blindaje nuclear — outage ≠ veneno (2026-09-15)

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

`GET /api/health/saf`: `SAF_QUEUE_DEPTH`, `SAF_REPLICATION_LAG`, `SAF_DROPPED_FULL`, `SAF_CYCLE_DUPES_DROPPED`, `PENDING_ROWS`, `SAF_CIRCUIT`, `SAF_DEADLETTER_COUNT`. 503 si estado crítico.

`GET /api/health/ready`: siempre **200**. Cuerpo `ok` o `DEGRADED` (circuito OPEN, PG down, pending/DLQ). **No** usarlo como probe `restart: always`. Liveness Docker = `/api/health/ping`.

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
python -m unittest automation.tests.test_store_and_forward.TestSafNuclearP0 -v
python -m unittest automation.tests.test_store_and_forward.TestReplicatorDomainIsolation -v
python -m unittest automation.tests.test_store_and_forward.TestSafJournal -v
```

Aislamiento: `test_missing_tag_does_not_block_events_or_alarms` (CA-ISOLATION-01). DataLogger/Machines: `automation.tests.test_filtered_tag_integrity` (CA-ISOLATION-03/04). Poison legado: `test_dead_letter_escapes_poison_and_leaves_pending`.

Outage de cable: HMI viva + PENDING creciente + replica al volver = [AUDIT_DB.md](./AUDIT_DB.md) (timeout). `connection already closed` post-CRITICAL = handle muerto, **retryable** (attempts intactos, DLQ=0). No es fallo de journal.

**No hacer:** borrar PENDING; `gevent.Timeout` alrededor de libpq; segundo `Proxy`; pool Peewee; tratar UNIQUE TagValue como poison; `restart: always` sobre `/health/ready` o `/health/saf` cuando el circuito está OPEN.

---

## 8. Archivos clave

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
