# Auditoría de durabilidad de disco y eficiencia de escritura

| Campo | Valor |
|---|---|
| **Productos** | PyAutomationIO (`automation/`) + iDetectFugas (`gitlab/intelcon/idetectfugas`) |
| **Alcance** | Store-and-Forward (SAF), SQLite local (journal + catalog), hot path CVT, capa OS/hardware, pruebas |
| **Metodología** | Caja de cristal — código fuente, arquitectura y documentación existente |
| **Fecha** | 2026-08-28 |
| **Fuentes cruzadas** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_LONG_RUN_CONTINUITY.md](./AUDIT_LONG_RUN_CONTINUITY.md), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md); iDetectFugas `06-AUDIT_PERFORMANCE.md`, `07-AUDIT_CVT.md`, `08-AUDIT_PRODUCTION_IMAGE.md`, `09-AUDIT_CORE_SAMPLING.md` |
| **Veredicto global** | **A− en código** (SAF + SQLite journal + hot path app). **B** en despliegue físico (OS/hardware/SMART no codificados). **No cumple aún el checklist WD completo** — gaps en capa borde y prueba de disco lleno |

---

## 1. Resumen ejecutivo

PyAutomationIO implementa un **Store-and-Forward de clase industrial** en el journal SQLite WAL: el camino caliente de adquisición (`Tag.set_value` → CVT → `TagObserver` → `PersistenceOrchestrator.enqueue`) **no espera la red ni hace fsync síncrono por muestra**; las tags van a un **ring RAM acotado** drenado por un hilo `SafJournalFlusher` en lotes de hasta 256 filas cada ~10 ms. Alarmas, eventos y logs críticos hacen **COMMIT local síncrono** antes de devolver control — diseño consciente de durabilidad vs. latencia.

La replicación remota (`RemoteReplicator`) opera en **lotes de hasta 1 000 filas/s**, con **circuit breaker**, **rate limiter** y **marcado SENT solo tras ACK** del historiador. El journal tiene **topes operativos**: ring 100 000 muestras, 5 000 000 filas PENDING, 10 GiB en disco (`max_disk_bytes`) con evicción de SENT antes de `JournalDiskFullError`.

iDetectFugas **hereda el contrato SAF** y aplica **Afinación Fina** en la capa de negocio: umbrales publicados como máximo cada **10 s** (o al cambiar), `leak` **una vez por ciclo**, `Leaks.put` solo si cambia el payload, alarmas SocketIO solo en **flanco de estado**.

**Fortalezas:** arquitectura SAF A+ (ver [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md)), deduplicación por ciclo (`CycleSampleCache`), backpressure explícita, monitoreo de cola SAF y uso de disco host vía `/performance`, volúmenes `./data/db` en borde.

**Debilidades para estándar 24/7/365 “clase mundial”:** (1) **sin runbook codificado** de filesystem (`noatime`), planificador I/O ni SSD industrial; (2) **sin SMART/temperatura SSD** — solo `% uso` vía psutil; (3) **`JournalDiskFullError` sin test unitario dedicado**; (4) **`catalog.db` con `synchronous=NORMAL`** (aceptable para catálogo, no para durabilidad crítica); (5) **journal sin `cache_size`/`mmap_size` explícitos**; (6) residual bayesiano: umbral puede escribirse **2×** en tick de cambio (`_apply` + `_publish_threshold_tags`).

---

## 2. Hallazgos detallados — lista de verificación

### 2.1 Arquitectura de persistencia (Store-and-Forward)

| # | Control | Estado | Evidencia |
|---|---|---|---|
| 1 | **Hot path sin E/S síncrona de disco** | ✅ **Cumple** | `TagObserver.update()` llama `get_persistence_gateway().enqueue(record)` — no sqlite3 en el hilo de la SM. Tags van al ring; flush en hilo `SafJournalFlusher` (`journal.py` `_flush_loop`, intervalo `tag_flush_interval_s=0.010`). Críticos (alarmas/eventos/logs) sí hacen `_insert_commit_locked` — diseño documentado en SAF. |
| 2 | **Buffer en memoria RAM** | ✅ **Cumple** | `JournalWriter._ring: deque` con `ring_maxsize` default **100 000** (`config.py`). `PersistenceOrchestrator` añade `CycleSampleCache` en RAM antes del journal. |
| 3 | **Journal en disco (WAL) como fuente de verdad local** | ✅ **Cumple** | Ruta `./db/saf/<node_id>/journal.db`; `PRAGMA journal_mode=WAL`, `synchronous=FULL` (`journal.py` `_ensure_open_locked`). Tabla `persistence_journal` estados PENDING → REPLICATING → SENT. |
| 4 | **Escritura por lotes (replicador)** | ✅ **Cumple** | Drain ring: `tag_batch_size=256`. Remoto: `replicate_batch_size=1_000`, `replicate_rate_per_s=10_000` (`config.py`). `RemoteReplicator.replicate_once()` agrupa por dominio y llama `write_batch_outcomes`. |
| 5 | **Exact-once y ACK** | ✅ **Cumple** | `mark_sent(sent_ids)` solo tras `outcomes` OK (`replicator.py` L183–187). Fallo → `mark_pending` + reintento. Idempotencia remota: `IdempotentBatchInserter`, UNIQUE journal + `sample_uuid`. Tests: `test_ack_marks_sent_and_gc`, `test_c02_failed_replicate_keeps_pending`, `test_t01_kill9_replay_exact_once`. |
| 6 | **Circuit breaker y rate limiting** | ✅ **Cumple** | Clases `CircuitBreaker` y `RateLimiter` en `replicator.py`; defaults `circuit_fail_threshold=5`, `circuit_open_s=5.0`. Test `test_circuit_opens`. Shed de tags analog si `pending >= shed_high` (50 000) en `orchestrator.py`. |
| 7 | **Capacidad del journal (ring / tope disco)** | ⚠️ **Parcial** | **Ring RAM** acotado + `JournalBackpressureError`. **Disco:** `max_disk_bytes=10 GiB`, `max_pending_rows=5_000_000`; evicción SENT más antiguos antes de `JournalDiskFullError` (`_guard_disk_locked`). **No es un ring buffer clásico** que descarte PENDING antiguos — PENDING se conserva hasta ACK o dead-letter (5 intentos). Comportamiento correcto para integridad, pero bajo outage prolongado el disco puede llenarse si SENT no alcanza a liberar. |

**Diagrama de flujo (estado vigente):**

```
Hot path (CVT / SM @ ~1 Hz)
        │  TagObserver → PersistenceOrchestrator.enqueue()
        │  CycleSampleCache (dedupe mismo tag/valor/ciclo)
        ▼
┌─────────────────────────────────────────┐
│  Ring RAM (_ring, ≤ saf_ring_maxsize)   │
│  SafJournalFlusher @ 10 ms, batch 256   │
│  SQLite WAL journal.db synchronous=FULL │
│  persistence_journal (PENDING…)         │
└───────────────┬─────────────────────────┘
                │ LoggerWorker / RemoteReplicator
                │ batch 1000 + rate limit + circuit breaker
                ▼
        PostgreSQL ──ACK──► status=SENT ──GC──►
```

---

### 2.2 Almacenamiento en disco (SQLite)

| # | PRAGMA / control | Journal SAF | catalog.db | Estado |
|---|---|---|---|---|
| 1 | `journal_mode=WAL` | ✅ `journal.py` L863 | ✅ `local_db.py` L47 | **Cumple** |
| 2 | `synchronous` | ✅ **FULL** (2) | ⚠️ **NORMAL** (1) | Journal: durabilidad ante power-loss. Catalog: espejo de config/usuarios — NORMAL es aceptable; **documentar** que no es Plan A de muestras. |
| 3 | `temp_store=MEMORY` | ✅ L865 | ❌ No configurado | **Gap menor** en catalog |
| 4 | `cache_size` | ❌ Default SQLite | ✅ `-8000` (~8 MB) | **Gap menor** en journal — conviene fijar p. ej. `-64000` (64 MB) en borde |
| 5 | `mmap_size` | ❌ No usado | ❌ No usado | **Gap** — oportunidad de lectura; bajo impacto en escritura |
| 6 | `auto_vacuum` | ✅ INCREMENTAL + `reclaim_idle()` / WAL checkpoint | ✅ INCREMENTAL en `compact_catalog_idle()` | **Cumple** |

**Nota:** El historiador remoto es PostgreSQL en planta; el SQLite “de aplicación” legacy (`core.py` L3756) usa WAL + `synchronous=1` + `cache_size` 10 MB — **no es el camino SAF** en despliegue certificado.

---

### 2.3 Frecuencia de escritura — hot path iDetectFugas

| # | Control | Estado | Evidencia |
|---|---|---|---|
| 1 | **Umbrales (`_publish_threshold_tags`)** | ✅ **Cumple** | `_THRESHOLD_PUBLISH_INTERVAL_S = 10.0` (`app/core.py` L48, L333–369). Publica si cambió **o** heartbeat 10 s. Residual: mixin bayesiano puede duplicar en tick de cambio (ver `07-AUDIT_CVT.md` §0.4). |
| 2 | **`leak` una vez por ciclo** | ✅ **Cumple** | Verificado en `07-AUDIT_CVT.md` §0 — hijos no duplican `set_value(leak)`; LDS escribe una vez sin `super().while_leaking()`. |
| 3 | **`Leaks.put` solo si payload cambió** | ✅ **Cumple** | `_leak_payload_changed()` fingerprint `(leak_report_id, size, location, flow, volume)` (`app/modules/lds/__init__.py` L521–533). |
| 4 | **Alarmas solo en cambio de estado** | ✅ **Cumple** | `_emit_active_alarm_if_changed()` — caché 5 s, emit SocketIO solo si `has_active` cambió (L535–551). Persistencia de alarmas vía SAF outbox en flanco de gestor, no periódica. |

**Dedupe adicional en framework:** `CycleSampleCache` (`cycle_dedupe.py`) elimina re-escrituras silenciosas del mismo tag/valor/timestamp dentro de ~2 s — complementa la lógica de app.

---

### 2.4 Capa de almacenamiento físico (OS / hardware)

| # | Control | Estado | Evidencia |
|---|---|---|---|
| 1 | **Opciones de montaje filesystem** | ❌ **No codificado** | `deploy/docker-compose.yml` monta `./data/db:/app/db` sin documentar `noatime`, `data=ordered`, etc. No hay Ansible/fstab en repos. |
| 2 | **Planificador I/O** | ❌ **No codificado** | Sin referencias a `mq-deadline`, `none`, `bfq` en deploy o docs. |
| 3 | **SSD industrial (TBW, wear leveling)** | ❌ **No codificado** | Imagen distroless + volumen genérico; **no hay BOM ni requisito TBW** en código ni `deploy/README.md`. |
| 4 | **Monitoreo temperatura / SMART** | ⚠️ **Parcial** | `MetricsSampler` expone `HOST_DISK_USED_PERCENT`, `HOST_DISK_FREE_GB`, `HOST_DISK_CRITICAL` (>85 % → evento sistema, cooldown 3600 s) — `workers/metrics_sampler.py`, `test_long_run_hardening.py`. **Sin SMART, sin temperatura SSD, sin wear %**. |

---

### 2.5 Pruebas automatizadas

| # | Control | Estado | Evidencia |
|---|---|---|---|
| 1 | **Chaos — BD remota caída** | ✅ **Cumple** | `test_c02_failed_replicate_keeps_pending`, `test_circuit_opens`, `test_catchup_drains_more_than_one_batch_per_period`, partial batch alarm tests. T-01 Apocalypse: SIGKILL + replay exact-once. |
| 2 | **Rendimiento de escritura journal** | ⚠️ **Parcial** | `test_flush_batch_does_not_stat_disk_per_insert` (O(1) stat disco). `TestT01Apocalypse` con `SAF_SOAK_*` env vars. Soak 24 h backend: **pendiente** en runbook (`AUDIT_PERFORMANCE.md` §4.3). |
| 3 | **Pruebas fsync / durabilidad** | ⚠️ **Parcial** | Journal usa `synchronous=FULL`; T-01 valida replay post-SIGKILL (muestras no commiteadas pueden perderse — documentado). `soak_producer.py` usa `os.fsync` en contador, **no** test dedicado de fsync del journal. |
| 4 | **Disco lleno → error controlado** | ❌ **Gap** | `JournalDiskFullError` implementado (`journal.py` `_guard_disk_locked`, L820–834). **No hay `test_*` que fuerce disco lleno** en `test_store_and_forward.py` (solo `max_disk_bytes` en config de otros tests). |

---

## 3. Criterios de éxito WD-01…WD-10

| ID | Criterio | Veredicto | Notas |
|---|---|---|---|
| **WD-01** | Hot path sin E/S síncrona | ✅ **PASS** | Tags → ring; flush async |
| **WD-02** | Buffer en memoria | ✅ **PASS** | `_ring` + `CycleSampleCache` |
| **WD-03** | Journal durable (`synchronous=FULL`) | ✅ **PASS** | WAL journal SAF |
| **WD-04** | Escritura por lotes | ✅ **PASS** | 256 local / 1000 remoto |
| **WD-05** | Exact-once + ACK | ✅ **PASS** | SENT post-ACK; idempotency keys |
| **WD-06** | Capacidad journal (ring buffer) | ⚠️ **CONDICIONAL** | Topes RAM/disco/filas sí; no ring que descarte PENDING |
| **WD-07** | Frecuencia escritura optimizada | ✅ **PASS** | App + cycle dedupe; residual bayesiano menor |
| **WD-08** | Pruebas de caos | ⚠️ **CONDICIONAL** | Red/BD sí; disco lleno no |
| **WD-09** | Hardware aprobado (SSD industrial) | ❌ **FAIL** | Sin especificación en repo |
| **WD-10** | Monitoreo activo disco + cola SAF | ⚠️ **CONDICIONAL** | Cola SAF + % disco sí; SMART/temp no |

**Puntuación:** 6 PASS · 3 CONDICIONAL · 1 FAIL → **no alcanza checklist “clase mundial” completo** sin cerrar capa borde y prueba WD-08/WD-06 explícita.

---

## 4. Gaps identificados (priorizados)

| Prioridad | ID | Gap | Impacto |
|---|---|---|---|
| **P0 — Alta** | G-DISK-01 | Sin runbook/BOM de **SSD industrial** (TBW, temperatura operativa, over-provisioning) | Vida útil del borde en 24/7/365 |
| **P0 — Alta** | G-DISK-02 | Sin **monitoreo SMART** / temperatura SSD — solo % uso volumen | Fallo inminente no detectado |
| **P1 — Alta** | G-DISK-03 | **`JournalDiskFullError` sin test automatizado** | Regresión silenciosa en outage largo |
| **P1 — Alta** | G-DISK-04 | **Filesystem / I/O scheduler** no documentados en deploy | Latencia y desgaste evitables |
| **P2 — Media** | G-DISK-05 | Journal SAF sin **`cache_size`/`mmap_size`** explícitos | Más lecturas/escrituras de las necesarias bajo carga |
| **P2 — Media** | G-DISK-06 | **`catalog.db` synchronous=NORMAL** sin nota operativa | Riesgo bajo (no es outbox de muestras) pero confusión en auditorías |
| **P2 — Media** | G-DISK-07 | Residual **doble escritura umbral bayesiano** en tick de cambio | ~2× writes en 3 tags en evento raro |
| **P3 — Baja** | G-DISK-08 | Soak **24 h con outage PG 4 h** pendiente de ejecución planta | Certificación operativa, no diseño |
| **P3 — Baja** | G-DISK-09 | **`temp_store=MEMORY`** ausente en catalog.db | E/S menor en operaciones admin |

---

## 5. Recomendaciones

### Alta prioridad

1. **G-DISK-01 — Especificación hardware borde**  
   Añadir en `docs/` o `deploy/README.md` una sección *Edge storage*: SSD industrial ≥ X TBW, rango térmico, capacidad mínima separando `/app/db` (SAF+catalog) de logs del SO. Ejemplo orientativo: 256 GB+ con ≥ 1 DWPD en volumen de journal.

2. **G-DISK-02 — Monitoreo SMART**  
   Integrar lectura periódica vía `smartctl` o agente node-exporter (atributos 177/231/233) → tags `HOST_SSD_WEAR_PERCENT`, `HOST_SSD_TEMP_C` en snapshot `/performance`; alarma `ALM.PERF.SSD` en umbral configurable.

3. **G-DISK-03 — Test disco lleno**  
   En `test_store_and_forward.py`: journal con `max_disk_bytes` mínimo, llenar con PENDING (sin SENT evictable), assert `JournalDiskFullError` + evento `SAF disk full` + backpressure.

4. **G-DISK-04 — Runbook montaje**  
   Documentar para planta Linux: ext4/xfs con `noatime`, `commit=30` (evaluar vs durabilidad), volumen dedicado para `./data/db`; I/O scheduler `mq-deadline` o `none` en NVMe; verificar en checklist de puesta en marcha.

### Media prioridad

5. **G-DISK-05 — PRAGMA journal**  
   En `_ensure_open_locked`: `PRAGMA cache_size=-64000` (64 MB); evaluar `mmap_size=268435456` en lecturas de catchup. Medir con `test_flush_batch_*` antes/después.

6. **G-DISK-06 — Clarificar roles SQLite**  
   Tabla en [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md): journal = FULL + Plan A; catalog = NORMAL + autonomía config.

7. **G-DISK-07 — Unificar umbral bayesiano**  
   En iDetectFugas: que `_sync_bayesian_detection_threshold` delegue en `_publish_threshold_tags` o marque “already published” para evitar doble `set_value` en el mismo tick.

### Baja prioridad

8. **G-DISK-08 — Ejecutar soak certificación**  
   Runbook `PERF_SOAK_SECONDS=86400` + outage PG 4 h; registrar en artefacto tipo `T01_SOAK_LAST_RUN.md`.

9. **G-DISK-09 — catalog pragmas**  
   Añadir `temp_store=MEMORY` en `open_catalog_db` si pruebas de compact no regresan.

---

## 6. Referencias de código

### PyAutomationIO — SAF journal

```863:867:github/PyAutomation/automation/persistence/journal.py
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute(f"PRAGMA wal_autocheckpoint={int(self.config.wal_autocheckpoint)}")
            self._conn.execute("PRAGMA foreign_keys=ON")
```

### PyAutomationIO — Topes operativos

```31:38:github/PyAutomation/automation/persistence/config.py
    journal_path: str = field(default_factory=_default_journal_path)
    max_disk_bytes: int = 10 * 1024 * 1024 * 1024
    max_pending_rows: int = 5_000_000
    ring_maxsize: int = 100_000
    tag_batch_size: int = 256
    tag_flush_interval_s: float = 0.010
    replicate_batch_size: int = 1_000
    replicate_rate_per_s: int = 10_000
```

### PyAutomationIO — ACK post-remoto

```183:187:github/PyAutomation/automation/persistence/replicator.py
                sent_ids = [jid for jid, ok in zip(ids, outcomes) if ok]
                failed_batch_ids = [jid for jid, ok in zip(ids, outcomes) if not ok]
                if sent_ids:
                    self.journal.mark_sent(sent_ids)
                    replicated += len(sent_ids)
```

### PyAutomationIO — Hot path CVT → SAF

```988:1003:github/PyAutomation/automation/tags/tag.py
            from ..persistence import get_persistence_gateway
            from ..persistence.records import PersistableRecord
            ...
            get_persistence_gateway().enqueue(record)
```

### iDetectFugas — Umbrales 10 s

```48:48:gitlab/intelcon/idetectfugas/app/core.py
_THRESHOLD_PUBLISH_INTERVAL_S = 10.0
```

### iDetectFugas — Leaks.put dedupe

```521:533:gitlab/intelcon/idetectfugas/app/modules/lds/__init__.py
    def _leak_payload_changed(self, payload: Dict[str, Any]) -> bool:
        """True si el payload de Leaks.put cambió respecto al último persistido."""
        fingerprint = (
            self.leak_report_id,
            payload.get("size"),
            payload.get("location"),
            payload.get("flow"),
            payload.get("volume"),
        )
        if self._last_leak_payload == fingerprint:
            return False
        self._last_leak_payload = fingerprint
        return True
```

---

## 7. Conclusión

**En software, iDetectFugas sobre PyAutomationIO está muy por encima del baseline “logger directo a PostgreSQL”** y cumple los principios de un sistema de adquisición 24/7: hot path desacoplado, journal WAL durable, replicación por lotes con exact-once, backpressure y deduplicación en app y framework.

**Para declarar “clase mundial” en durabilidad de disco** faltan piezas que no viven solo en Python: **hardware industrial acreditado**, **SMART/temperatura**, **runbook de filesystem/I/O**, y **prueba automatizada de disco lleno**. Con esos cuatro cierres — más la ejecución del soak 24 h ya definido — el sistema pasaría de **A− (código) / B (borde)** a **A+ operativo**.

**Próximo paso recomendado (orden):** (1) test `JournalDiskFullError`; (2) sección deploy SSD + montaje; (3) métricas SMART en `MetricsSampler`; (4) soak planta con outage PG documentado.
