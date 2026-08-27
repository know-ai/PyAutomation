# Auditorías PyAutomationIO — índice compacto

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Fecha de compactación** | 2026-08-20 |
| **Continuidad día-1000** | 2026-08-27 — [AUDIT_LONG_RUN_CONTINUITY.md](./AUDIT_LONG_RUN_CONTINUITY.md); hardening R1–R5 en código; deploy/soak planta pendiente |
| **Revisión aislamiento Bulkhead** | 2026-08-25 — CA-ISOLATION-01…04 en código; CA-ISOLATION-05 soak planta |
| **Revisión controles `/performance`** | 2026-08-25 — CA-OPS-01…04 en código; CA-OPS-02/05 HMI planta |
| **Auditoría consistencia catálogo planta** | 2026-08-25 — 2 edges reales + PG; ver [AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md](./AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md) |
| **Alcance** | Contraste código vs diseño; no son especificaciones de producto (`specs/` y `docs/` cubren eso) |
| **Regla** | Un documento por dominio. Lo desactualizado se actualizó contra evidencia de código del 2026-08-18 |

---

## Documentos canónicos (18)

| Doc | Archivo | Absorbe | Veredicto vigente |
|---|---|---|---|
| **01 Índice** | [README.md](./README.md) | — | Mapa de navegación |
| **02 BD y conexiones** | [AUDIT_DB.md](./AUDIT_DB.md) | `AUDIT_DB_CONNECTIONS`, `AUDIT_DB_CONNECTIONS_ETERNAL`, `AUDIT_OPTIMAL_CONNECTIONS`, `AUDIT_DB_RECONNECT`, `AUDIT_NETWORK_TIMEOUT`, `AUDIT_DB_CONNECTION_MEMORY` | Un handle Peewee; idle 1 worker **1–3** (techo **≤ 4**); pool Peewee **prohibido**; reconexión owner-scoped |
| **03 Rendimiento y memoria** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) | `AUDIT_BACKEND_PERFORMANCE`, `AUDIT_MEMORY`, `PERFORMANCE_RUNBOOK` | Hot path **A−**; ciclo de vida observers cerrado; soak 24 h **pendiente** |
| **04 HMI** | [AUDIT_HMI.md](./AUDIT_HMI.md) | `AUDIT_HMI_PERFORMANCE`, `AUDIT_RT_TRENDS` | Heap acotado **A**; forma de onda RT con cola por tag (no last-wins en historial) |
| **05 Store-and-Forward** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) | `STORE_AND_FORWARD`, `PERSISTENCE_FLOW`, `T01_SOAK_LAST_RUN` | **A+** durabilidad; **A** aislamiento Bulkhead (código); CA-ISOLATION-05 planta pendiente |
| **06 Multi-edge** | [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) | (ya era único) | Fase 1 en código; **planta 2-edge 2026-08-25**: 3 binds Linea2→DAQ Linea1 ([AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md](./AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md)); RLS y soak 24 h pendientes |
| **07 Logs, eventos y bitácora** | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) | `AUDIT_USER_EVENTS`, `AUDIT_OPERATIONAL_LOGS` | **Log aplicación ≠ Eventos**; pantalla HMI dedicada pendiente (LOG-GUI); export Loki **C** |
| **08 Tiempo (presentación)** | [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) | (ya era único; actualizado) | Operación «Hora Única»: UTC en wire; selector planta/local en HMI |
| **09 Acondicionamiento de señal** | [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md) | `AUDIT_TAG_NOISE_FILTERS` | **A− (wavelet RT)** / **C (nuclear)** — calidad OPC en `.f`, legado eliminado; IAD pendiente |
| **10 Máquinas de estado** | [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) | (nuevo 2026-08-18; spec 02) | Tres relojes; SM-H1 cerrado en modo `sample_interval`; iDetectFugas dual-path |
| **11 NTP / reloj edge** | [AUDIT_NTP_TIME_SYNC.md](./AUDIT_NTP_TIME_SYNC.md) | (nuevo 2026-08-19) | **A** — monitor universal v2.0 (IPv4/IPv6, backoff, salto, runbook); soak 2-edge **pendiente** (A+) |
| **12 Trazabilidad Socket HMI** | [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md) | Spec [04-HMI-SOCKET-TRACEABILITY](../specs/04-HMI-SOCKET-TRACEABILITY.md) | **A+** — PG `hmi_sessions`, fail-closed, TLS/IP, heartbeat; soak 2-edge **pendiente** |
| **13 Dashboard performance nodo** | [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](./AUDIT_NODE_PERFORMANCE_DASHBOARD.md) | Specs [05](../specs/05-NODE-PERFORMANCE-DASHBOARD.md) + [06](../specs/06-PERFORMANCE-ALARMS.md) + controles ops 2026-08-25 | **A−** — snapshot O(1), sampler, `/performance`, alarmas `ALM.PERF.*`, controles `/api/admin`; soak 24 h / 2-edge / HMI planta (CA-OPS-02/05) **pendientes** (A+) |
| **14 Calidad OPC + arranque degradado** | [AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md](./AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md) | Specs [09](../specs/09-OPC-QUALITY-AND-DEGRADED-STARTUP.md) + [10](../specs/10-OPC-QUALITY-A-PLUS.md) — verificación 2026-08-21 | **A− disponibilidad** / **A− calidad** (A+ condicionado a soak) / **A Login-UX** — CA-OQ-01…12 PASS; soak 13–15 pendiente |
| **15 Catálogo local SQLite** | [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md) | Spec [11](../specs/11-CATALOG-SQLITE-LOCAL.md) — verificación 2026-08-21 P0 + Bulkhead 2026-08-25 | **A autonomía + integridad reinicio (código)** / **A separación SAF** / **A HMI-API** / **A aislamiento por fila** / **A− sync planta** — CA-01…06/10…13/15…18 + CA-ISOLATION-02…04 PASS; soak 07–09/14 + CA-ISOLATION-05 pendiente |
| **16 Consistencia catálogo planta** | [AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md](./AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md) | Corrida 19:15 + 22:36 · CA-DAQ-01 vivo en planta · CA-CATALOG-NOISE-01/02 en código | **A catálogo de proceso** / **B− sidecar .81** — SyncFailed era umbral, no outage |
| **17 Extensión HMI machines/domain** | [AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md](./AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md) | (nuevo 2026-08-26; implementación Fase A 2026-08-26) | **A** contrato Schema-Driven — pregunta fundamental **SÍ**; Fase B schemas de producto en iDetectFugas |
| **18 Continuidad 1–1000 días** | [AUDIT_LONG_RUN_CONTINUITY.md](./AUDIT_LONG_RUN_CONTINUITY.md) | baseline N1 2026-08-27 + SPEC_LONG_RUN R1–R5 (DLQ, compact catalog, drop SM, disco CRITICAL, config limpia) | Edge **A−** en código; PG **B−** (DBA); deploy + soak 24 h pendiente |

---

## Cómo usar este índice

1. Incidente de planta → abrir el dominio, no el hallazgo histórico suelto.
2. IDs de hallazgos (`BE-H4`, `CA-DB-1`, `HMI-C1`, `CA-EDGE-1`, …) **se conservan**.
3. El runbook operativo de deriva (RSS, OPC, SAF, conexiones, logs) vive en [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) § Runbook.
4. Specs de arquitectura: `specs/01-MULTI-EDGE-ARCHITECTURE.md` (el estado de implementación real está en [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), no en el encabezado «propuesta» de la spec).
5. Extensión de formularios de dominio en `/hmi/machines/detailed` (DIP/OCP, hardcodes producto, contrato Schema-Driven): [AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md](./AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md).

---

## Fuentes absorbidas (ya no existen como archivos)

`AUDIT_DB_CONNECTIONS.md`, `AUDIT_DB_CONNECTIONS_ETERNAL.md`, `AUDIT_OPTIMAL_CONNECTIONS.md`, `AUDIT_DB_RECONNECT.md`, `AUDIT_NETWORK_TIMEOUT.md`, `AUDIT_DB_CONNECTION_MEMORY.md`, `AUDIT_BACKEND_PERFORMANCE.md`, `AUDIT_MEMORY.md`, `PERFORMANCE_RUNBOOK.md`, `AUDIT_HMI_PERFORMANCE.md`, `AUDIT_RT_TRENDS.md`, `STORE_AND_FORWARD.md`, `PERSISTENCE_FLOW.md`, `AUDIT_USER_EVENTS.md`, `AUDIT_OPERATIONAL_LOGS.md`, `AUDIT_TAG_NOISE_FILTERS.md`.

## Artefacto de soak (no es auditoría canónica)

`T01_SOAK_LAST_RUN.md` lo regenera `automation/tests/test_store_and_forward.py`. El contrato y el último resultado interpretado viven en [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md).
