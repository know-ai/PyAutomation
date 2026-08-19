# Especificaciones PyAutomationIO

Índice maestro de especificaciones técnicas de PyAutomationIO (`automation/`).

**Estructura actual (v1.0, 2026-08-19):** **3 documentos temáticos** en la raíz de `specs/`.

---

## Índice de documentos

| Doc | Archivo | Contenido |
|-----|---------|-----------|
| **01** | [01-MULTI-EDGE-ARCHITECTURE.md](./01-MULTI-EDGE-ARCHITECTURE.md) | Adquisición multi-edge, partición por área ISA-95, hidratación acotada, single-writer — **propuesta v1.0** ([AUDIT_MULTI_EDGE](../audits/AUDIT_MULTI_EDGE.md)) |
| **02** | [02-STATE-MACHINE-TEMPORAL-DECOUPLING.md](./02-STATE-MACHINE-TEMPORAL-DECOUPLING.md) | Tres relojes SM (adquisición / muestreo / ejecución) — **implementado v1.0** ([AUDIT_STATE_MACHINES](../audits/AUDIT_STATE_MACHINES.md)) |
| **03** | [03-NTP-EDGE-CLOCK-MONITOR.md](./03-NTP-EDGE-CLOCK-MONITOR.md) | Monitor SNTP edge, alarmas, HMI — **implementado v1.0** ([AUDIT_NTP_TIME_SYNC](../audits/AUDIT_NTP_TIME_SYNC.md)) |

---

## Documentación operativa (fuera de specs)

| Documento | Contenido |
|-----------|-----------|
| [Auditorías](../audits/) | Contrastes código vs. diseño (conexiones, SAF, multi-edge) |

---

## Convenciones

- Numeración **01–NN**: un documento por dominio / capacidad.
- Título: `# Documento NN: …`
- Cabecera: versión, fecha, fuentes, autores, **Estado**, auditoría de contraste.
- Anclas internas: cada sección principal incluye `<a id="...">` para enlaces estables.
- Índice `§` al inicio de cada spec.
- Criterios de aceptación con IDs estables (`CA-…`).
- Estado de implementación: ver auditorías en `audits/`.
