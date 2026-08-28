# SOAK disco / SAF — plantilla de campaña

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO + iDetectFugas |
| **Alcance** | 24 h (ideal 5 días) con outage PostgreSQL 4 h |
| **Estado** | **Pendiente de ejecución en planta** (G-DISK-08) |
| **Fecha de esta plantilla** | 2026-08-28 |
| **Runbook** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) §4.3 · iDetectFugas `06-AUDIT_PERFORMANCE.md` Parte B |

Esta campaña **no se simula en CI**. Rellenar la tabla tras una corrida real y enlazarla desde [AUDIT_DISK_DURABILITY.md](./AUDIT_DISK_DURABILITY.md).

## Cómo ejecutar

```bash
# Backend 24 h (framework)
PERF_SOAK_SECONDS=86400 python -m unittest automation.tests.test_performance_soak

# SAF apocalypse (opcional, más corto)
SAF_SOAK_SECONDS=1800 SAF_SOAK_TAGS=1000 SAF_SOAK_HZ=100 \
  python -m unittest automation.tests.test_store_and_forward.TestT01Apocalypse
```

En lab 2-edge: dejar ambos nodos 24 h, cortar PG 4 h, restaurar, confirmar `SAF_QUEUE_DEPTH → 0`.

## Resultados (rellenar)

| Métrica | Resultado | Umbral | OK |
|---|---|---|---|
| Fecha / operator | _pendiente_ | — | ☐ |
| Duración | | ≥ 24 h | ☐ |
| RSS_MB | | ±10 % vs baseline | ☐ |
| SAF_QUEUE_DEPTH (régimen) | | < 1000 | ☐ |
| Outage PG 4 h — cola pico | | < cap 5e6 | ☐ |
| Outage PG 4 h — drenaje post-ACK | | cola → 0 | ☐ |
| `JournalDiskFullError` | no debe aparecer si disco ≥ 256 GB | 0 | ☐ |
| HOST_DISK_USED_PERCENT | | < 85 % | ☐ |
| HOST_SSD_WEAR_PERCENT / TEMP | | < warn | ☐ |
| OPC_MONITORED_COUNT | | constante | ☐ |
| Exact-once post-replay | | sin duplicados TagValue | ☐ |

## Evidencia

Adjuntar: `GET /api/health/node` T0/T24, `/api/health/saf`, Events `Disk usage critical` / `SSD SMART` (no deben disparar), logs gunicorn.

Última corrida T-01 (SIGKILL, no 24 h): [T01_SOAK_LAST_RUN.md](./T01_SOAK_LAST_RUN.md).
