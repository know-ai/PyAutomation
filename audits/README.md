# Auditorías PyAutomationIO — índice compacto

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Fecha de compactación** | 2026-08-20 · **revisión suscripción/domain 2026-09-01** · **auth/authz 2026-09-03** · **UI/UX Real-Time Trends 2026-09-09** · **SAF nuclear 2026-09-15** · **ISA 18.2 alarmas 2026-09-16** · **agrupación 10 documentos 2026-09-16** |
| **Alcance** | Contraste código vs diseño; no son especificaciones de producto (`specs/` y `docs/` cubren eso) |
| **Regla** | Un documento por dominio. Lo desactualizado se actualiza contra evidencia de código (última revisión **2026-09-16**) |

---

## Documentos canónicos (10)

| Doc | Archivo | Absorbe | Veredicto vigente |
|---|---|---|---|
| **01 Alarmas** | [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) | `AUDIT_ISA18_2_ALARMS` + informes ISA18-2 (P0/P1/P2, EXPLAIN, E2E, partición, baseline, schema SQL) | SM **A−** · historial **A−** · footer **A** · hot path **A**; P2 **con waivers** (partición live) |
| **02 Tags** | [AUDIT_TAGS.md](./AUDIT_TAGS.md) | `AUDIT_SIGNAL_CONDITIONING`, `AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP`, `AUDIT_CATALOG_SQLITE_LOCAL`, `AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE` | Wavelet **A−** / nuclear **C** · OPC **A−** · catálogo local **A** código / sync **A−** · consistencia proceso **A** / sidecar **B−** |
| **03 HMI** | [AUDIT_HMI.md](./AUDIT_HMI.md) | `AUDIT_HMI_PERFORMANCE`, `AUDIT_RT_TRENDS`, `AUDIT_REALTIME_TRENDS_UIUX`, `AUDIT_HMI_SOCKET_TRACEABILITY`, `AUDIT_HMI_MACHINE_DOMAIN_EXTENSION` | Heap **A** · forma de onda RT cola por tag · layout RT **B+ código** / datos **A−** · socket **A+** · machines/domain **A** |
| **04 BD, SAF y disco** | [AUDIT_DB.md](./AUDIT_DB.md) | `AUDIT_DB_CONNECTIONS*`, `AUDIT_STORE_AND_FORWARD`, `AUDIT_DISK_DURABILITY`, `T01_SOAK_LAST_RUN`, `SOAK_DISK_LAST_RUN` | Un handle Peewee; idle **1–3** (techo **≤ 4**); pool **prohibido**. SAF **A+** / Bulkhead **A**. Disco **A+** código; soak 24 h planta pendiente |
| **05 Rendimiento** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) | `AUDIT_BACKEND_PERFORMANCE`, `AUDIT_MEMORY`, `PERFORMANCE_RUNBOOK`, `AUDIT_NODE_PERFORMANCE_DASHBOARD` | Hot path **A−**; dashboard **A−** (`ALM.PERF.*`); soak 24 h / 2-edge / HMI planta pendientes |
| **06 Multi-edge** | [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) | (único; catálogo de tags vive en 02) | Fase 1 en código; planta 2-edge 2026-08-25: 3 binds Linea2→DAQ Linea1; RLS y soak 24 h pendientes |
| **07 Tiempo** | [AUDIT_TIME.md](./AUDIT_TIME.md) | `AUDIT_TIMEZONE`, `AUDIT_NTP_TIME_SYNC` | Hora Única: UTC en wire. NTP **A** (monitor v2.0); soak 2-edge pendiente (A+) |
| **08 Máquinas de estado** | [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) | (único; spec 02) | Tres relojes; SM-H1 cerrado en modo `sample_interval`; iDetectFugas dual-path |
| **09 Auth / Authz** | [AUDIT_AUTH_AUTHORIZATION.md](./AUDIT_AUTH_AUTHORIZATION.md) | Login/sesión/TPT; ACL `authz_grants`; roles dinámicos; Swagger; bus Redis/PG | Auth **A−** · Authz **A−** — ACL fail-closed; Socket.IO por vista pendiente |
| **10 Fiabilidad** | [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) | `AUDIT_LOGGING`, `AUDIT_LONG_RUN_CONTINUITY`, `AUDIT_MISSION_CRITICAL`, `CHAOS_LAST_RUN` | Logs: app ≠ eventos; Loki **C**. Continuidad edge **A−** / PG **B−**. Misión **A− / B+**; campaña OT pendiente |

---

## Cómo usar este índice

1. Incidente de planta → abrir el dominio, no el hallazgo histórico suelto.
2. IDs de hallazgos (`BE-H4`, `CA-DB-1`, `HMI-C1`, `CA-EDGE-1`, `GAP-01`, …) **se conservan**.
3. El runbook operativo de deriva (RSS, OPC, SAF, conexiones, logs) vive en [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) Parte A § Runbook.
4. Specs de arquitectura: `specs/01-MULTI-EDGE-ARCHITECTURE.md` (el estado de implementación real está en [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md)).
5. Login, sesión, ACL REST/HMI (`authz_grants`, `/api/authz/me`): [AUDIT_AUTH_AUTHORIZATION.md](./AUDIT_AUTH_AUTHORIZATION.md).
6. Layout / edición de `/real-time-trends` (spec HMI 2.10): [AUDIT_HMI.md](./AUDIT_HMI.md) Parte B. Fidelidad de serie y heap: Parte A.
7. T-01 soak lo regenera `automation/tests/test_store_and_forward.py` dentro de [AUDIT_DB.md](./AUDIT_DB.md) (marcadores `T01_SOAK_LAST_RUN`). La campaña 24 h de disco/SAF y la de caos CT-07 son plantillas en [AUDIT_DB.md](./AUDIT_DB.md) Parte D y [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) Parte D.

---

## Fuentes absorbidas (ya no existen como archivos)

`AUDIT_DB_CONNECTIONS.md`, `AUDIT_DB_CONNECTIONS_ETERNAL.md`, `AUDIT_OPTIMAL_CONNECTIONS.md`, `AUDIT_DB_RECONNECT.md`, `AUDIT_NETWORK_TIMEOUT.md`, `AUDIT_DB_CONNECTION_MEMORY.md`, `AUDIT_BACKEND_PERFORMANCE.md`, `AUDIT_MEMORY.md`, `PERFORMANCE_RUNBOOK.md`, `AUDIT_HMI_PERFORMANCE.md`, `AUDIT_RT_TRENDS.md`, `STORE_AND_FORWARD.md`, `PERSISTENCE_FLOW.md`, `AUDIT_USER_EVENTS.md`, `AUDIT_OPERATIONAL_LOGS.md`, `AUDIT_TAG_NOISE_FILTERS.md`, `AUDIT_ISA18_2_ALARMS.md`, `ISA18-2-P0P1-REPORT.md`, `ISA18-2-BASELINE.md`, `ISA18-2-COMPLEXITY-REPORT.md`, `ISA18-2-EXPLAIN.md`, `ISA18-2-EXPLAIN-PG.md`, `ISA18-2-EXPLAIN-PG-raw.txt`, `ISA18-2-E2E-REPORT.md`, `ISA18-2-PARTITION-PLAN.md`, `ISA18-2-P1-CLOSURE-REPORT.md`, `ISA18-2-P2-CLOSURE-REPORT-v2.md`, `AUDIT_SIGNAL_CONDITIONING.md`, `AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md`, `AUDIT_CATALOG_SQLITE_LOCAL.md`, `AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md`, `AUDIT_REALTIME_TRENDS_UIUX.md`, `AUDIT_HMI_SOCKET_TRACEABILITY.md`, `AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md`, `AUDIT_STORE_AND_FORWARD.md`, `AUDIT_DISK_DURABILITY.md`, `AUDIT_NODE_PERFORMANCE_DASHBOARD.md`, `AUDIT_TIMEZONE.md`, `AUDIT_NTP_TIME_SYNC.md`, `AUDIT_LOGGING.md`, `AUDIT_LONG_RUN_CONTINUITY.md`, `AUDIT_MISSION_CRITICAL.md`, `T01_SOAK_LAST_RUN.md`, `SOAK_DISK_LAST_RUN.md`, `CHAOS_LAST_RUN.md`, `p2/alarmsummary.schema.sql`.
