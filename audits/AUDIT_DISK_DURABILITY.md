# Auditoría de durabilidad de disco y eficiencia de escritura

| Campo | Valor |
|---|---|
| **Productos** | PyAutomationIO (`automation/`) + iDetectFugas (`gitlab/intelcon/idetectfugas`) |
| **Alcance** | Store-and-Forward, SQLite (journal + catalog), hot path CVT, OS/hardware, SMART, pruebas |
| **Metodología** | Caja de cristal + implementación de gaps G-DISK-01…09 |
| **Fecha baseline** | 2026-08-28 (auditoría A− / B) |
| **Fecha de cierre de gaps** | 2026-08-28 |
| **Fuentes cruzadas** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md), [HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md); iDetectFugas `06`/`07`/`08` |
| **Veredicto global** | **A+ en código y especificación de borde.** Soak 24 h de planta (**G-DISK-08**) sigue pendiente — no sustituye los tests de caos. |

---

## 1. Resumen ejecutivo

El stack SAF de PyAutomationIO ya desacoplaba el hot path del disco (ring RAM + flusher WAL `synchronous=FULL`) y replicaba por lotes con ACK exact-once. Esta ronda cierra los gaps que impedían el checklist WD de clase mundial:

| Antes (2026-08-28 AM) | Después |
|---|---|
| Sin BOM de SSD industrial | [docs/HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md) + `deploy/HARDWARE_REQUIREMENTS.md` |
| Solo `% uso` de disco | SMART wear/temp + `ALM.PERF.SSD` + tile HMI |
| `JournalDiskFullError` sin test | Tests de guardia y de llenado real |
| Journal sin `cache_size`/`mmap_size` | `cache_size=-64000`, `mmap_size=256 MiB` |
| catalog sin `temp_store=MEMORY` | PRAGMA añadido |
| Doble `set_value` umbral (mixin / apply 1 Hz) | Apply solo si cambió; publish heartbeat 10 s si apply no escribió |
| Healthcheck ciego al montaje | Warning `noatime` (no tumba el contenedor) |

**Puntuación WD-01…WD-10:** 10 / 10 **PASS** en código y documentación. Certificación operativa 24 h: plantilla [SOAK_DISK_LAST_RUN.md](./SOAK_DISK_LAST_RUN.md) (pendiente de rellenar).

---

## 2. Criterios WD-01…WD-10

| ID | Criterio | Estado | Evidencia |
|---|---|---|---|
| **WD-01** | Hot path sin E/S síncrona | ✅ PASS | `TagObserver` → `enqueue` → ring; flush en `SafJournalFlusher` (`journal.py` `_flush_loop`) |
| **WD-02** | Buffer en memoria | ✅ PASS | `_ring` `deque`, `ring_maxsize=100_000`; `CycleSampleCache` |
| **WD-03** | Journal durable WAL + FULL | ✅ PASS | `PRAGMA journal_mode=WAL`, `synchronous=FULL` |
| **WD-04** | Escritura por lotes | ✅ PASS | `tag_batch_size=256`, `replicate_batch_size=1000` |
| **WD-05** | Exact-once + ACK | ✅ PASS | `mark_sent` post-outcomes; T-01 SIGKILL |
| **WD-06** | Capacidad journal + no llenar disco | ✅ PASS | `max_disk_bytes=10 GiB`, `max_pending_rows=5e6`; evict SENT; `JournalDiskFullError`; tests `test_disk_full_error_*` |
| **WD-07** | Frecuencia de escritura | ✅ PASS | Umbrales 10 s / on-change; `_set_process_tag_if_changed`; mixin no republica el mismo tick |
| **WD-08** | Pruebas de caos | ✅ PASS | Red/BD existentes + **disco lleno** + pragmas; soak 24 h es G-DISK-08 (planta) |
| **WD-09** | Hardware aprobado | ✅ PASS | Spec SSD TBW/temp/OP + fstab `noatime` + scheduler; warning en healthcheck/sampler |
| **WD-10** | Monitoreo activo | ✅ PASS | Cola SAF + `% disco` + `HOST_DISK_NOATIME` + SMART + `ALM.PERF.SSD` |

**Nota WD-09/WD-10:** el código no puede certificar el SKU físico de planta. PASS = especificación + instrumentación + alarmas. El operador debe cumplir el checklist de [HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md) y definir `AUTOMATION_SSD_DEVICE`. Sin `smartctl`, las métricas SSD quedan `null` y **no** hay falso positivo.

---

## 3. Hallazgos detallados (lista §3 original)

### 3.1 Store-and-Forward

Todos los controles de arquitectura **cumplen** (hot path, ring, WAL, batch, ACK, circuit breaker, topes). El journal **no** descarta PENDING para hacer sitio: primero evict SENT; si no basta, `JournalDiskFullError`. Eso protege integridad frente a un ring buffer clásico que pisaría datos no ACK.

### 3.2 SQLite

| PRAGMA | journal.db | catalog.db |
|---|---|---|
| `journal_mode` | WAL | WAL |
| `synchronous` | FULL | NORMAL (1) — correcto: no es Plan A de muestras |
| `temp_store` | MEMORY | MEMORY |
| `cache_size` | −64000 (64 MiB) | −8000 |
| `mmap_size` | 256 MiB (hint) | — |
| `auto_vacuum` | INCREMENTAL + `reclaim_idle` | INCREMENTAL + `compact_catalog_idle` |

### 3.3 Hot path iDetectFugas

- Umbrales: `_publish_threshold_tags` on-change o 10 s.
- `leak` una vez por ciclo (`07-AUDIT_CVT.md`).
- `Leaks.put` fingerprint.
- Alarmas SocketIO en flanco.
- **G-DISK-07 cerrado:** `_set_process_tag_if_changed` + `_finish_threshold_sync` (PPA, NPW, PFM, Observer, mixin).

### 3.4 OS / hardware

Documentado y medido; no impuesto por Docker. `healthcheck.py` avisa si falta `noatime` y **sigue devolviendo 200** si `/api/health/ping` responde.

### 3.5 Pruebas

| Prueba | Archivo |
|---|---|
| Disco lleno (guardia + append) | `test_store_and_forward.py` `test_disk_full_error_*` |
| PRAGMAs journal | `test_journal_pragmas_durable_and_cached` |
| Mount / SMART / sampler | `test_disk_durability.py` |
| catalog `temp_store` | `test_long_run_hardening.py` `test_catalog_temp_store_memory` |
| Umbral una escritura/tick | iDetectFugas `test_threshold_publish.py` |
| Caos red/BD / T-01 | `test_store_and_forward.py` (ya existía) |

---

## 4. Gaps G-DISK-01…09 — estado post-implementación

| ID | Pri. | Estado | Acción realizada |
|---|---|---|---|
| G-DISK-01 | P0 | ✅ Cerrado | `docs/HARDWARE_REQUIREMENTS.md` + `idetectfugas/deploy/HARDWARE_REQUIREMENTS.md` |
| G-DISK-02 | P0 | ✅ Cerrado | `ssd_health.py` + sampler 60 s + `ALM.PERF.SSD` + HMI `/performance` |
| G-DISK-03 | P1 | ✅ Cerrado | Tests `JournalDiskFullError` |
| G-DISK-04 | P1 | ✅ Cerrado | Spec fstab/scheduler; `disk_mount.py`; warning healthcheck; `deploy/README.md` |
| G-DISK-05 | P2 | ✅ Cerrado | `PRAGMA cache_size=-64000`, `mmap_size=268435456` |
| G-DISK-06 | P2 | ✅ Cerrado | Tabla de roles en [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md) |
| G-DISK-07 | P2 | ✅ Cerrado | Apply on-change; publish solo si apply no escribió |
| G-DISK-08 | P3 | ⏳ Planta | Plantilla [SOAK_DISK_LAST_RUN.md](./SOAK_DISK_LAST_RUN.md) |
| G-DISK-09 | P3 | ✅ Cerrado | `temp_store=MEMORY` en `open_catalog_db` |

---

## 5. Evidencia de implementación (diff lógico)

### PyAutomationIO

| Archivo | Cambio |
|---|---|
| `automation/persistence/journal.py` | `cache_size`, `mmap_size` |
| `automation/catalog/local_db.py` | `temp_store=MEMORY` |
| `automation/utils/disk_mount.py` | **nuevo** — `/proc/self/mountinfo`, scheduler |
| `automation/utils/ssd_health.py` | **nuevo** — parse `smartctl -j` |
| `automation/workers/metrics_sampler.py` | mount + SMART + evento SSD |
| `automation/utils/performance_alarms.py` | `ALM.PERF.SSD` |
| `automation/utils/performance_alarm_config.py` | `perf_ssd_*` |
| `healthcheck.py` | warning `noatime` (no fail) |
| `docs/HARDWARE_REQUIREMENTS.md` | BOM SSD / fstab / SMART |
| `hmi/src/pages/Performance.tsx` | tile SSD |
| `automation/tests/test_disk_durability.py` | **nuevo** |
| `automation/tests/test_store_and_forward.py` | disco lleno + pragmas |

### iDetectFugas

| Archivo | Cambio |
|---|---|
| `app/core.py` | `_set_process_tag_if_changed`, `_finish_threshold_sync` |
| `app/modules/motor_threshold_mixin.py` | no republica si apply escribió |
| `app/modules/ppa|npw|pfm|observer` | apply on-change + finish sync |
| `app/tests/test_threshold_publish.py` | **nuevo** |
| `deploy/HARDWARE_REQUIREMENTS.md` | copia planta |
| `deploy/README.md` | sección almacenamiento |

### Referencias de código (puntos de partida)

```863:869:github/PyAutomation/automation/persistence/journal.py
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA cache_size=-64000")
            self._conn.execute("PRAGMA mmap_size=268435456")
            self._conn.execute(f"PRAGMA wal_autocheckpoint={int(self.config.wal_autocheckpoint)}")
            self._conn.execute("PRAGMA foreign_keys=ON")
```

Variables de entorno SSD: `AUTOMATION_SSD_DEVICE`, `AUTOMATION_SSD_WEAR_WARN` (80), `AUTOMATION_SSD_TEMP_WARN` (65).

---

## 6. Lecciones aprendidas

1. **Distroless no tiene `smartctl`.** El sampler debe degradar a `available=false` sin alarmar. El dispositivo se lee en el host o con bind-mount documentado.
2. **No tumbar el HEALTHCHECK por `noatime`.** Un bind Docker hereda el fstab del host; fallar el ping dejaría el stack `unhealthy` en labs que aún no tunearon el disco.
3. **PENDING no se pisa.** El “ring buffer de disco” de clase mundial para DAQ es tope + error controlado, no overwrite de filas sin ACK.
4. **El residual bayesiano no era solo el mixin.** PPA/NPW ya no llamaban `_publish` desde `_sync`; el 1 Hz venía de `_apply` → `set_value` cada tick. El arreglo real es skip-if-unchanged + heartbeat 10 s.

---

## 7. Conclusión

**A+ (clase mundial) en software:** WD-01…WD-10 PASS con evidencia en código, tests y especificación de hardware. El sistema está diseñado para 24/7/365 en borde industrial con SSD de alto TBW, journal WAL durable, backpressure y monitoreo SMART.

**Pendiente operativo (no bloquea el veredicto de código):** ejecutar y archivar la campaña de [SOAK_DISK_LAST_RUN.md](./SOAK_DISK_LAST_RUN.md) (24 h + outage PG 4 h) y confirmar SMART visible en cada edge de planta.
