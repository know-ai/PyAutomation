# Documento 07: Dashboard de rendimiento — UI profesional con umbrales integrados

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 3.0 |
| **Fecha** | 2026-08-19 |
| **Estado** | Implementado (fuente HMI) |
| **Alcance** | Refactor de `/performance`. No modifica evaluación ni muestreo del backend. |
| **Auditoría** | [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](../audits/AUDIT_NODE_PERFORMANCE_DASHBOARD.md) |
| **Depende de** | [05](./05-NODE-PERFORMANCE-DASHBOARD.md) · [06](./06-PERFORMANCE-ALARMS.md) |

## Premisas

- Las alarmas ya existen (tags BOOL + AlarmManager).
- Los umbrales se persisten en `app_config.json` y se aplican en caliente (`PUT /api/settings/performance` → `reconfigure()`).
- El dashboard es responsivo (≥ 1024×768), accesible y bilingüe ES/EN.

## Métricas alarmables

| Métrica | Alarma | Unidad | Default |
|---|---|---|---|
| CPU | `ALM.PERF.CPU` | % | 85 |
| Disco | `ALM.PERF.DISK` | % | 90 |
| Cola SAF | `ALM.PERF.SAF_QUEUE` | filas | 5000 |
| Lag SAF | `ALM.PERF.SAF_LAG` | ms | 10000 |
| HTTP 5xx | `ALM.PERF.HTTP_5XX` | /min | 5 |
| Conexiones DB | `ALM.PERF.DB_CONN` | conexiones | 10 |
| Edad del snapshot | `ALM.PERF.METRICS_AGE` | ms | 30000 |

RSS, NTP, clientes HMI, txn/min, CVT y OPC son **informativas** (icono ℹ️).

## Estados de tarjeta

| Estado | Tono CSS | Indicador |
|---|---|---|
| Normal | `--ok` | punto verde + OK |
| Activa no ack | `--error` | punto rojo parpadeante + ACTIVA |
| Ack | `--warn` | punto ámbar + ACK |
| Shelved | `--shelved` | punto gris + SILENCIADA |

## Piezas HMI

| Pieza | Ruta |
|---|---|
| Página | `hmi/src/pages/Performance.tsx` |
| Gauge / tile | `hmi/src/components/MetricTile.tsx` |
| Paneles de subsistema | `hmi/src/components/PerfPanel.tsx` |
| Modal ISA-18.2 | `hmi/src/components/PerformanceAlarmModal.tsx` |
| Modal umbral | `hmi/src/components/PerformanceThresholdModal.tsx` |
| Contrato visual | `hmi/src/services/performanceAlarms.ts` |

## Criterios

| ID | Criterio |
|---|---|
| CA-UI-06 | Tarjeta alarmable: indicador verde/ámbar/rojo/gris y umbral visible |
| CA-UI-07 | Engranaje abre modal de umbral / debounce / habilitado |
| CA-UI-08 | Tras guardar, el catálogo se recarga; el sampler aplica en &lt; 1 ciclo |
| CA-UI-09 | Modal de alarma: Ack, Shelve 1 h, Unshelve, Configurar |
| CA-UI-10 | Layout usable en 1024×768 y superior (5 gauges / 3 paneles ≥ 1024 px) |
