# Documento 06: Gestión unificada de alarmas de rendimiento

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 2026-08-19 |
| **Estado** | Implementado (P0 + P1) |
| **Auditoría** | [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](../audits/AUDIT_NODE_PERFORMANCE_DASHBOARD.md) |
| **Runbook** | [docs/node-performance-runbook.md](../docs/node-performance-runbook.md) |

## Alcance

Alarmas ISA-18.2 de rendimiento del nodo (CPU, disco, SAF, HTTP 5xx, conexiones BD, antigüedad del snapshot). Una sola fuente de verdad: tag BOOL + AlarmManager. El operador actúa desde el dashboard **o** desde la página de Alarmas.

## Componentes

| Pieza | Ruta |
|---|---|
| Catálogo + ensure BOOL | `automation/utils/performance_alarms.py` |
| Config (app_config / env) | `automation/utils/performance_alarm_config.py` |
| Evaluador debounce | `automation/utils/perf_alarm_evaluator.py` |
| Sampler | `MetricsSamplerWorker._sample_perf_alarms` + `reconfigure()` |
| API umbrales | `GET/PUT /api/settings/performance` |
| Unshelve HTTP | `POST /api/alarms/unshelve/<name>` (usa `Alarm.unshelve`) |
| HMI dashboard | `MetricTile`, `PerfPanel`, `PerformanceAlarmModal`, `PerformanceThresholdModal` |
| HMI settings | `PerformanceAlarmConfig` (admin/supervisor/sudo) |
| Tests | `automation/tests/test_performance_alarms.py` |

## Alarmas

| Key | Tag | Alarma | Campo snapshot | Default |
|---|---|---|---|---|
| cpu | `SYS.PERF.CPU` | `ALM.PERF.CPU` | `HOST_CPU_PERCENT` | ≥ 85 % |
| disk | `SYS.PERF.DISK` | `ALM.PERF.DISK` | `HOST_DISK_USED_PERCENT` | ≥ 90 % |
| saf_queue | `SYS.PERF.SAF_QUEUE` | `ALM.PERF.SAF_QUEUE` | `SAF_QUEUE_DEPTH` | ≥ 5000 |
| saf_lag | `SYS.PERF.SAF_LAG` | `ALM.PERF.SAF_LAG` | `SAF_REPLICATION_LAG_MS` | ≥ 10000 ms |
| metrics_age | `SYS.PERF.METRICS_AGE` | `ALM.PERF.METRICS_AGE` | `METRICS_AGE_MS` | ≥ 30000 ms |
| db_conn | `SYS.PERF.DB_CONN` | `ALM.PERF.DB_CONN` | `DB_ACTIVE_CONNECTIONS` | ≥ 10 |
| http_5xx | `SYS.PERF.HTTP_5XX` | `ALM.PERF.HTTP_5XX` | `HTTP_5XX_1M` | ≥ 5 / min |

Nombres cualificados con área en multi-edge (`Linea1.ALM.PERF.CPU`). Descripción: `System · …`. Eventos de transición: classification **System**.

## Contrato

- Debounce: N muestras consecutivas (default 3) para **activar**; retorno a normal **inmediato**.
- PUT umbrales → `metrics_worker.reconfigure()` en el mismo ciclo (sin restart).
- GET `/health/node` sigue siendo O(1); el evaluador corre **solo** en el sampler.
- Ack / shelve / unshelve: endpoints de alarmas existentes + Redux `alarmsSlice` / Socket `on.alarm`.
- Catálogo `SYS.PERF.*` en tabla `Tags` del historiador: `ensure_performance_alarms()` al conectar/reconectar y reintento en el sampler hasta persistir (CA-SAF-TAGS-01…03).

## Criterios

CA-PERF-09 … CA-PERF-14. UI profesional: CA-UI-06 … CA-UI-10 ([spec 07](./07-PERFORMANCE-DASHBOARD-UI.md)). Catálogo historiador: CA-SAF-TAGS-01…03. Evidencia en la auditoría.
