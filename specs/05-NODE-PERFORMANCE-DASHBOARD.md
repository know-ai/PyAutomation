# Documento 05: Dashboard de rendimiento del nodo

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 2026-08-19 |
| **Estado** | Implementado (P0 + P1 + P2 txn/min). Soak 24 h pendiente. |
| **Auditoría** | [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](../audits/AUDIT_NODE_PERFORMANCE_DASHBOARD.md) |
| **Runbook** | [docs/node-performance-runbook.md](../docs/node-performance-runbook.md) |

## Alcance

Pantalla de rendimiento por edge: CPU, RAM, disco, HTTP, HMI, BD, SAF y adquisición en tiempo real, **sin degradar el hot path**. El poll HTTP es O(1) (copia de un dict precomputado).

## Componentes

| Pieza | Ruta |
|---|---|
| Contadores HTTP O(1) | `automation/utils/http_metrics.py` |
| Worker muestreador | `automation/workers/metrics_sampler.py` |
| API | `GET /api/health/node` (auth admin/supervisor/sudo) |
| Health full (sin regresión) | `GET /api/health/system` |
| HMI | `/performance` — `Performance.tsx`, sparklines canvas |
| Arranque | `PyAutomation.__start_workers` / `__stop_workers` |

## Variables de entorno

`AUTOMATION_METRICS_SAMPLE_INTERVAL_S` — intervalo del sampler (default 5, rango 5–30).

## Contrato de poll

| Cliente | Intervalo |
|---|---|
| HMI en foco | 3 s |
| HMI `document.hidden` | 30 s |
| Sampler | 5 s (configurable) |
| `GET /health/node` | lectura de dict, `Cache-Control: max-age=1` |

## Criterios de aceptación

CA-NPD-01 … CA-NPD-15. Evidencia en la [auditoría §4](../audits/AUDIT_NODE_PERFORMANCE_DASHBOARD.md).

Alarmas ISA-18.2 del nodo: [06-PERFORMANCE-ALARMS.md](./06-PERFORMANCE-ALARMS.md) (CA-PERF-09…14).

## Multi-edge

Cada nodo muestrea **sus** métricas. `HMI_ACTIVE_CLIENTS` filtra `hmi_sessions` por `node_id`. Ver [docs/multi-edge.md](../docs/multi-edge.md).
