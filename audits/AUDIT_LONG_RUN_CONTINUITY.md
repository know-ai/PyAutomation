# AUDIT_LONG_RUN_CONTINUITY — Continuidad día 1 vs día 1000

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + despliegue planta iDetectFugas |
| **Alcance** | Degradación a 1 / 10 / 100 / 1000 días: disco, RAM, CPU, locks, colas, historiador, catálogo, logs. **No** es spec de producto. **No** incluye cambios de código (solo evidencia y plan). |
| **Fecha** | 2026-08-27 |
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](./AUDIT_NODE_PERFORMANCE_DASHBOARD.md) |
| **Evidencia planta** | N1 `intelcon2` / 192.168.1.80 · `journal.db` 331 MiB + WAL 50 MiB · PENDING=45 · SENT=190 712 · freelist 217 MiB · `auto_vacuum=0` |
| **Veredicto** | Hot path y colas **A−** (acotados en código). Disco SAF **B+** hasta desplegar `reclaim_idle`. Historiador PG y `DEAD_LETTER` **B−** (crecimiento de planta, no de proceso). Certificado día-1000 **pendiente de soak**. |
| **Clasificación** | Auditoría de continuidad operacional · degrada-ción · grado planta 24/7 |

---

## 0. Pregunta fundamental

**¿El nodo del día 1000 es tan ligero y predecible como el del día 1, con catálogo fijo y red recuperable?**

Respuesta honesta: **el proceso sí está diseñado para no hincharse en RAM/CPU del hot path**. El disco local y el historiador remoto **no** vuelven solos al tamaño del día 1 si no hay compactación + política de retención. Eso no es un leak de Python; es física de SQLite y de tablas de historia.

```
Día 1     proceso ligero + journal pequeño + PG vacío
Día 10    mismo RSS; journal en tamaño pico de la peor outage (hasta compactar)
Día 100   mismo RSS; PG crece lineal con TagValue/Events/Logs
Día 1000  mismo RSS si catálogo fijo; disco host = journal compactado + PG + backups
```

---

## 1. Horizonte temporal (qué debe pasar)

| Horizonte | Régimen | Lo que debe permanecer plano | Lo que puede crecer (y cómo se corta) |
|---|---|---|---|
| **Día 1** | Arranque, catálogo caliente | RSS worker, `set_value` p99, `SAF_QUEUE_DEPTH` ≈ flujo vivo | Journal WAL transitorio |
| **Día 10** | Outage PG de horas + catch-up | Tras drenar: PENDING ≈ decenas, no millones | SENT 1 h + freelist; **antes** el `.db` no encogía |
| **Día 100** | Operación continua | Mismas métricas de proceso; `TAG_OBSERVER_COUNT` estable | Historiador PG (TagValue) ~ lineal con Hz × tags |
| **Día 1000** | Años de planta | Hot path O(1); ring ≤ 100k; logs L1 rotados | Sin retención DBA, PG es el único unbounded “oficial” |

Objetivo de aceptación (alineado con [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md)):

- RSS gunicorn **±15 %** vs baseline a catálogo fijo.
- `SAF_QUEUE_DEPTH` sin crecimiento monotónico con PG sano.
- `SAF_DISK_BYTES` **después de compactar** en el orden del flujo vivo (MiB, no el pico de la outage).
- `DAS.monitored_items` / `TAG_OBSERVER_COUNT` estables.
- p99 `set_value` no degrada con journal gordo (post O(1) `pending_count`).

---

## 2. Qué ya está acotado (día 1 = día 1000 en proceso)

| Recurso | Techo | Dónde |
|---|---|---|
| Ring RAM tags | 100 000 | `SafConfig.ring_maxsize` |
| PENDING durable | 5 000 000 → backpressure | `max_pending_rows` |
| Disco journal (hard) | 10 GiB | `max_disk_bytes`; evict SENT; si no basta → `JournalDiskFullError` |
| Shed analog history | high 50k / low 10k | tags pausados; eventos/alarmas siguen |
| SENT | GC TTL **1 h**, lotes 5 000 | `gc_sent` |
| CycleSampleCache | TTL 2 s | `cycle_dedupe.py` |
| Buffer OPC / SM | `deque(maxlen=…)` | `buffer.py`, DAS, core |
| Trend PERF | ~68 puntos / 5 min | `metrics_sampler.py` |
| Cooldown audit | cap 256 | `audit_metrics.py` |
| L1 `app.log` | 10 MiB × 3 backups ≈ 40 MiB | `RotatingFileHandler` |
| Docker json-file (iDetectFugas) | 10m × 7 ≈ 70 MiB | `compose/docker-compose.yml` |
| Redis sesión | 64 MiB LRU | compose |
| Health `/health/saf` | O(1) `pending_count` + LIMIT 1 lag | post-parche 2026-08-27 |
| Hot path `pending_count` / shed / cap | **O(1)** RAM | `_pending_durable + len(_ring)`; COUNT solo al abrir y reconcile 30 s |

Esto es lo que permite afirmar: **con catálogo fijo, el worker no “engorda” por día**.

---

## 3. Hallazgo planta 2026-08-27 — disco ≠ cola

N1 Linea1, cola ya drenada:

| Magnitud | Valor | Lectura |
|---|---|---|
| PENDING / REPLICATING | 45 | Flujo vivo. No hay lag de réplica. |
| SENT | 190 712 | Catch-up marcado SENT en la última hora (`updated_at` 13:11–14:11 UTC). TTL 1 h **aún no aplica**. |
| `journal.db` | 331 MiB | Tamaño de fichero, no de filas vivas. |
| WAL | 50 MiB | No se truncaba en idle. |
| Freelist | 217 MiB (55 393 páginas) | Huecos de DELETE previos. `PRAGMA auto_vacuum=0`. |
| Gauge HMI | `SAF_DISK_BYTES` = db+wal+shm | Correcto; **no** es “cola”. |

**Antes (código en imagen `3.0.0`):** el GC borra SENT a la hora, pero SQLite **no devuelve páginas al SO**. El gauge se queda en el pico. Estrategia incompleta para “día 10 ligero”.

**Ahora (checkout PyAutomation, no desplegado):** `JournalWriter.reclaim_idle()` en `ReplicationWorker` cuando la cola está quieta:

1. `gc_sent` (igual que antes, TTL 1 h).
2. `PRAGMA wal_checkpoint(TRUNCATE)` si WAL ≥ 8 MiB o cada 30 s.
3. `VACUUM` si `pending ≤ 256`, freelist ≥ 64 MiB, y ≥ 1 h desde el último compact.

**Estrategia de disco (intencional, no instantánea):**

```
t=0      Cola drenada → PENDING ≈ flujo vivo
         Disco sigue alto (SENT < 1 h + freelist + WAL)
t≈0+     TRUNCATE WAL → baja el WAL (decenas de MiB)
t≈1 h    GC borra SENT → freelist aún más grande, .db igual de gordo
t≥1 h    VACUUM idle → el SO recupera el pico
```

VACUUM **no** va en el enqueue. Corre bajo el `RLock` del journal: unos segundos de cola de tags en RAM (ring) y eventos críticos esperan el lock. Frecuencia máx. ~1/h y solo con cola baja. Es el trade-off planta: compactar sin matar detección.

Hasta reinstalar wheel + reiniciar gunicorn, N1 sigue el comportamiento **antes**.

---

## 4. Matriz de riesgos residuales (día 1000)

### 4.1 P1 — deben cerrarse para certificado nuclear

| ID | Riesgo | Día 1 | Día 1000 sin remediar | Mitigación actual | Hueco |
|---|---|---|---|---|---|
| **LR-DLQ-1** | Filas `DEAD_LETTER` sin GC | 0 | Poison pills + tags crónicos acumulan disco e índice UNIQUE | Solo `drop_unsent(confirm=True)` de operador | Falta TTL/cap de DLQ (p. ej. 7–30 d o N filas) |
| **LR-PG-1** | `TagValue` / `Events` / `Logs` en PG **sin TTL en framework** | Vacío | Lineal con Hz × tags × 1000 d | Política DBA (particiones, `pg_partman`, archive) | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) LOG-H5: retención = planta |
| **LR-VAC-1** | VACUUM journal bajo el mismo lock que enqueue | N/A | Compact de cientos de MiB puede stallar `set_value` segundos | Solo idle, 1/h, pending ≤ 256 | Medir p99 durante compact; si duele: `incremental_vacuum` por lotes |
| **LR-CAT-1** | `catalog.db` WAL sin VACUUM | Pequeño | Churn de sync infla fichero | Backoff, orphans TTL 5 min / 5 reintentos | Compact idle análogo al journal |
| **LR-BKP-1** | `LoggerWorker.sqlite_db_backup` → `./db/backups/` **sin poda** | 0 ficheros | Un `.db` cada vez que historian SQLite > 1 GiB | Solo aplica historiador SQLite local (no PG) | `saf_backup_size_bytes` en config **no está cableado**; umbral hardcoded 1 GiB |

### 4.2 P2 — degradación silenciosa, no explosiva

| ID | Riesgo | Notas |
|---|---|---|
| **LR-SYS-1** | `GET /health/system` y `_sample_field` (FIELD_STALE) son **O(n tags)** cada poll / cada 5 s | Catálogo de miles de tags: CPU del sampler crece. No es leak; es coste lineal. |
| **LR-CTR-1** | Contadores `enqueued`, `shed_dropped`, `dropped_full`, `HTTP_REQUESTS_TOTAL` monotónicos | No comen RAM (int64). Dashboards “siempre suben”; usar **rates** (`SAF_INGEST` / `SAF_RATE`), no totales. |
| **LR-MEM-1** | MEM-PY-4: `AsyncStateMachineWorker.drop()` no quita de `_machines` | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) §3.2. Leak solo si se crean/destruyen SM en caliente mil veces. |
| **LR-CFG-1** | `ingest_heartbeat_s` y `backup_size_bytes` definidos y **no usados** | Expectativa ops falsa. |
| **LR-DEP-1** | Bind mounts `./temp/db` sin cuota Docker | El techo real es el disco del host + `max_disk_bytes`. |
| **LR-IDX-1** | UNIQUE `idempotency_key` vive mientras la fila viva (PENDING+SENT+DL) | SENT se va a 1 h; DL no. Catch-up de 190k SENT es transitorio. |

### 4.3 Ya no son el problema (cerrados o contenidos)

| Tema | Estado |
|---|---|
| `COUNT(*)` por tag en journal gordo | **Cerrado en checkout** — O(1) cache |
| Health hub haciendo COUNT sqlite | **Cerrado** (sesión P0) |
| FIFO / DLQ escape / shed TAG-only | **Cerrado** |
| L1 logs y json-file Docker | **Acotados** |
| Ring, shed, cap pending, max disk | **Acotados** |
| `pending_orphans` catálogo | TTL 5 min + 5 retries |
| HMI trends | colas por tag acotadas ([AUDIT_HMI.md](./AUDIT_HMI.md)) |

---

## 5. CPU, locks y “el día 1000 se siente lento”

No basta con no crecer en bytes. Hay que no degradar latencia.

| Camino | Complejidad vs tamaño | Riesgo a 1000 d |
|---|---|---|
| `set_value` → ring | O(1) | Bajo si no hay VACUUM en curso |
| Flusher INSERT | O(log N) B-tree | N = filas vivas (PENDING + SENT de la última hora + DL), no el histórico PG |
| `fetch_pending LIMIT` | O(lote) con índice `(status,id)` | OK |
| `oldest_pending_age_s` | `ORDER BY id LIMIT 1` | OK |
| Catalog full scan | cada 5 min, O(tablas × filas catálogo) | Catálogo de proceso es casi estático |
| Sampler PERF | O(tags) / 5 s | Sube si el catálogo sube, no con el tiempo |
| VACUUM idle | O(tamaño fichero) bajo lock | Evento raro; hay que instrumentar duración (`SAF journal compact done elapsed_s`) |

**Resiliencia de lock:** un solo `RLock` une enqueue, flusher, replicator y compact. Correcto para un writer SQLite. Incorrecto si VACUUM se dispara en catch-up (el código **lo evita**: `compact_max_pending=256`, y en catch-up profundo no compacta).

**Crash:** ring RAM se pierde (contrato T-01). WAL + `synchronous=FULL` recupera PENDING. Hidratar `_pending_durable` al abrir es O(pending) **una vez**, no por tag.

---

## 6. Resiliencia (outage, no solo “cabe en disco”)

| Escenario | Día 1 | Día 1000 |
|---|---|---|
| PG caído 1 h | PENDING crece; shed a 50k tags; eventos siguen | Igual. Disco journal sube. Tras recuperar: catch-up + TTL SENT 1 h + (nuevo) compact. |
| PG caído muchos días | PENDING → 5e6 o 10 GiB | Backpressure / disk-full. **No** borra PENDING. Operador: retry / reset confirmado. |
| Poison row | 5 intentos → DLQ | Sin GC, DLQ es el único crecimiento “con PG sano”. |
| Catálogo PG a ratos | Backoff 30→900 s; sqlite local | `catalog.db` puede hincharse (LR-CAT-1). |
| Restart gunicorn | Relee journal; COUNT hidrata | Arranque con 10 GiB PENDING puede tardar segundos (aceptable). |
| Hub gevent freeze | Recycle opcional `AUTOMATION_HUB_LAG_RECYCLE` | No es leak; es watchdog. |

---

## 7. Despliegue iDetectFugas (contexto planta)

No es código PyAutomation, pero gobierna el día 1000 del edge:

| Recurso | Tope | Comentario |
|---|---|---|
| `./temp/db` | Disco host | Journal + catalog.db + backups |
| `./temp/logs` | Rotación app ~40 MiB | Volumen persiste |
| `./temp/models` | Tamaño de artefactos ML | Estático salvo redeploy |
| json-file | ~70 MiB | OK |
| Healthcheck / `GUNICORN_TIMEOUT=120` | No relajar | Fuera de alcance de esta auditoría |

Compose genérico de PyAutomation documenta **256M RAM** y **tmpfs /tmp 500k** en algunos YAML: demasiado justos para soak real. El compose de iDetectFugas planta es el que manda.

---

## 8. Estrategia de continuidad (sin implementar aquí)

Orden industrial, no “vacuum cada tag”:

1. **Hot path O(1)** — hecho en checkout (pending cache, disk stat cache).
2. **Reclaim idle** — hecho en checkout (TRUNCATE + VACUUM condicionado). Desplegar.
3. **DLQ con TTL o cap** — único leak de filas con réplica sana (LR-DLQ-1).
4. **Retención PG** — partición/archive de `TagValue` (LR-PG-1). Esto es DBA, no el edge.
5. **Compact `catalog.db`** en idle, nunca en sync catch-up (LR-CAT-1).
6. **Poda `db/backups`** si hay historiador SQLite (LR-BKP-1).
7. **Soak certificado:** 24 h mínimo; 7 d deseable; día-1000 se **infiere** con las invariantes de §1 + ausencia de DLQ/PG sin tope, no se espera un ensayo de 1000 d.

**No hacer:** VACUUM en enqueue; COUNT por muestra; borrar PENDING automáticamente; relajar healthcheck/timeout; `pg_dump`/backup SQLite en el hilo de drain.

---

## 9. Criterios de aceptación (CA-LR)

| ID | Criterio | Estado |
|---|---|---|
| **CA-LR-01** | Enqueue de tags no ejecuta `COUNT(*)` | PASS en tests checkout |
| **CA-LR-02** | `reclaim_idle` compacta freelist y trunca WAL con cola quieta | PASS tests; **pendiente planta** |
| **CA-LR-03** | VACUUM no corre en catch-up (`compact_max_pending`) | PASS tests |
| **CA-LR-04** | Tras outage + 1 h + compact, `SAF_DISK_BYTES` vuelve a orden de MiB de flujo vivo | Pendiente deploy + observación N1 |
| **CA-LR-05** | `DEAD_LETTER` acotado por TTL o procedimiento ops documentado | **Pendiente** |
| **CA-LR-06** | Política de retención TagValue/Events en PG documentada en planta | **Pendiente DBA** |
| **CA-LR-07** | Soak 24 h: RSS ±15 %, cola plana, compact `elapsed_s` acotado | **Pendiente planta** |

---

## 10. Archivos clave

| Pieza | Ruta |
|---|---|
| Contador O(1) + reclaim | `automation/persistence/journal.py` |
| Config techos / compact | `automation/persistence/config.py` |
| Shed / gateway | `automation/persistence/orchestrator.py` |
| Idle compact caller | `automation/workers/replication.py` |
| GC en drain | `automation/persistence/replicator.py` |
| Sampler O(n tags) | `automation/workers/metrics_sampler.py` |
| Backup SQLite historian | `automation/workers/logger.py` `sqlite_db_backup` |
| Catálogo local | `automation/catalog/replicator.py`, `local_db.py` |

---

## 11. Veredicto

La aplicación **puede** ser tan ligera el día 1000 como el día 1 **en el proceso** (RAM, CPU del hot path, colas), porque esos recursos están techos y el COUNT del journal ya no escala con el fichero.

**No** será igual de ligera **en disco** hasta:

- desplegar `reclaim_idle` (WAL + VACUUM),
- acotar DLQ,
- retener/archivar el historiador PG.

Eso es el estándar de planta (historiador crece; el edge no). El hueco que vimos en N1 (cola vacía, disco alto) es exactamente el eslabón que el compact idle cierra, **con retardo de ~1 h**, a propósito.
