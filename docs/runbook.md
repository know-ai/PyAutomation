# Runbooks operativos

Índice de procedimientos de planta. Las auditorías en `audits/` contrastan código; estos documentos dicen qué hacer ante una alerta.

| Tema | Documento |
|---|---|
| Dashboard de rendimiento del nodo | [node-performance-runbook.md](./node-performance-runbook.md) (incluye alarmas ISA-18.2) |
| NTP / reloj de edge | [ntp-deployment.md](./ntp-deployment.md) |
| Calidad OPC UA y modo degradado | [opc-quality-runbook.md](./opc-quality-runbook.md) |
| Catálogo local SQLite | [catalog-sqlite.md](./catalog-sqlite.md) (feature) · [catalog-sqlite-runbook.md](./catalog-sqlite-runbook.md) (operación) |
| Arquitectura multi-edge | [multi-edge.md](./multi-edge.md) |
| Deriva RSS / hot path / SAF | [AUDIT_PERFORMANCE.md](../audits/AUDIT_PERFORMANCE.md) (sección Runbook) |
| Poll de métricas | Dashboard `/performance` usa `GET /api/health/node` (copia O(1) del sampler). No poll frecuente de `/health/system`. Intervalo: `AUTOMATION_METRICS_SAMPLE_INTERVAL_S` (5–30 s, default 5). |
