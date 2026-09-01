# Auditoría de puntos críticos de misión (CT-01…CT-07)

| Campo | Valor |
|---|---|
| **Productos** | PyAutomationIO (`github/PyAutomation`, rama de trabajo) + iDetectFugas (`gitlab/intelcon/idetectfugas`) |
| **Alcance** | Sincronización temporal, integridad ante cortes de energía, sesiones, redundancia, actualizaciones, monitorización, caos |
| **Estándar de referencia** | Grado nuclear industrial / 24/7/365 — **código + spec**, no certificación de planta |
| **Fecha** | 2026-08-28 |
| **Audiencia** | Ingeniería, operaciones, seguridad |
| **Fuentes** | [AUDIT_NTP_TIME_SYNC.md](./AUDIT_NTP_TIME_SYNC.md), [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_DISK_DURABILITY.md](./AUDIT_DISK_DURABILITY.md), [docs/multi-edge.md](../docs/multi-edge.md), [docs/CHAOS_TESTING.md](../docs/CHAOS_TESTING.md) |

**Regla de veredicto:** PASS de código no es “grado nuclear alcanzado en planta”. Soak, caos OT y hardware PLP/UPS van como pendientes con plantilla, no como ejecutados.

---

## 1. Resumen ejecutivo

El stack ya era fuerte en SAF (WAL + ACK exact-once), NTP de aplicación, sesiones HMI auditadas y dashboard `/performance`. Esta ronda cierra los huecos **nombrados** por la spec CT (métrica `HOST_NTP_OFFSET_MS`, gate SAF a 1 s, `fsync` post-COMMIT, heartbeat de pares, runbook de caos, rollback documentado) **sin inventar** un failover que robe tags ni un restart &lt; 10 s.

| ID | Área | Nota | Estado código/spec | Planta |
|---|---|---|---|---|
| CT-01 | Tiempo | NTP + `ALM.PERF.NTP` + gate SAF | **A** | soak 2-edge pendiente |
| CT-02 | Energía | FULL + fsync + PLP documentado + T-01 | **A+** | soak 24 h / UPS pendiente |
| CT-03 | Sesiones | TTL por heartbeat, fail-closed token, audit Events | **A** | soak 2-edge pendiente |
| CT-04 | Failover | Circuit breaker + `ALM.PERF.NODE_DOWN`; **no** steal-tags | **B+** (diseño) | lab C-04 pendiente |
| CT-05 | Zero-DT | Volúmenes persistentes; rolling por línea; overlay ~30 s | **B** | procedimiento en deploy |
| CT-06 | Salud | `/performance` + `/lds-dashboard` + 16 `ALM.PERF.*` | **A−** | scrape Prometheus opcional |
| CT-07 | Caos | Runbook + plantilla + unitarios; campaña OT vacía | **B+** | [CHAOS_LAST_RUN.md](./CHAOS_LAST_RUN.md) |

**Puntuación global (código):** **A− / B+**. No se declara “grado nuclear industrial alcanzado” mientras CT-04-A (I/O failover), CT-05-B (&lt; 10 s) y CT-07-D (campaña firmada) sigan fuera de contrato o pendientes.

---

## 2. Hallazgos por control

### CT-01 Sincronización temporal

**Pregunta:** ¿Todos los nodos comparten fuente de tiempo y se monitorea el desfase?

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-01-A | NTP en nodos | ✅ PASS | `AUTOMATION_NTP_SERVERS`; chrony en [docs/ntp-deployment.md](../docs/ntp-deployment.md); comentarios en `compose/.env` y `deploy/.env` |
| CT-01-B | Deriva | ✅ PASS | `HOST_NTP_OFFSET_MS` / `HOST_NTP_ABS_OFFSET_MS` en sampler; `ALM.PERF.NTP` default **100 ms**; crítica `ALM.NTP.OutOfSync` **1000 ms** (`ntp_monitor.py`, `clock_alarms.py`) |
| CT-01-C | Timestamps UTC | ⚠️ CONDICIONAL | Wire UTC ([AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md)); TagValue resolución **ms** (`TAGVALUE_TIMESTAMP_RESOLUTION = 3`), no µs — UNIQUE `(tag, timestamp)` |
| CT-01-D | Gate SAF | ✅ PASS | `clock_blocks_replication()`: si NTP enabled y `|offset| > 1000 ms`, no replica; PENDING intacto; no abre el circuit breaker |

**Gaps residuales**

- Precisión µs en TagValue: **no se cambia** (colapsaría UNIQUE y el ciclo de máquina).
- `ntp_fail_closed` sigue siendo opt-in (pausa adquisición); el gate SAF a 1 s aplica con el monitor activo aunque fail-closed esté en false.

### CT-02 Integridad ante cortes de energía

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-02-A | `synchronous=FULL` | ✅ PASS | `journal.py` `_ensure_open_locked` |
| CT-02-B | fsync post-COMMIT | ✅ PASS | FD `O_RDONLY` + `os.fsync` en `_commit_locked` |
| CT-02-C | Hardware PLP | ✅ PASS spec | [HARDWARE_REQUIREMENTS.md](../docs/HARDWARE_REQUIREMENTS.md) § power-loss (UPS + SSD PLP) |
| CT-02-D | `data=ordered` | ✅ PASS | fstab documentado; `HOST_DISK_DATA_ORDERED`; warning en `healthcheck.py` (no tumba ping) |
| CT-02-E | SIGKILL | ✅ PASS tests | `TestT01Apocalypse`; plantilla soak [SOAK_DISK_LAST_RUN.md](./SOAK_DISK_LAST_RUN.md) |

### CT-03 Sesiones y trazabilidad

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-03-A | TTL | ✅ PASS | No hay columna `expires_at`; TTL = `last_heartbeat` + 120 s (`hmi_session_cleanup.py`) |
| CT-03-B | Heartbeat | ✅ PASS | Socket ping/pong; `register_hmi_socket_heartbeat` |
| CT-03-C | Fail-closed auth | ⚠️ CONDICIONAL | Token inválido → rechazo. Store de sesión caído → **acepta** socket con `session_store_degraded` (autonomía de catálogo local). No se cambia: rompería HMI offline. |
| CT-03-D | Trazabilidad | ✅ PASS | Events HMI connect/disconnect/reject (`hmi_socket_audit.py`); login API en Events |
| CT-03-E | No reutilizar sid | ✅ PASS | sid Socket.IO único; logout/disconnect borra store |

Detalle: [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md) (A+ código).

### CT-04 Redundancia y failover

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-04-A | Multi-edge steal-tags | ❌ FAIL de spec / ✅ diseño | **Edge B no asume tags de A.** Partición `owner_node` + rechazo SAF extranjero. Documentado en [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) y [docs/multi-edge.md](../docs/multi-edge.md). Implementar steal-tags sería split-brain de I/O. |
| CT-04-B | Circuit breaker | ✅ PASS | `replicator.py` `CircuitBreaker` |
| CT-04-C | Heartbeat pares | ✅ PASS | `Nodes.heartbeat` cada tick del sampler; `ALM.PERF.NODE_DOWN` |
| CT-04-D | Runbook + caos | ⚠️ CONDICIONAL | Runbook sí; campaña C-04 en [CHAOS_LAST_RUN.md](./CHAOS_LAST_RUN.md) pendiente |
| CT-04-E | Split-brain | ✅ PASS | Single-writer por área; samples ajenos a SENT/descartados |

### CT-05 Actualizaciones sin downtime

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-05-A | Estrategia | ⚠️ CONDICIONAL | Rolling **por línea**, no blue-green en el mismo puerto. iDetectFugas `deploy/README.md` |
| CT-05-B | Restart &lt; 10 s | ❌ FAIL | `_restart_eta_s` ≈ **30 s** (delay 2 + graceful 10 + boot 15 + recycle 3). LGBM ya no infla el overlay (hilo nativo). Sigue sin ser &lt; 10 s. iDetectFugas `audits/13-AUDIT_CONTAINER_STARTUP.md` |
| CT-05-C | Estado persistente | ✅ PASS | `data/db`, `data/configs`, `data/models` bind mounts |
| CT-05-D | Rollback | ✅ PASS docs | Restaurar `AUTOMATION_VERSION` + `./up.sh`; backup tar |
| CT-05-E | CI smoke deploy | ⚠️ CONDICIONAL | Unitarios sí; job de imagen+smoke de planta no es parte de este repo de framework |

Mitigación: overlay HMI durante el reciclo; la otra línea sigue adquiriendo.

### CT-06 Monitorización proactiva

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-06-A | Salud sistema | ✅ PASS | `/api/health/system` y `/api/health/node` |
| CT-06-B | KPI negocio (fugas) | ✅ PASS | Dashboard `/lds-dashboard` + `GET /api/LDS/dashboard` (iDetectFugas `audits/14-AUDIT_LDS_DASHBOARD.md`). No vive en `/performance`. |
| CT-06-C | Alertas tempranas | ✅ PASS | `ALM.PERF.*` (16 specs) + NTP/SSD/NODE_DOWN |
| CT-06-D | Events de salud | ✅ PASS | Transiciones NTP, disco crítico, SSD, HMI |
| CT-06-E | Dashboard HMI | ✅ PASS | `/performance` chips NTP y nodo par |
| CT-06-F | Prometheus | ✅ PASS docs | [docs/observability.md](../docs/observability.md) — scrape JSON, sin exporter nativo |

### CT-07 Pruebas de caos

| ID | Control | Estado | Evidencia |
|---|---|---|---|
| CT-07-A | Runbook | ✅ PASS | [docs/CHAOS_TESTING.md](../docs/CHAOS_TESTING.md) |
| CT-07-B | Simulación | ✅ PASS tests | T-01, disco lleno, circuit, catalog, `test_mission_critical.py` |
| CT-07-C | RTO/RPO | ⚠️ CONDICIONAL | Objetivos escritos; **no medidos en OT** |
| CT-07-D | Última campaña | ⚠️ CONDICIONAL | Plantilla [CHAOS_LAST_RUN.md](./CHAOS_LAST_RUN.md) |
| CT-07-E | CI caos corto | ✅ PASS opcional | unittest listado en el runbook |

---

## 3. Plan de implementación (esta ronda)

| Pri. | Gap | Acción | Estado |
|---|---|---|---|
| P0 | CT-01-B/D | `HOST_NTP_*`, `ALM.PERF.NTP`, gate replicador 1 s | Hecho |
| P0 | CT-02-B/C/D | `os.fsync`, PLP doc, `data=ordered` en snapshot/healthcheck | Hecho |
| P0 | CT-04-C | Heartbeat `Nodes.last_seen` + `ALM.PERF.NODE_DOWN` | Hecho |
| P1 | CT-05-A/D | Rolling + rollback en `deploy/README.md` | Hecho |
| P1 | CT-07 | CHAOS runbook + plantilla | Hecho |
| P2 | CT-06-F | `docs/observability.md` | Hecho |
| P2 | CT-04-A | **No implementar** steal-tags | Documentado |
| P2 | CT-05-B | **No afirmar** restart &lt; 10 s | Documentado |
| P3 | CT-06-B | KPI fugas: dashboard `/lds-dashboard` (iDetect + HMI) | Hecho |
| P3 | CT-07-D | Ejecutar C-01…C-05 en lab y firmar `CHAOS_LAST_RUN.md` | Abierto |

---

## 4. Evidencia de implementación (código)

| Archivo | Cambio |
|---|---|
| `automation/persistence/journal.py` | FD durabilidad + `os.fsync` post-COMMIT |
| `automation/persistence/replicator.py` | `clock_blocks_replication` |
| `automation/dbmodels/nodes.py` | `heartbeat`, `stale_peer_ids` |
| `automation/managers/db.py` | wrappers |
| `automation/workers/metrics_sampler.py` | `HOST_NTP_*`, `_sample_peers` |
| `automation/utils/performance_alarms.py` | specs `ntp`, `node_down` |
| `automation/utils/performance_alarm_config.py` | umbrales 100 ms / bool |
| `automation/utils/disk_mount.py` | `HOST_DISK_DATA_ORDERED` |
| `healthcheck.py` | warning `data=ordered` |
| `hmi/src/pages/Performance.tsx` | chips NTP / peer |
| `automation/tests/test_mission_critical.py` | **nuevo** |
| `docs/CHAOS_TESTING.md`, `docs/observability.md` | **nuevos** |
| `audits/CHAOS_LAST_RUN.md` | plantilla |
| `docs/HARDWARE_REQUIREMENTS.md` | § power-loss |
| iDetectFugas `deploy/README.md` | update / rollback / NTP; overlay ~30 s |
| `automation/modules/health/resources/health.py` | `/liveness`, `/readiness` (Fase A; LGBM no bloquea) |

Tests: `test_mission_critical`, pragmas journal (`_durability_fd`), `test_disk_durability` `data=ordered`, catálogo PERF 16.

---

## 5. Checklist clase mundial (honesto)

| ID | Área | Criterio spec | Estado |
|---|---|---|---|
| CT-01 | Tiempo | NTP configurado, monitoreado, alarmado | ✅ PASS código (ms, no µs) |
| CT-02 | Energía | FULL + fsync + hardware spec + T-01 | ✅ PASS código/spec |
| CT-03 | Sesiones | TTL, heartbeat, audit; fail-closed token | ✅ PASS con fail-open store degradado |
| CT-04 | Failover | Multi-edge + breaker + heartbeat | ⚠️ CONDICIONAL (sin steal-tags) |
| CT-05 | Zero-DT | Docs + persistencia + rollback | ⚠️ CONDICIONAL (~30 s overlay, no &lt; 10 s) |
| CT-06 | Salud | Métricas, alarmas, dashboard | ✅ PASS; KPI fugas en `/lds-dashboard` |
| CT-07 | Caos | Runbook + RTO/RPO escritos + tests | ⚠️ CONDICIONAL (campaña OT vacía) |

**Veredicto final:** el sistema está **listo para operar 24/7 por línea con SAF y fail-closed de I/O**. No está certificado como planta nuclear hasta: (1) UPS/SSD PLP instalados, (2) `CHAOS_LAST_RUN.md` firmado, (3) soak 24 h 2-edge, (4) `AUTOMATION_NTP_SERVERS` en cada Moxa. El failover mágico de adquisición **no forma parte del producto**.
