# Auditoría: Store-and-Forward con PostgreSQL desconectado

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) · versión de código contrastada **2.9.0** |
| **Documento** | Satélite del canónico 04 ([AUDIT_DB.md](./AUDIT_DB.md)). No sustituye las Partes A–D |
| **Fecha** | 2026-09-29 |
| **Pregunta** | Qué hace cada instancia cuando el historiador PostgreSQL no está, y qué pasa en el hot path cuando el journal vuelve a soltar datos a producción |
| **Método** | Contraste de código. No es un soak de planta. El T-01 archivado en [AUDIT_DB.md](./AUDIT_DB.md) Parte B §6 es un `SIGKILL` de 2 s (`journal_durable=0`) y no certifica latencia de caída |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md) Partes A y B, [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md), [AUDIT_ALARMS.md](./AUDIT_ALARMS.md), [AUDIT_TIME.md](./AUDIT_TIME.md) |
| **Veredicto** | Caída: adquisición, tick de máquina y reconocimiento ISA **siguen**. Durabilidad local **A** para filas que alcanzan `COMMIT`. Drenaje de red **fuera** del tick. Independencia **no total**: un solo lock de SQLite, y el ACK inline vuelve a tocar PostgreSQL en cuanto la sonda dice que está vivo. Certificado de planta **pendiente** |
| **Clasificación** | Auditoría de contraste código vs operación. Hallazgos `SAF-OUT-*` |

---

## 0. Respuesta directa

| Pregunta | Respuesta en código 2.9.0 |
|---|---|
| ¿Hay un documento previo que mida el performance con PostgreSQL caído? | **No como pieza única.** El contrato está repartido. Parte B de [AUDIT_DB.md](./AUDIT_DB.md) absorbe `AUDIT_STORE_AND_FORWARD`. Los umbrales viven en [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md). La retención de disco, en [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) Parte B. Este archivo cierra el hueco operativo |
| ¿La instancia se detiene si PostgreSQL cae? | **No.** El plan de durabilidad es el journal SQLite. PostgreSQL es el plan de distribución |
| ¿Cuánto tarda en persistir un tag? | Encolado al anillo RAM: el `append` no espera PostgreSQL ni el `fsync`. El hilo `SafJournalFlusher` vuelca el anillo cada **10 ms** (`saf_tag_flush_interval_s`), en lotes de **256**, con un `COMMIT` + `fsync` al final del vuelco. Ventana de pérdida ante `SIGKILL`: lo que aún está en el anillo |
| ¿Cuánto tarda una alarma o un ACK? | Dominio crítico: el caller espera `INSERT` + `COMMIT` + `fsync` del journal **antes** de volver. No espera el commit de PostgreSQL si la sonda está en cooldown o `is_db_connected()` es falso |
| ¿El reconocimiento sigue? | **Sí, en memoria primero.** `unack_alarm → ack_alarm` y `rtn_unack → normal` no dependen del historiador. La fila queda `PENDING` y se reintenta sin sumar intentos |
| ¿Hay TTL de los datos no enviados? | **No.** `PENDING` se conserva hasta `SENT`, hasta **5 000 000** filas o hasta **10 GiB**. Lo ya enviado se borra a la **hora** |
| ¿El drenaje al reconectar frena adquisición y máquinas? | El `INSERT` remoto corre en `ReplicationWorker` (hilo de sistema), con presupuesto **0,4 s** por ciclo y tope **10 000** registros/s. El tick de máquina no llama a `replicate_once`. El acoplamiento que queda es el **lock** del journal y el write remoto **inline** del ACK cuando el historiador ya parece vivo |
| ¿Hay p95 de planta? | **No.** No inventar uno |

---

## 1. Dónde vive cada instancia

Cada proceso `PyAutomation()` es una instancia. El journal no es compartido entre nodos.

| Multi-edge | Ruta del journal |
|---|---|
| Activado (default `AUTOMATION_MULTI_EDGE_ENABLED=true`) | `./db/saf/<node_id>/journal.db` |
| Desactivado | `./db/saf/journal.db` |
| `node_id` vacío | `./db/saf/unconfigured/journal.db` |

`<node_id>` se sanea a `[A-Za-z0-9._-]`. El resto de caracteres pasa a `_`.

Archivos del mismo directorio: `journal.db-wal`, `journal.db-shm`, y el archivo de archivo de dead-letter `journal-archive.db` cuando entra el prune.

PostgreSQL es el historiador común. Con la base caída, **cada edge acumula el suyo** y, al volver, **cada `ReplicationWorker` drena el suyo**. No hay un drenaje central. Una fila cuyo `area` / `owner_node` no pertenece al nodo se marca `SENT` local sin insertarla en PostgreSQL (`RemoteReplicator`, rama foreign). Eso no es pérdida de la fila propia; es descarte de una fila que este nodo no debía poseer.

SQLite abre con `timeout=30`, `journal_mode=WAL`, `synchronous=FULL`, `cache_size=-64000` (64 MiB), `mmap_size=256 MiB`, `wal_autocheckpoint=1000`, `foreign_keys=ON`, `check_same_thread=False`. Un solo `sqlite3.Connection` y un `threading.Lock` (`JournalWriter._lock`). El `timeout=30` aplica si **otro proceso** tiene el archivo. Dentro del mismo proceso la espera es el lock de Python, no el busy-timeout.

---

## 2. Planos y hilos

El hot path y el drenaje no comparten hilo. Comparten el lock del journal.

| Plano | Hilo | Qué hace con la base caída | Qué hace al reconectar |
|---|---|---|---|
| Adquisición OPC / CVT | Hilo OPC + greenlets gevent | `set_value` no abre socket de historiador. El sample entra al anillo | Igual. No drena PostgreSQL |
| Máquina de estado | `StateMachineWorker` (gevent) | El tick no llama a `replicate_once` ni a `journal_then_remote` de tags. Publica valores al CVT | El tick sigue sin drenar |
| Evaluación de alarma | Observador del tag | `notify` / `check_condition` solo encola en `AlarmRuntime` (cola máx. **100 000**) | Sigue encolando |
| Transición ISA y ACK unitario | `AlarmTransitionWorker` (hilo, daemon) o el greenlet HTTP del ACK | Transición en memoria; luego `COMMIT` local | Si `historian_write_ready()` pasa, el **mismo** caller ejecuta el `INSERT` remoto |
| ACK masivo | Greenlet HTTP | Memoria con `_defer_persist`; un `COMMIT` de lote vía `acknowledge_many` | Igual: el lote remoto va en ese caller si la sonda está verde |
| Vuelco de tags | `SafJournalFlusher` (daemon) | Cada 10 ms (o al despertar el anillo): drena el anillo y hace `COMMIT`+`fsync` | Igual. No habla con PostgreSQL |
| Drenaje SAF | `ReplicationWorker` (daemon), arrancado en `core.py` | Si el circuito está abierto: solo `_reconnect_only`. Si `is_reachable()` falla: `circuit.failure()` y return **sin** leer filas | `replicate_catchup` hasta 0,4 s; duerme 10 ms si la profundidad previa era > 5 000, si no 200 ms |
| Watchdog de historiador | `LoggerWorker` (hilo, periodo default **10 s**) | `SELECT 1` acotado, marca `ALM.DB.Connection`, cierra el socket del greenlet del logger | Si `ReplicationWorker` está vivo, **no** llama a `replicate_catchup`. El diagrama de [AUDIT_DB.md](./AUDIT_DB.md) §4.2 que pone el drenaje en `LoggerWorker` está **desactualizado** |
| Kick de anillo lleno | `SafForceFlush` (daemon, uno a la vez) | Tras un drenaje forzado del anillo, un `replicate_once` | Puede coincidir con `ReplicationWorker` sobre el mismo lock |
| Compactación | Dentro de `ReplicationWorker.reclaim_idle` | No corre mientras el ciclo arrancó con `pending > 5000` | Al bajar de ese umbral (medido **al inicio** del ciclo): GC, checkpoint `TRUNCATE`, `VACUUM` condicional y, si `pending ≤ 256`, compact del catálogo SQLite |

Contrato de sockets (ya auditado en [AUDIT_DB.md](./AUDIT_DB.md) Parte A, se repite porque condiciona la caída):

- Un objeto Peewee. Pool **prohibido**.
- `journal_then_remote` cierra el socket del caller si no es un rol residente (`_close_ephemeral_historian`).
- El caller del outbox **no** pone `_db_live=False`. Eso es del watchdog. Si lo hiciera, `ALM.DB.Connection` se quedaría pegada.
- `connect_timeout` default **5 s** (`AUTOMATION_DB_CONNECT_TIMEOUT`, techo 30). Sonda `SELECT 1` default **2 s** (`AUTOMATION_DB_PROBE_TIMEOUT`). Cooldown tras peer muerto: `max(connect_timeout, 8)` segundos. Mientras el cooldown está armado, `historian_write_ready()` devuelve `False` **sin** otra sonda.
- libpq no cede a gevent. La sonda del hub va al threadpool de `db_io`. Un `SELECT 1` en el hilo del hub, sin eso, congelaría `on.tag` hasta el timeout TCP del sistema.

---

## 3. Fases de una caída

### 3.1 Corte

1. El remoto deja de contestar. La próxima sonda (`LoggerWorker.check_connectivity` o `historian_write_ready`) falla dentro del presupuesto de `db_io` o entra en cooldown.
2. `set_db_disconnected(True)`, `_db_live=False` en el watchdog, cierre del socket de ese greenlet.
3. `RemoteReplicator.replicate_once` llega a `is_reachable()==False`, cuenta un fallo de circuito y **sale antes de** `fetch_pending`. Las filas siguen `PENDING`. No hay `REPLICATING` nuevo mientras el remoto está caído.
4. A los **5** fallos seguidos el circuito pasa a `open` durante **5 s**. En `open`, el worker solo intenta `_ensure_connection` y no drena. A los 5 s pasa a `half-open` y prueba un ciclo. Un fallo de red no incrementa `attempts` y no manda a dead-letter.
5. Tags nuevos siguen al anillo. Críticos siguen al `COMMIT` local.

### 3.2 Régimen estable sin PostgreSQL

- Adquisición y máquinas corren contra CVT y el anillo.
- Alarmas cambian de estado en `AlarmTransitionWorker`. La historia queda en el journal.
- HMI de tiempo real (`on.tag`) no depende del `COMMIT` remoto. Sí puede notar contención si el flusher o un crítico retienen `JournalWriter._lock`.
- `/api/health/ready` responde **200** con `status=DEGRADED` (`circuit==open` **o** `pg_connected==false` **o** `pending>0` **o** `deadletter>0`).
- `/api/health/db` responde **200**; el campo `connected` dice la verdad. No usar 503 aquí.
- `/api/health/saf` responde **503** solo si `status==critical` (hubo drop o `backpressure`). Con solo `pending>0` el snapshot es `degraded` y el HTTP sigue **200**.
- Docker liveness = `/api/health/ping`. **No** reiniciar el contenedor por `/ready` ni por circuito `OPEN`.
- **No** usar `POST /api/admin/saf/reset` para “recuperar” la caída. `drop_unsent` borra `PENDING`, `REPLICATING`, dead-letter y el anillo. `POST /api/admin/saf/retry` solo resucita dead-letter a `PENDING`.

### 3.3 Vuelta de PostgreSQL

1. El watchdog ve `SELECT 1`, llama `reconnect_to_db` si el handle no estaba vivo, y limpia la alarma de desconexión.
2. `ReplicationWorker` deja de recibir `is_reachable()==False`. Empieza `replicate_catchup`.
3. Cada `replicate_once` pide al rate limiter hasta `replicate_batch_size` (1 000) dentro de una ventana de 1 s cuyo techo es `replicate_rate_per_s` (10 000). Si el limiter devuelve 0, el ciclo escribe 0 y el catch-up **corta** (`written<=0`).
4. `fetch_pending` lee `status=PENDING ORDER BY id ASC`. Dentro de ese lote, el orden de dominio es tag, `alarm_summary`, `alarm_summary_update`, event, log, leak, y después cualquier dominio no listado. El orden entre lotes sigue siendo el `id` (FIFO). Un backlog de tags no adelanta alarmas de un lote futuro; sí las escribe **después** de los tags del mismo lote.
5. ACK remoto = `mark_sent` solo tras éxito, o `IDEMPOTENT_OK` (clave duplicada / unique). Hasta ese momento la fila no es borrable por GC.
6. Reloj: si NTP está habilitado y `|offset| > 1000 ms`, `clock_blocks_replication` deja el ciclo en 0 **sin** abrir el circuito. Offset desconocido o NTP apagado no bloquean.
7. Cuando el `pending` medido al **inicio** del ciclo baja de `catchup_depth` (5 000), ese ciclo además llama `reclaim_idle` (GC de `SENT`, checkpoint, posible `VACUUM`).

Tiempo mínimo de un backlog de 5 000 000 filas al tope de 10 000 registros/s: **500 s (~8,3 min)** de réplica, más el tiempo real de PostgreSQL, el circuito y el limiter. No es un único burst que congele el proceso. Es un hilo ocupado, con el lock tomado solo en los tramos SQLite.

---

## 4. Tiempos de persistencia

### 4.1 Tags (no críticos)

`PersistableRecord.tag_sample` fija `critical=False`. `JournalWriter.append` llama `_enqueue_ring`:

1. Toma `_lock`.
2. Si `pending_durable + len(ring) >= max_pending_rows` (5e6): `JournalBackpressureError`.
3. Si el anillo ya tiene `ring_maxsize` (100 000): el **propio productor** drena el anillo a SQLite y hace `COMMIT` dentro del lock (`_drain_ring_for_backpressure_locked`), y al soltarlo dispara `SafForceFlush`.
4. Si tras ese drenaje el anillo sigue lleno: incrementa `dropped_full` y lanza `JournalBackpressureError`. El sample **no** entra.
5. Si hay sitio: `deque.append` y suelta el lock. El id devuelto es **0** (aún no hay fila).
6. `SafJournalFlusher` despierta (evento o 10 ms), toma el lock, vacía **todo** el anillo en chunks de 256, un `COMMIT` y `fsync` del fd del `journal.db`.

Dedup: `CycleSampleCache` (TTL **2 s**) descarta el mismo tag y valor repetido en la ventana. Contador `SAF_CYCLE_DUPES_DROPPED`. No es pérdida de un cambio; es el mismo sample.

Durabilidad de tag = momento del `COMMIT` del flusher, no el momento del `set_value`. Presupuesto de diseño del anillo: **≤ 10 ms** si el flusher no está bloqueado en el lock ni en un `fsync` largo. Si el anillo llega a 100 000, el presupuesto deja de ser 10 ms: el productor sincroniza el WAL en su propio hilo.

### 4.2 Críticos

`_CRITICAL` = `alarm_summary`, `alarm_summary_update`, `event`, `log`, `leak`.

`append` → `_insert_commit_locked`: un `INSERT` y un `COMMIT`+`fsync` bajo el lock. `append_committed_many` / el batch del ACK hacen un lock y un `COMMIT` para N filas.

Clave de idempotencia: `sample_uuid` canónico, máximo 64 caracteres (SHA-256 hex si no cabe). `UNIQUE` en el journal. Un `IntegrityError` de clave repetida devuelve el `id` existente; no duplica.

`journal_then_remote` (y el batch):

1. `enqueue` / `enqueue_many` **antes** de mirar PostgreSQL. Si esto lanza (`JournalDiskFullError`, `JournalBackpressureError`), la excepción **sale**. El comentario “Never raises” cubre el write remoto, no el journal.
2. Si `connected` es falso o `historian_write_ready()` es falso: vuelve `(None, True)`. Fila `PENDING`. Cero espera de red.
3. Si la sonda pasa: `mark_replicating`, ejecuta `remote_write` **en el caller**, luego `mark_sent` o `mark_pending`.
4. Error de red / `connection already closed` / timeout: `RETRYABLE`, `increment_attempts=False`.
5. Unique violation: `IDEMPOTENT_OK` → `mark_sent`.
6. `IntegrityError` que no es unique, `ValidationError`, JSON malformado, `KeyError`, `TypeError`: `POISON`, sí incrementa `attempts`. A los **5** intentos la fila pasa a `DEAD_LETTER`.
7. Cualquier otra excepción: `RETRYABLE`. Lo desconocido no va a DLQ.
8. `finally`: cierra el socket Peewee del caller efímero.

### 4.3 Clasificador

Marcadores reintentables (texto): `connection already closed`, `cursor already closed`, `ssl syscall`, `eof detected`, `could not connect`, `connection refused`, `connection reset`, `timeout expired`, `timed out`, `network is unreachable`, `temporary failure`, entre otros.

Tipos reintentables: `OperationalError`, `InterfaceError`, `InternalError`, `TimeoutError`, `ConnectionError`, `OSError`, `BrokenPipeError`.

`ValueError` con `unsupported saf domain` es reintentable, no veneno.

---

## 5. Lag

| Señal | Definición en código | Umbral de alarma |
|---|---|---|
| `SAF_QUEUE_DEPTH` | Filas `PENDING`+`REPLICATING` en SQLite **más** lo que aún está en el anillo | `ALM.PERF.SAF_QUEUE` ≥ **5 000** (`perf_saf_queue_threshold`). On-delay de la spec de performance: 3 s. Runbook de [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) cita además `pya_saf_queue_depth > 10000` durante 15 min como página distinta; no es el umbral del tag |
| `SAF_REPLICATION_LAG` | Edad en **segundos** del `created_at` de la fila `PENDING` más vieja (`ORDER BY id ASC LIMIT 1`). No mira `REPLICATING` | El sampler lo pasa a `SAF_REPLICATION_LAG_MS` (×1000). `ALM.PERF.SAF_LAG` ≥ **10 000 ms** |
| `SAF_TAG_INGEST_AGE_S` | Segundos desde el último `INSERT` de dominio `tag` en el journal. 0 si nunca hubo | No es el lag de réplica. Un proceso sin tags nuevos lo deja quieto |
| Lag del anillo | No hay métrica aparte. Es la espera hasta el flusher (diseño 10 ms) más la cola del lock | — |
| Lag de alarma en runtime | `AlarmRuntime._last_lag_ms`: tiempo desde `enqueued_at` hasta `process_event` | `/api/health/alarms` puede ir a 503 si el subsistema viola su presupuesto O(1). Es independiente del lag SAF |

Durante la caída, `SAF_REPLICATION_LAG_MS` crece con la edad del `PENDING` más viejo aunque la adquisición vaya a 1 Hz. La alarma de lag **debe** anunciarse. No significa que el tick se haya frenado.

`SAF_QUEUE_DEPTH` cuenta `REPLICATING`. `fetch_pending` no. Ver hallazgo SAF-OUT-04.

---

## 6. Performance del hot path

### 6.1 Lo que permanece O(1) respecto a PostgreSQL

- `CVTEngine.set_value` no espera un round-trip al historiador.
- El tick de `AutomationStateMachine` / motores de iDetectFugas no abre el journal de réplica. Escribe atributos y tags en memoria; la historia sale por el observador.
- `check_condition` no hace SQL. Encola.
- Con circuito abierto o sonda en cooldown, el ACK no hace `INSERT` en PostgreSQL.

### 6.2 Dónde el hot path sí espera disco

| Situación | Quién espera | Qué espera |
|---|---|---|
| Tag con anillo por debajo de 100 000 | El productor | Solo el lock el tiempo de un `deque.append` |
| Tag con anillo lleno | El productor (adquisición) | Drenaje completo del anillo + `COMMIT` + `fsync`, y luego puede seguir recibiendo `JournalBackpressureError` |
| Flusher con anillo cargado | `SafJournalFlusher`, y cualquiera que quiera el lock | Un solo critical section vacía **todo** el anillo, no un solo lote de 256, y un `fsync` |
| Alarma, evento, log, fuga, ACK | `AlarmTransitionWorker` o el greenlet HTTP | `INSERT` + `fsync` del journal. Con PostgreSQL “vivo”, además el `remote_write` |
| `reclaim_idle` con freelist grande | Quien pida el lock durante el `VACUUM` | Checkpoint `TRUNCATE` y `VACUUM`. Solo se agenda si el ciclo de réplica **arrancó** con `pending ≤ 5000`, o si la cola está vacía (ahí el worker duerme 5 s entre reclamaciones) |
| Otro proceso sobre el mismo `journal.db` | `sqlite3` | Hasta 30 s de `timeout` de conexión |

Conclusión de diseño: la red de PostgreSQL no está en el tick. El disco del journal **sí** puede estarlo, en el flusher, en el crítico y en el productor cuando el anillo rebosa. “Totalmente independiente” no se cumple para el lock. Se cumple para el socket de PostgreSQL del tick de máquina y de la evaluación.

### 6.3 Shed

Histéresis: entra a **50 000** pendientes (`shed_high`), sale a **10 000** (`shed_low`).

Solo aplica a dominio `tag`. Se saltan (siguen journalizándose):

- cualquier dominio no-tag (alarmas, eventos, logs, fugas);
- tag cuyo nombre contiene `LEAK`;
- tag cuyo nombre contiene `FI_`, `PI_`, `DI_` o `TI_`;
- tag con `criticity` `critical` o `5`.

Lo que se tira en shed (contador `SAF_SHED_DROPPED`, sin excepción) es historia analógica no protegida, por ejemplo `SYS.PERF.*`. El log dice “tags paused, alarms/events continue”.

El shed **no** protege del techo de 5e6 ni del de 10 GiB. Esos sí rechazan también a los críticos (`JournalBackpressureError` / `JournalDiskFullError`).

### 6.4 Presión de disco del host

`host_disk_critical_percent` default **85**. El sampler publica `HOST_DISK_USED_PERCENT` y `HOST_DISK_CRITICAL`. El flanco persiste un evento de sistema con cooldown de 3600 s. No borra `PENDING`.

---

## 7. Reconocimiento de alarmas

Secuencia unitaria (`Alarm.acknowledge`):

1. Si el estado no es `unack_alarm` ni `rtn_unack`, no-op (`ALM.ACK.Noop`).
2. `_apply_acknowledge` dispara la transición ISA **en memoria** (`unack_alarm_to_ack_alarm` o `rtn_unack_to_normal`).
3. Sin `_defer_persist`, `_record_transition` llama a `AlarmsLogger.create_record_on_alarm_summary`.
4. Eso arma un `PersistableRecord` crítico y `journal_then_remote`.
5. Con historiador caído: `COMMIT` local, retorno `(None, True)`. El operador ya ve el estado reconocido. Socket y OPC se marcan en el camino de la transición (`put_alarm_state`), no en el commit de PostgreSQL.
6. Al volver la base, `ReplicationWorker` inserta la fila. Unique → se considera enviada.

Secuencia masiva:

1. `_acknowledge_in_memory` pone `_defer_persist` para no pagar un journal por alarma.
2. `acknowledge_many` construye N `PersistableRecord.alarm_create` y un `journal_then_remote_batch` (un `COMMIT` local, una transacción remota si la sonda pasa).
3. Si no hay records de historia y no hay conexión, devuelve 0. La memoria ya cambió en el paso 1.

Shelve, unshelve y supresión diseñada pasan por la misma máquina de estados y el mismo `_record_transition`. Tampoco necesitan PostgreSQL para cambiar el estado en RAM.

Lo que **no** está garantizado:

- Si el `COMMIT` local lanza por disco lleno o por techo de filas, la transición en memoria **ya ocurrió** y la excepción sube desde `enqueue`, fuera del `try` del write remoto. Puede haber ACK en HMI sin fila en el journal. Hallazgo SAF-OUT-02.
- Si `is_history_logged` es falso, `create_record_on_alarm_summary` sale antes del journal. El estado en memoria cambia igual; no hay replay.
- Durante la reconexión, un ACK unitario con sonda verde bloquea al caller en el `INSERT` de PostgreSQL (presupuesto de red del handle, no el de 0,4 s del replicador). Hallazgo SAF-OUT-03.
- Consultas de historia que leen PostgreSQL (`require_db`) responden **503** con `Retry-After` mientras el historiador está caído. El reconocimiento no es una de esas lecturas.

GATE-37 en [AUDIT_ALARMS.md](./AUDIT_ALARMS.md): el seed de alarmas sobrevive a un reinicio de PostgreSQL. El replay en vivo del camino DAS sigue pendiente de campaña. Este documento no lo cierra.

---

## 8. Retención

| Dato | Política | Default | Override |
|---|---|---|---|
| `PENDING` / `REPLICATING` | No hay TTL. Sagrados frente al GC y frente al evict de disco | Hasta enviar o hasta techo | — |
| Techo de filas | `JournalBackpressureError`. Contador `SAF_PENDING_CAP_HITS` | 5 000 000 | `saf_max_pending_rows` |
| Techo de disco del journal (`db`+`-wal`+`-shm`) | Primero borra los `SENT` más viejos en lotes de `gc_batch`. Si no libera, `JournalDiskFullError` | 10 GiB | `saf_max_disk_bytes` |
| `SENT` | `DELETE` si `created_at` es más viejo que el umbral, lotes de 5 000, al final de un `replicate_once` con trabajo o con cola vacía, y en `reclaim_idle` | 3600 s | `saf_gc_sent_after_s`, `saf_gc_batch` |
| `DEAD_LETTER` | Tras `dead_letter_attempts` solo en errores `POISON` | 5 | `saf_dead_letter_attempts` |
| Archivo DLQ | Copia a `journal-archive.db` y `status=ARCHIVED`. No `DELETE` del proceso | 7 días **o** 10 000 filas | `saf_dead_letter_ttl_s`, `saf_dead_letter_max_rows` |
| Anillo | Pérdida solo si no llegó a `COMMIT` (kill) o si salta backpressure | 100 000 | `saf_ring_maxsize` |
| PostgreSQL (`TagValue`, `AlarmSummary`, …) | Fuera del edge. Política DBA | — | — |
| Compact | `VACUUM` del journal si freelist ≥ 64 MiB, intervalo ≥ 3600 s, y `pending ≤ compact_max_pending` (256) después del GC | ver celdas | `saf_compact_*` |

Capacidad orientativa del techo de **filas** (no del de 10 GiB, que depende del tamaño de payload):

| Ritmo que entra al journal | Tiempo hasta 5e6 |
|---|---|
| 100 tags × 1 Hz | ~13,9 h |
| 100 tags × 10 Hz | ~1,4 h |
| 1 000 tags × 1 Hz | ~1,4 h |
| 1 000 tags × 100 Hz (el T-01 de laboratorio, 2 s) | ~50 s |

El shed a 50 000 recorta analógicos no protegidos **antes** de ese techo, así que el tiempo real de tags de proceso de campo es el de las filas que el shed no toca, más alarmas y eventos. 10 GiB puede llegar antes que 5e6 si el payload es ancho o el WAL no se trunca (el checkpoint agresivo espera a cola baja).

`drop_unsent(confirm=True)` es la única vía de código que borra no-enviados a propósito. Exige confirmación. No es recuperación.

---

## 9. Drenaje al restablecer la conexión

`PersistenceOrchestrator.replicate_catchup`:

```
budget = 0,4 s (mínimo efectivo 0,05 s)
mientras monotonic < deadline:
    written = replicator.flush()   # = replicate_once
    si written <= 0: break
```

`ReplicationWorker.run`:

```
pending = pending_count()          # se congela para las decisiones de este ciclo
si pending > 0:
    replicate_catchup()
    dormir 0,01 s si pending > 5000, si no 0,20 s
    si pending <= 5000: reclaim_idle()
si no:
    reclaim_idle()
    soltar socket de historiador
    dormir 5 s
```

`pending` no se relee después del catch-up. Un ciclo que entra con 6 000 no compacta aunque el catch-up deje la cola por debajo de 5 000. Un ciclo que entra con 4 000 sí compacta al terminar sus 0,4 s, aunque el flusher haya metido más filas durante el drenaje.

Dentro de `replicate_once`, el orden que protege al historiador:

1. Scope de nodo inválido → 0, sin circuito.
2. Circuito abierto y aún no cumplió `circuit_open_s` → reconnect only, 0.
3. Reloj NTP fuera de 1 s → 0, sin circuito.
4. No alcanzable → `failure()`, 0, filas intactas.
5. Limiter → 0 si la ventana de 1 s ya dio 10 000.
6. `fetch_pending`.
7. Foreign → `mark_sent` local, sin `INSERT`.
8. Por dominio: `mark_replicating`, write, clasificar, `mark_sent` / `mark_pending`.
9. Si hubo reintentables: `circuit.failure()`. Si no: `circuit.success()`.
10. `gc_sent` de lo ya enviado con más de 1 h.

Exact-once de tags en PostgreSQL: `IdempotentBatchInserter`, `INSERT … ON CONFLICT DO NOTHING` sobre `sample_uuid`. Un reintento después de un commit remoto que no alcanzó a marcar `SENT` no duplica la fila; el unique la da por enviada.

Dominio `leak` (fugas de producto registradas como `PersistableRecord` crítico) va en el mismo drenaje, después de tags y de alarmas **dentro del lote**. No tiene camino aparte. No entra en shed.

---

## 10. Salud, alarmas de sistema y operación

| Endpoint | HTTP en caída sana (journal acepta) | HTTP en backpressure o disco de journal |
|---|---|---|
| `GET /api/health/ping` | 200 | 200. No mirar SAF aquí |
| `GET /api/health/ready` | 200 `DEGRADED` | 200 `DEGRADED` |
| `GET /api/health/db` | 200, `connected=false` | 200 |
| `GET /api/health/saf` | 200, `status=degraded` si hay `PENDING` | **503**, `status=critical` |
| `GET /api/health/alarms` | 200 si el runtime cumple su presupuesto | 503 solo por el subsistema de alarmas, no por la cola SAF |

Snapshot SAF (campos): `status`, `healthy`, `SAF_QUEUE_DEPTH`, `SAF_REPLICATION_LAG` (segundos), `SAF_DROPPED_FULL`, `SAF_DISK_BYTES`, `SAF_BACKPRESSURE`, `SAF_CIRCUIT` (`closed` / `open` / `half-open`), `SAF_LAST_ERROR`, `SAF_MAX_DISK_BYTES`, `SAF_MAX_PENDING_ROWS`, `SAF_PENDING_CAP_HITS`, `SAF_DEADLETTER_COUNT`, `SAF_TAG_INGEST_AGE_S`. El orquestador añade `SAF_CYCLE_DUPES_DROPPED`, `SAF_SHED`, `SAF_SHED_DROPPED`.

Alarmas de performance que deben seguir anunciándose en la caída (son tags de proceso + estado ISA en memoria; su historia también va al journal):

| Tag | Alarma | Condición default |
|---|---|---|
| `{area}.SYS.PERF.SAF_QUEUE` | `{area}.ALM.PERF.SAF_QUEUE` | profundidad ≥ 5000 |
| `{area}.SYS.PERF.SAF_LAG` | `{area}.ALM.PERF.SAF_LAG` | lag ≥ 10000 ms |
| disco de host | `{area}.ALM.PERF.DISK` | ≥ 85 % si así está el spec de disco |
| desconexión | `ALM.DB.Connection` | watchdog, no el outbox |

Variables de entorno de I/O (no son `SafConfig`): `AUTOMATION_DB_CONNECT_TIMEOUT` (5), `AUTOMATION_DB_PROBE_TIMEOUT` (2), `AUTOMATION_DB_IDLE_SESSION_TIMEOUT_S` (300, mínimo aplicado 60), `AUTOMATION_DB_IDLE_IN_TRANSACTION_TIMEOUT_S` (60, mínimo aplicado 10). Keepalives libpq: idle 3, intervalo 1, count 3.

Overrides de `SafConfig.from_app_config`: claves `saf_*` listadas en `automation/persistence/config.py` (ruta, discos, anillo, batch, rate, circuito, GC, DLQ, shed, catch-up, compact, disco de host).

---

## 11. Deriva documental

| Sitio | Dice | Código 2.9.0 |
|---|---|---|
| [AUDIT_DB.md](./AUDIT_DB.md) Parte B §5, fila `ring_maxsize` | 50 000 | `SafConfig.ring_maxsize = 100_000`. El mismo archivo, WD-02, ya dice 100 000 |
| [AUDIT_DB.md](./AUDIT_DB.md) §4.2, diagrama de tags | `LoggerWorker.replicate_once` | El drenaje continuo es `ReplicationWorker`. `LoggerWorker` solo hace catch-up si ese worker **no** está vivo |
| Lag en health vs alarma | `SAF_REPLICATION_LAG` en segundos en el snapshot | `SAF_REPLICATION_LAG_MS` solo existe después del sampler |
| “Never raises” en `journal_then_remote` | El helper no propaga | El `enqueue` sí propaga disco lleno y backpressure |

---

## 12. Hallazgos

| ID | Severidad | Hecho | Efecto en la caída / el drenaje |
|---|---|---|---|
| **SAF-OUT-01** | Observación | Un solo `threading.Lock` para flusher, críticos, `fetch_pending`, `mark_*` y `reclaim_idle` | El tick no hace SQL remoto. Un `fsync` largo o un `VACUUM` de cola baja sí retrasa el `COMMIT` de un ACK y el `append` de un tag |
| **SAF-OUT-02** | Media | La transición ISA del ACK ocurre antes del `COMMIT`. `enqueue` puede lanzar | ACK visible en memoria sin fila journalizada si el journal rechaza por techo o disco. No hay rollback de la máquina de estados |
| **SAF-OUT-03** | Media | Con sonda verde, `journal_then_remote` escribe PostgreSQL en el caller (worker de alarmas o HTTP), no solo en `ReplicationWorker` | Durante el drenaje, un ACK o una transición nueva puede bloquearse en la red del historiador. El presupuesto de 0,4 s no aplica a ese caller |
| **SAF-OUT-04** | Media | `mark_replicating` hace `COMMIT` antes del write remoto. `fetch_pending` solo lee `PENDING`. No hay rewind a `PENDING` en el arranque | Un `SIGKILL` entre `mark_replicating` y `mark_sent`/`mark_pending` deja filas `REPLICATING` contadas en la profundidad y **fuera** del drenaje. `/ready` permanece `DEGRADED`. No ocurre mientras `is_reachable()` falla antes del fetch (caída estable). Ocurre si el proceso muere a mitad de un drenaje |
| **SAF-OUT-05** | Baja | El anillo lleno drena en el hilo productor | Con flusher atrasado, la adquisición deja de ser un `deque.append` y pasa a `fsync` |
| **SAF-OUT-06** | Baja | `reclaim_idle` usa el `pending` del inicio del ciclo | La compactación (lock largo) coincide con la cola ya baja, que es cuando el operador espera que el hot path esté más libre, no durante el pico |
| **SAF-OUT-07** | Info | Foreign `mark_sent` sin `INSERT` | Un payload con scope ajeno desaparece del journal local y no llega a producción. Es aislamiento de nodo, no un reintento |
| **SAF-OUT-08** | Info | T-01 y la plantilla de 24 h de [AUDIT_DB.md](./AUDIT_DB.md) Parte D | No hay número de planta para p95 de tick, de ACK y de drenaje en la misma ventana. Este documento no los inventa |

Nada de lo anterior contradice el veredicto de durabilidad **A+** de [AUDIT_DB.md](./AUDIT_DB.md) para “la fila que hizo `COMMIT` sobrevive a un corte de PostgreSQL y no entra en DLQ por red”. Lo acota: el hot path no es independiente del disco del journal, y el ACK no es independiente de PostgreSQL en el instante en que la sonda vuelve a dar luz verde.

---

## 13. Qué queda explícitamente fuera

- Retención y partición de `TagValue` / `AlarmSummary` en PostgreSQL (DBA).
- Soak 24 h, dos edges, y caos de cable con medición de p95 (plantilla Parte D de [AUDIT_DB.md](./AUDIT_DB.md) y Parte D de [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md)).
- Replay DAS en vivo (GATE-37 residual).
- Rendimiento del algoritmo de fugas, NPW, PPA u otros motores. Esos ticks no llaman al replicador; su costo de CPU es otro documento.
- Arreglo de SAF-OUT-02, SAF-OUT-03 o SAF-OUT-04. Esta auditoría no cambia código.

---

## 14. Mapa de código

| Pieza | Archivo |
|---|---|
| Defaults y overrides | `automation/persistence/config.py` |
| Anillo, `COMMIT`, GC, evict, flusher | `automation/persistence/journal.py` |
| Journal primero, sonda, cierre de socket | `automation/persistence/outbox.py` |
| Clasificación reintento / veneno / unique | `automation/persistence/errors.py` |
| Shed, catch-up, kick | `automation/persistence/orchestrator.py` |
| Circuito, rate limit, orden de dominio, NTP | `automation/persistence/replicator.py` |
| Snapshot | `automation/persistence/health.py` |
| Dedup 2 s | `automation/persistence/cycle_dedupe.py` |
| Worker de drenaje | `automation/workers/replication.py` |
| Watchdog 10 s | `automation/workers/logger.py` |
| Timeouts libpq | `automation/utils/db_io.py` |
| ACK en memoria | `automation/alarms/__init__.py` (`acknowledge`, `_apply_acknowledge`) |
| Historia y batch de ACK | `automation/logger/alarms.py` |
| Cola de transiciones | `automation/alarms/runtime.py` |
| HTTP health | `automation/modules/health/resources/health.py` |
| Umbrales `ALM.PERF.SAF_*` | `automation/utils/performance_alarm_config.py`, `specs/06-PERFORMANCE-ALARMS.md` |
| Arranque del replicador | `automation/core.py` (`replication_worker.start`) |

---

## 15. Comprobaciones que sí cerrarían el certificado

Sin ejecutarlas aquí. Para una campaña posterior, por instancia y con PostgreSQL cortado de verdad (no un mock):

1. Congelar el tick: p95 de `StateMachineWorker` y de `set_value` antes, durante y en los primeros 10 min del drenaje. El pase es que el p95 del tick no escale con `SAF_QUEUE_DEPTH`.
2. ACK de una alarma `unack_alarm` a los 60 s de corte: estado en memoria `ack_alarm` en el mismo request, fila `PENDING` en el journal, `attempts` sin subir, DLQ=0. Al volver PostgreSQL, una sola fila de historia.
3. ACK masivo en el mismo escenario: un `COMMIT` local, estados en memoria, replay sin duplicar.
4. Matar el proceso con `-9` a mitad de `ReplicationWorker` (no durante la caída estable) y medir filas `REPLICATING` que el nuevo proceso no reclama. Confirma o cierra SAF-OUT-04.
5. Llenar anillo (productor más rápido que 10 ms de flush) y medir si `set_value` bloquea en `fsync`. Confirma SAF-OUT-05.
6. No usar `/api/health/ready` como `restart`. Anotar que permanece 200 `DEGRADED` toda la caída.
7. Disco de journal y filas a las 1 h, 4 h y al techo. Separar tags de campo (no shed) de `SYS.PERF` (shed).

---

## 16. Cierre de código SPEC-SAF-HOTPATH-CONTINUITY (2026-09-29)

El código de 2.9.0 en este checkout aplica el spec con las lecturas de [docs/adr/SAF-HOTPATH-CONTINUITY.md](../docs/adr/SAF-HOTPATH-CONTINUITY.md). No sustituye la campaña de §15.

| ID | Estado en código | Qué cambió |
|---|---|---|
| SAF-OUT-01 | Cerrado en código | Lock del anillo distinto del lock del writer. `fetch_pending` y la edad del `PENDING` leen por una conexión `query_only`. `pending_count` sigue siendo el contador en memoria |
| SAF-OUT-02 | Cerrado en código | El ACK unitario y el masivo hacen `COMMIT` antes de la transición ISA. Si el journal rechaza, la RAM no cambia y el HTTP responde 503 `error_type=journal_error`. Al cargar alarmas, `reconcile_pending_acks` aplica filas `PENDING` de ACK que no llegaron a la RAM |
| SAF-OUT-03 | Cerrado en código | `journal_then_remote` y el batch solo journalizan. El `INSERT` remoto queda en `ReplicationWorker` |
| SAF-OUT-04 | Cerrado en código | `JournalWriter.start` pasa `REPLICATING` a `PENDING` sin tocar `attempts` |
| SAF-OUT-05 | Cerrado en código | El productor no drena. Anillo lleno: drop de `SYS.PERF` y análogos, o expulsión de una dropeable para admitir `FI_`/`PI_`/`DI_`/`TI_`/`*leak*`/`criticity=5`. `SafEmergencyDrainer` vuelca a partir del 80 % bajo el mismo writer lock |
| SAF-OUT-06 | Cerrado en código | `reclaim_idle` no corre con drenaje activo ni en los 60 s siguientes a un write crítico, un ACK o un catch-up. El tick y el flush de tags no reinician ese reloj |

Pendiente de campaña (no de este diff): p95 de planta OP1–OP7, soak 24 h con outage de 4 h, bench de 1 M filas. El harness corto está en `automation/tests/test_saf_hotpath_continuity.py` (`SAF_SOAK=1`). `SAF_REGIME` y los contadores nuevos salen en `GET /api/health/saf` y `GET /api/health/system`.
