# CHAOS — última campaña de laboratorio

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO + iDetectFugas |
| **Estado** | **Pendiente de ejecución en planta / lab OT** |
| **Fecha de esta plantilla** | 2026-08-28 |
| **Runbook** | [docs/CHAOS_TESTING.md](../docs/CHAOS_TESTING.md) |

Esta campaña **no se simula en CI**. Rellenar tras C-01…C-05 reales. Los unitarios (T-01, disco lleno, gate NTP, heartbeat de nodos) viven en `automation/tests/` y no sustituyen esta tabla.

## Resultados (rellenar)

| Campaña | Fecha / operador | RPO | RTO medido | OK |
|---|---|---|---|---|
| C-01 SIGKILL / T-01 | _pendiente_ | 0 samples perdidos | replay inmediato | ☐ |
| C-02 PG down | | cola drena a 0 | | ☐ |
| C-03 Disco lleno | | sin WAL corrupto | | ☐ |
| C-04 Edge down | | 0 writes cruzados | `ALM.PERF.NODE_DOWN` ≤ 105 s | ☐ |
| C-05 NTP > 1 s | | PENDING conservado | réplica bloqueada | ☐ |

## Objetivos de contrato

| Métrica | Objetivo | Medido |
|---|---|---|
| RPO energía | 0 | |
| RTO contenedor | ≤ `_restart_eta_s` (~30 s overlay; LGBM en background) | |
| RTO detección par caído | ≤ 90 s + debounce | |
| Steal-tags A→B | **no aplica** (diseño) | n/a |

## Evidencia

Adjuntar: `GET /api/health/node` de ambos edges, Events `NTP` / `NODE_DOWN`, logs gunicorn, T-01 [T01_SOAK_LAST_RUN.md](./T01_SOAK_LAST_RUN.md).

Última corrida T-01 automatizada (no lab OT): ver `T01_SOAK_LAST_RUN.md`.
