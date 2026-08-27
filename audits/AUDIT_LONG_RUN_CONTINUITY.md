# AUDIT_LONG_RUN_CONTINUITY — Continuidad día 1 vs día 1000

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + despliegue planta iDetectFugas |
| **Alcance** | Degradación a 1 / 10 / 100 / 1000 días: disco, RAM, CPU, locks, colas, historiador, catálogo, logs. Contraste código vs operación 24/7. Retención PG = DBA (fuera del edge). |
| **Fecha baseline** | 2026-08-27 (hallazgo N1 disco ≠ cola) |
| **Hardening código** | 2026-08-27 — SPEC_LONG_RUN_SOFTWARE_HARDENING (R1–R5) en checkout |
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](./AUDIT_NODE_PERFORMANCE_DASHBOARD.md) |
| **Evidencia planta** | N1 `intelcon2` / 192.168.1.80 · `journal.db` 331 MiB + WAL 50 MiB · PENDING=45 · SENT=190 712 · freelist 217 MiB · `auto_vacuum=0` (imagen `3.0.0` **sin** hardening) |
| **Veredicto** | Edge local (proceso + disco SAF/catálogo/DLQ) **A− en código**. Hot path O(1) + reclaim unificado + DLQ acotada + alerta disco + fuga SM cerrada. Historiador PG **B−** (retención = DBA). Certificado día-1000 **pendiente deploy + soak 24 h**. |
| **Clasificación** | Auditoría de continuidad operacional · degradación · grado planta 24/7 |

---

## 0. Pregunta fundamental

**¿El nodo del día 1000 es tan ligero y predecible como el del día 1, con catálogo fijo y red recuperable?**

**Respuesta (post-hardening en checkout):** **sí para el edge** — RAM, CPU del hot path, journal, `catalog.db` y `DEAD_LETTER` tienen techo duro o reclamación automática. El historiador PostgreSQL sigue creciendo de forma lineal; eso es política DBA, no del proceso del edge.

```
Día 1     proceso ligero + journal pequeño + PG vacío
Día 10    mismo RSS; tras catch-up + ~1 h, reclaim_idle compacta journal/catalog
Día 100   mismo RSS; DLQ ≤ 10k / ≤ 7 d; PG crece (DBA)
Día 1000  mismo RSS si catálogo fijo; disco edge autoregenerativo; PG retenido por planta
```

---

## 1. Horizonte temporal (qué debe pasar)

| Horizonte | Régimen | Lo que debe permanecer plano | Lo que puede crecer (y cómo se corta) |
|---|---|---|---|
| **Día 1** | Arranque, catálogo caliente | RSS worker, `set_value` p99, `SAF_QUEUE_DEPTH` ≈ flujo vivo | Journal WAL transitorio |
| **Día 10** | Outage PG de horas + catch-up | Tras drenar: PENDING ≈ decenas | SENT TTL 1 h → freelist → VACUUM idle; WAL TRUNCATE |
| **Día 100** | Operación continua | Mismas métricas de proceso; `TAG_OBSERVER_COUNT` estable | Historiador PG ~ lineal (DBA); DLQ podada |
| **Día 1000** | Años de planta | Hot path O(1); ring ≤ 100k; logs L1 rotados | Sin retención DBA, PG es el único unbounded “oficial” |

Objetivo de aceptación (alineado con [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md)):

- RSS gunicorn **±15 %** vs baseline a catálogo fijo.
- `SAF_QUEUE_DEPTH` sin crecimiento monotónico con PG sano.
- `SAF_DISK_BYTES` **después de compactar** en el orden del flujo vivo (MiB, no el pico de la outage).
- `HOST_DISK_CRITICAL` falso en régimen sano; alerta al cruzar 85 %.
- `DAS.monitored_items` / `TAG_OBSERVER_COUNT` / `len(_machines)` estables.
- p99 `set_value` no degrada con journal gordo (O(1) `pending_count`).

---

## 2. Qué está acotado (día 1 ≈ día 1000 en el edge)

| Recurso | Techo | Dónde |
|---|---|---|
| Ring RAM tags | 100 000 | `SafConfig.ring_maxsize` |
| PENDING durable | 5 000 000 → backpressure | `max_pending_rows` |
| Disco journal (hard) | 10 GiB | `max_disk_bytes`; evict SENT; si no basta → `JournalDiskFullError` |
| Shed analog history | high 50k / low 10k | tags pausados; eventos/alarmas siguen |
| SENT | GC TTL **1 h**, lotes 5 000 | `gc_sent` |
| **DEAD_LETTER** | **TTL 7 d + cap 10 000** | `prune_dead_letters` en `reclaim_idle` |
| Journal freelist / WAL | TRUNCATE + VACUUM idle | `reclaim_idle` (pending ≤ 256, freelist ≥ 64 MiB, ≤ 1/h) |
| **catalog.db** | Mismo umbral, **lock propio** | `compact_catalog_idle` fuera del `RLock` del journal |
| CycleSampleCache | TTL 2 s | `cycle_dedupe.py` |
| Buffer OPC / SM | `deque(maxlen=…)` | `buffer.py`, DAS, core |
| Async SM registry | `drop()` remueve `_machines` | `state_machine.py` |
| Trend PERF | ~68 puntos / 5 min | `metrics_sampler.py` |
| Cooldown audit | cap 256 | `audit_metrics.py` |
| L1 `app.log` | 10 MiB × 3 ≈ 40 MiB | `RotatingFileHandler` |
| Docker json-file | 10m × 7 ≈ 70 MiB | compose iDetectFugas |
| Disco host (alerta) | **85 %** → `HOST_DISK_CRITICAL` | sampler + evento con cooldown 1 h |
| Health `/health/saf` | O(1) | post-parche |
| Hot path pending / shed / cap | **O(1)** | `_pending_durable + len(_ring)` |

---

## 3. Hallazgo planta 2026-08-27 — disco ≠ cola (evidencia baseline)

N1 Linea1, cola ya drenada (imagen `idetectfugas/app:3.0.0` **sin** el hardening):

| Magnitud | Valor | Lectura |
|---|---|---|
| PENDING / REPLICATING | 45 | Flujo vivo. No hay lag de réplica. |
| SENT | 190 712 | Catch-up marcado SENT en la última hora. TTL 1 h aún no aplica. |
| `journal.db` | 331 MiB | Tamaño de fichero, no de filas vivas. |
| WAL | 50 MiB | No se truncaba en idle en esa imagen. |
| Freelist | 217 MiB | Huecos internos. `auto_vacuum=0`. |
| Gauge HMI | `SAF_DISK_BYTES` = db+wal+shm | Correcto; **no** es “cola”. |

Ese síntoma motivó el compact idle. Con el código actual del checkout, tras deploy:

```
t=0      Cola drenada → PENDING ≈ flujo vivo
t≈0+     TRUNCATE WAL (journal + catalog) → baja WAL
t≈1 h    GC SENT → freelist grande
t≥1 h    VACUUM idle (ambos .db) → SO recupera el pico
continuo prune_dead_letters (TTL 7 d / cap 10k)
```

VACUUM del journal sigue bajo el `RLock` (trade-off conocido: segundos en idle, ≤ 1/h). El VACUUM de `catalog.db` **no** comparte ese lock.

---

## 4. SPEC_LONG_RUN_SOFTWARE_HARDENING — evidencia implementada

Orden ejecutado: R3 → R5 → R2 → R1 → R4 (+ docs sampler).

### 4.1 Cierres R1–R5

| ID | Requerimiento | Evidencia en código | Tests |
|---|---|---|---|
| **R1 / LR-DLQ-1** | DLQ acotada | `JournalWriter.prune_dead_letters()`: DELETE por `created_at` (TTL default 7 d) y por exceso sobre `dead_letter_max_rows` (default 10 000). Llamado desde `reclaim_idle()`. Config: `saf_dead_letter_ttl_s`, `saf_dead_letter_max_rows`. | `test_prune_dead_letters_caps_max_rows`, `test_prune_dead_letters_ttl` |
| **R2 / LR-CAT-1** (+ compact journal) | Compactación unificada | Tras compactar journal, si `pending ≤ compact_max_pending`, `compact_catalog_idle()` en `catalog/local_db.py` con `_compact_lock` propio: checkpoint TRUNCATE + VACUUM condicional. | `test_compact_catalog_idle_vacuums_freelist`, `test_reclaim_idle_*` |
| **R3 / LR-MEM-1** | Fuga SM | `AsyncStateMachineWorker.drop()` hace `_machines.remove(machine)` y `sched_to_drop.stop()`. | `test_drop_removes_from_registry` |
| **R4 / LR-DEP-1** | Alarma disco host | Sampler mide volumen de datos (`journal_path` dir o `AUTOMATION_DATA_DIR`). Snapshot: `HOST_DISK_USED_PERCENT`, `HOST_DISK_CRITICAL` (> `host_disk_critical_percent` default 85). Flanco → `persist_system_event("Disk usage critical")` cooldown 3600 s. HMI: tile rojo si critical. | `test_host_disk_critical_*`, `test_psutil_fields_when_available` |
| **R5 / LR-CFG-1** | Config huérfana | Eliminados `ingest_heartbeat_s` y `backup_size_bytes` de `SafConfig` / `from_app_config`. `grep` en `automation/` vacío. | CA-LR-06 por grep |

### 4.2 Defaults nuevos (`SafConfig`)

| Parámetro | Default | Override |
|---|---|---|
| `dead_letter_max_rows` | 10 000 | `saf_dead_letter_max_rows` |
| `dead_letter_ttl_s` | 604 800 (7 d) | `saf_dead_letter_ttl_s` |
| `compact_min_freelist_bytes` | 64 MiB | `saf_compact_min_freelist_bytes` |
| `compact_min_interval_s` | 3600 | `saf_compact_min_interval_s` |
| `compact_max_pending` | 256 | `saf_compact_max_pending` |
| `host_disk_critical_percent` | 85.0 | `saf_host_disk_critical_percent` |

### 4.3 Docs / operabilidad (LR-SYS-1 mitigado en ops)

- [docs/runbook.md](../docs/runbook.md): poll de métricas → `/health/node` O(1); no poll frecuente de `/health/system`.
- [docs/node-performance-runbook.md](../docs/node-performance-runbook.md): mismo aviso + `HOST_DISK_CRITICAL`.
- HMI `performance.pollHint` (es/en): tooltip en `/performance`.

El coste O(n tags) de `/health/system` y `_sample_field` **permanece**; la mitigación es no usarlo para dashboard.

---

## 5. Matriz de riesgos (día 1000) — estado post-hardening

### 5.1 Cerrados en checkout

| ID | Riesgo | Estado |
|---|---|---|
| **LR-DLQ-1** | DEAD_LETTER sin tope | **Cerrado** — TTL 7 d + cap 10k |
| **LR-CAT-1** | catalog.db sin compact | **Cerrado** — `compact_catalog_idle` |
| **LR-MEM-1** | `drop()` no limpia `_machines` | **Cerrado** |
| **LR-CFG-1** | Config huérfana | **Cerrado** — eliminada |
| **LR-DEP-1** | Disco host sin alerta | **Cerrado** — `HOST_DISK_CRITICAL` + evento |
| O(1) pending / reclaim journal | COUNT por tag; fichero que no encoge | **Cerrado** (sesión previa + R2) |

### 5.2 Residuales aceptados / fuera de alcance edge

| ID | Riesgo | Notas |
|---|---|---|
| **LR-PG-1** | TagValue/Events/Logs en PG sin TTL | **Fuera de alcance** — DBA / particiones. LOG-H5. |
| **LR-VAC-1** | VACUUM journal bajo `RLock` | Mitigado (idle, ≤ 1/h, pending ≤ 256). Medir `elapsed_s` en soak. Catalog compact **fuera** del lock. |
| **LR-BKP-1** | `sqlite_db_backup` sin poda | Historiador SQLite legado; planta usa PG. Spec: backups historiador fuera de alcance. |
| **LR-SYS-1** | `/health/system` O(n) | Documentado; dashboard usa `/health/node`. |
| **LR-CTR-1** | Contadores monotónicos | Usar rates, no totales. |
| **LR-IDX-1** | Índice UNIQUE mientras fila viva | SENT 1 h; DL ahora podada. |

### 5.3 Ya no son el problema

| Tema | Estado |
|---|---|
| `COUNT(*)` por tag | Cerrado |
| Health hub COUNT sqlite | Cerrado (P0) |
| FIFO / shed TAG-only / DLQ escape | Cerrado |
| L1 logs / json-file | Acotados |
| Ring / shed / cap / max disk | Acotados |
| `pending_orphans` catálogo | TTL 5 min + 5 retries |

---

## 6. CPU, locks y latencia

| Camino | Complejidad | Riesgo a 1000 d |
|---|---|---|
| `set_value` → ring | O(1) | Bajo si no hay VACUUM journal en curso |
| Flusher INSERT | O(log N) | N = filas vivas (PENDING + SENT &lt; 1 h + DL acotada) |
| `fetch_pending LIMIT` | O(lote) | OK |
| Sampler PERF / FIELD_STALE | O(tags) / 5 s | Crece con catálogo, no con el calendario |
| VACUUM journal | O(fichero), bajo lock | Raro; log `elapsed_s` |
| VACUUM catalog | O(fichero), lock propio | No bloquea enqueue SAF |
| `prune_dead_letters` | O(borrados), idle | Capado a ≥ 60 s entre podas |

**Invariante:** ninguna lógica R1–R5 corre dentro de `Tag.set_value`.

---

## 7. Resiliencia (outage)

| Escenario | Día 1 | Día 1000 (código nuevo) |
|---|---|---|
| PG caído 1 h | PENDING crece; shed tags | Tras recuperar: catch-up + SENT TTL + reclaim |
| PG caído muchos días | Cap 5e6 / 10 GiB | Backpressure; PENDING sagrado; ops retry/reset |
| Poison row | → DLQ | DLQ se poda sola (TTL/cap) |
| Catálogo a ratos | Backoff 30→900 s | `catalog.db` compacta en idle |
| Disco host ≥ 85 % | — | `HOST_DISK_CRITICAL` + Event |
| Restart gunicorn | Hidrata contadores | Arranque con journal gordo: COUNT una vez |

---

## 8. Despliegue iDetectFugas

| Recurso | Tope | Comentario |
|---|---|---|
| `./temp/db` | Disco host + alerta 85 % | Journal + catalog; reclaim tras deploy |
| `./temp/logs` | ~40 MiB app | Volumen persiste |
| `./temp/models` | Artefactos ML | Estático salvo redeploy |
| json-file | ~70 MiB | OK |
| Healthcheck / `GUNICORN_TIMEOUT=120` | No relajar | Fuera de alcance |

**Planta hoy:** imagen `3.0.0` **no** incluye R1–R5 ni O(1) pending hasta reinstalar wheel PyAutomation (+ rebuild HMI para tile/tooltip).

---

## 9. Estrategia de continuidad (estado)

| Paso | Estado |
|---|---|
| 1. Hot path O(1) | **Hecho** en checkout |
| 2. Reclaim idle journal | **Hecho** |
| 3. Compact catalog | **Hecho** (R2) |
| 4. DLQ TTL/cap | **Hecho** (R1) |
| 5. Alerta disco host | **Hecho** (R4) |
| 6. Fuga SM + config limpia | **Hecho** (R3, R5) |
| 7. Retención PG | **Pendiente DBA** (LR-PG-1) |
| 8. Deploy wheel + soak 24 h | **Pendiente planta** |

**No hacer:** VACUUM en enqueue; COUNT por muestra; borrar PENDING automático; relajar healthcheck/timeout.

---

## 10. Criterios de aceptación (CA-LR)

| ID | Criterio | Estado |
|---|---|---|
| **CA-LR-01** (spec: DLQ ≤ 10k / ≤ 7 d) | `prune_dead_letters` | **PASS** unit (`test_long_run_hardening`) |
| **CA-LR-02** | `reclaim_idle` compacta journal **y** catalog con PENDING ≤ 256 | **PASS** unit; **pendiente planta** |
| **CA-LR-03** | `drop()` decrementa `_machines` | **PASS** `test_drop_removes_from_registry` |
| **CA-LR-04** | `/health/node` expone `HOST_DISK_*` + CRITICAL | **PASS** unit (psutil skip si no instalado) |
| **CA-LR-05** | Evento Disk usage critical con cooldown | **PASS** unit flanco |
| **CA-LR-06** | Sin `ingest_heartbeat_s` / `backup_size_bytes` en `automation/` | **PASS** grep |
| **CA-LR-07** | Hot path no ejecuta R1–R5 | **PASS** por diseño (idle workers); soak/py-spy planta pendiente |
| **CA-LR-08** (legado) | Enqueue sin `COUNT(*)` | **PASS** tests SAF |
| **CA-LR-09** | Tras outage + compact, `SAF_DISK_BYTES` orden MiB | **Pendiente deploy N1** |
| **CA-LR-10** | Retención TagValue/Events PG | **Pendiente DBA** |
| **CA-LR-11** | Soak 24 h RSS ±15 %, cola plana | **Pendiente planta** |

Numeración CA-LR-01…07 alineada a SPEC_LONG_RUN_SOFTWARE_HARDENING; CA-LR-08…11 conservan criterios del baseline O(1)/disco/PG/soak.

---

## 11. Archivos clave

| Pieza | Ruta |
|---|---|
| Contador O(1), prune DLQ, reclaim | `automation/persistence/journal.py` |
| Config techos | `automation/persistence/config.py` |
| Compact catalog | `automation/catalog/local_db.py` `compact_catalog_idle` |
| Idle caller | `automation/workers/replication.py` |
| Disco host / CRITICAL | `automation/workers/metrics_sampler.py` |
| drop SM | `automation/workers/state_machine.py` |
| Tests hardening | `automation/tests/test_long_run_hardening.py` |
| HMI tile + pollHint | `hmi/src/pages/Performance.tsx`, locales |

---

## 12. Veredicto

Con R1–R5 en el checkout, el **edge** cumple la filosofía nuclear-industrial para 1000 días: RAM acotada, disco local autoregenerativo (journal + catalog + DLQ), CPU del hot path sin estas rutinas, configuración sin falsos techos.

Queda:

1. **Desplegar** wheel (+ HMI) en N1/N2.
2. **Observar** CA-LR-09 tras una outage o compact natural.
3. **Soak 24 h** (CA-LR-11).
4. **Retención PG** (CA-LR-10) — no es trabajo del edge.

El hueco visto en planta (cola vacía, disco alto) queda explicado y cerrado en código; la imagen en producción aún no lo refleja.
