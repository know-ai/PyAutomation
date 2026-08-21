# Especificaciones PyAutomationIO

Índice maestro de especificaciones técnicas de PyAutomationIO (`automation/`).

**Estructura actual (v1.3, 2026-08-21):** **11 documentos temáticos** en la raíz de `specs/`.

---

## Índice de documentos

| Doc | Archivo | Contenido |
|-----|---------|-----------|
| **01** | [01-MULTI-EDGE-ARCHITECTURE.md](./01-MULTI-EDGE-ARCHITECTURE.md) | Adquisición multi-edge, partición por área ISA-95, hidratación acotada, single-writer — **propuesta v1.0** ([AUDIT_MULTI_EDGE](../audits/AUDIT_MULTI_EDGE.md)) |
| **02** | [02-STATE-MACHINE-TEMPORAL-DECOUPLING.md](./02-STATE-MACHINE-TEMPORAL-DECOUPLING.md) | Tres relojes SM (adquisición / muestreo / ejecución) — **implementado v1.0** ([AUDIT_STATE_MACHINES](../audits/AUDIT_STATE_MACHINES.md)) |
| **03** | [03-NTP-EDGE-CLOCK-MONITOR.md](./03-NTP-EDGE-CLOCK-MONITOR.md) | Monitor SNTP edge, alarmas, HMI — **implementado v1.0** ([AUDIT_NTP_TIME_SYNC](../audits/AUDIT_NTP_TIME_SYNC.md)) |
| **04** | [04-HMI-SOCKET-TRACEABILITY.md](./04-HMI-SOCKET-TRACEABILITY.md) | Sesiones HMI en PG, fail-closed, TLS/IP — **implementado** ([AUDIT_HMI_SOCKET_TRACEABILITY](../audits/AUDIT_HMI_SOCKET_TRACEABILITY.md)) |
| **05** | [05-NODE-PERFORMANCE-DASHBOARD.md](./05-NODE-PERFORMANCE-DASHBOARD.md) | Dashboard de rendimiento del nodo O(1) — **implementado P0+P1** ([AUDIT_NODE_PERFORMANCE_DASHBOARD](../audits/AUDIT_NODE_PERFORMANCE_DASHBOARD.md)) |
| **06** | [06-PERFORMANCE-ALARMS.md](./06-PERFORMANCE-ALARMS.md) | Alarmas ISA-18.2 de rendimiento; dashboard + Alarmas + Settings — **implementado** ([AUDIT_NODE_PERFORMANCE_DASHBOARD](../audits/AUDIT_NODE_PERFORMANCE_DASHBOARD.md)) |
| **07** | [07-PERFORMANCE-DASHBOARD-UI.md](./07-PERFORMANCE-DASHBOARD-UI.md) | UI profesional `/performance`: gauges, umbrales en tarjeta, modales ISA-18.2 — **implementado** |
| **08** | [08-WAVELET-RPA-RT.md](./08-WAVELET-RPA-RT.md) | Filtro wavelet DWT por bloques, tag `.f`, calidad OPC en pipeline — **implementado** ([AUDIT_SIGNAL_CONDITIONING](../audits/AUDIT_SIGNAL_CONDITIONING.md)) |
| **09** | [09-OPC-QUALITY-AND-DEGRADED-STARTUP.md](./09-OPC-QUALITY-AND-DEGRADED-STARTUP.md) | Calidad OPC UA (StatusCode → CVT → alarmas), stale en disconnect, modo degradado BD — **implementado v1.0** ([AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP](../audits/AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md)) |
| **10** | [10-OPC-QUALITY-A-PLUS.md](./10-OPC-QUALITY-A-PLUS.md) | Calidad A+: `ALM.QUALITY.*`, `event_id` en Login, toggle UNCERTAIN, badge Trends — **implementado v2.0** (soak 24 h pendiente) |
| **11** | [11-CATALOG-SQLITE-LOCAL.md](./11-CATALOG-SQLITE-LOCAL.md) | Catálogo local SQLite espejo + sync bidireccional con PG/MySQL; multi-edge; sin SQLite en HMI central — **propuesta v1.3** |

---

## Documentación operativa (fuera de specs)

| Documento | Contenido |
|-----------|-----------|
| [Auditorías](../audits/) | Contrastes código vs. diseño (conexiones, SAF, multi-edge, calidad OPC) |

---

## Convenciones

- Numeración **01–NN**: un documento por dominio / capacidad.
- Título: `# Documento NN: …`
- Cabecera: versión, fecha, fuentes, autores, **Estado**, auditoría de contraste.
- Anclas internas: cada sección principal incluye `<a id="...">` para enlaces estables.
- Índice `§` al inicio de cada spec.
- Criterios de aceptación con IDs estables (`CA-…`).
- Estado de implementación: ver auditorías en `audits/`.
