# Auditorías PyAutomationIO — índice compacto

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Fecha de compactación** | 2026-08-18 |
| **Alcance** | Contraste código vs diseño; no son especificaciones de producto (`specs/` y `docs/` cubren eso) |
| **Regla** | Un documento por dominio. Lo desactualizado se actualizó contra evidencia de código del 2026-08-18 |

---

## Documentos canónicos (10)

| Doc | Archivo | Absorbe | Veredicto vigente |
|---|---|---|---|
| **01 Índice** | [README.md](./README.md) | — | Mapa de navegación |
| **02 BD y conexiones** | [AUDIT_DB.md](./AUDIT_DB.md) | `AUDIT_DB_CONNECTIONS`, `AUDIT_DB_CONNECTIONS_ETERNAL`, `AUDIT_OPTIMAL_CONNECTIONS`, `AUDIT_DB_RECONNECT`, `AUDIT_NETWORK_TIMEOUT`, `AUDIT_DB_CONNECTION_MEMORY` | Un handle Peewee; idle 1 worker **1–3** (techo **≤ 4**); pool Peewee **prohibido**; reconexión owner-scoped |
| **03 Rendimiento y memoria** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) | `AUDIT_BACKEND_PERFORMANCE`, `AUDIT_MEMORY`, `PERFORMANCE_RUNBOOK` | Hot path **A−**; ciclo de vida observers cerrado; soak 24 h **pendiente** |
| **04 HMI** | [AUDIT_HMI.md](./AUDIT_HMI.md) | `AUDIT_HMI_PERFORMANCE`, `AUDIT_RT_TRENDS` | Heap acotado **A**; forma de onda RT con cola por tag (no last-wins en historial) |
| **05 Store-and-Forward** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) | `STORE_AND_FORWARD`, `PERSISTENCE_FLOW`, `T01_SOAK_LAST_RUN` | **A+** durabilidad; historiador ≠ mapeo OPC UA |
| **06 Multi-edge** | [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) | (ya era único) | Fase 1 en código; soak 2-edge y RLS **pendientes** |
| **07 Logs, eventos y bitácora** | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) | `AUDIT_LOGGING`, `AUDIT_USER_EVENTS`, `AUDIT_OPERATIONAL_LOGS` | L1 **A+**; Events **A−**; bitácora **A+** |
| **08 Tiempo** | [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) | (ya era único; actualizado) | Operación «Hora Única»: UTC en wire; selector planta/local en HMI |
| **09 Acondicionamiento de señal** | [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md) | `AUDIT_TAG_NOISE_FILTERS` | **D+** producto: Kalman 1D experimental; `process_filter` e IAD no corren |
| **10 Máquinas de estado** | [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) | (nuevo 2026-08-18) | Capas de muestreo independientes; buffer canónico `self.data` **huérfano** (SM-H1); ventana real = ciclo de máquina |

---

## Cómo usar este índice

1. Incidente de planta → abrir el dominio, no el hallazgo histórico suelto.
2. IDs de hallazgos (`BE-H4`, `CA-DB-1`, `HMI-C1`, `CA-EDGE-1`, …) **se conservan**.
3. El runbook operativo de deriva (RSS, OPC, SAF, conexiones, logs) vive en [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) § Runbook.
4. Specs de arquitectura: `specs/01-MULTI-EDGE-ARCHITECTURE.md` (el estado de implementación real está en [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), no en el encabezado «propuesta» de la spec).

---

## Fuentes absorbidas (ya no existen como archivos)

`AUDIT_DB_CONNECTIONS.md`, `AUDIT_DB_CONNECTIONS_ETERNAL.md`, `AUDIT_OPTIMAL_CONNECTIONS.md`, `AUDIT_DB_RECONNECT.md`, `AUDIT_NETWORK_TIMEOUT.md`, `AUDIT_DB_CONNECTION_MEMORY.md`, `AUDIT_BACKEND_PERFORMANCE.md`, `AUDIT_MEMORY.md`, `PERFORMANCE_RUNBOOK.md`, `AUDIT_HMI_PERFORMANCE.md`, `AUDIT_RT_TRENDS.md`, `STORE_AND_FORWARD.md`, `PERSISTENCE_FLOW.md`, `AUDIT_USER_EVENTS.md`, `AUDIT_OPERATIONAL_LOGS.md`, `AUDIT_TAG_NOISE_FILTERS.md`.

## Artefacto de soak (no es auditoría canónica)

`T01_SOAK_LAST_RUN.md` lo regenera `automation/tests/test_store_and_forward.py`. El contrato y el último resultado interpretado viven en [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md).
