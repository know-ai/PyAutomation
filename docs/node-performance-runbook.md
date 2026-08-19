# Runbook: dashboard de rendimiento del nodo

Vista operativa del edge en `HMI → Rendimiento del nodo` (`/performance`).
Solo roles **admin**, **supervisor** y **sudo**. Cada edge muestra **sus** métricas.

## Cómo leer el snapshot

El valor viene de `GET /api/health/node`. Es una copia del dict que escribe `MetricsSamplerWorker` cada 5 s (configurable con `AUTOMATION_METRICS_SAMPLE_INTERVAL_S`). Si **Snapshot age** supera ~15 s, el sampler se retrasó; si supera ~60 s, el worker no está actualizando.

## Umbrales recomendados y acciones

| Métrica | Warning | Crítico | Acción |
|---|---|---|---|
| CPU % | ≥ 70 | ≥ 90 | Revisar SM/OPC; no aumentar poll de `/health/system` |
| Disco usado % | ≥ 80 | ≥ 90 | Liberar journal SAF / logs rotados |
| 5xx / min | ≥ 1 | sostenido | Logs ERROR; no es el sampler (O(1) en GET /node) |
| Cola SAF | > 0 sostenida | backpressure | Historiador o red; ver `/api/health/saf` |
| NTP unsynced | warn offset | alarma BOOL | Runbook NTP |
| Clientes HMI | — | mismatch vs `hmi_sessions` | Socket rechazado / heartbeat |

## Qué no hacer

- No hacer poll de `/api/health/system` cada 1–3 s desde N clientes: ese endpoint **recalcula** OPC/PG/SAF.
- No reintroducir pool Peewee para “acelerar” métricas PG. Las consultas de txn/conexiones usan **throwaway psycopg2**.

## Multi-edge

Cada proceso tiene su propio sampler y su propia fila de `hmi_sessions` filtrada por `node_id`. Un dashboard en Linea1 no muestra CPU de Linea2.

## Alarmas de rendimiento (ISA-18.2)

Siete alarmas BOOL de sistema: CPU, disco, cola SAF, lag SAF, antigüedad del snapshot, conexiones PG y HTTP 5xx/min. Viven en el AlarmManager (`{área}.ALM.PERF.*`).

| Acción | Dónde |
|---|---|
| Ver estado y ack/shelve sin cambiar de contexto | Clic en la tarjeta del dashboard `/performance` |
| Vista consolidada | Página **Alarmas** (buscar `ALM.PERF` o descripción `System ·`) |
| Cambiar umbral / debounce | Engranaje en la tarjeta (admin/supervisor/sudo) o Settings → Alarmas de rendimiento. `PUT /api/settings/performance` recarga el evaluador **sin reiniciar** |

Debounce default: **3** ticks del sampler (~15 s a 5 s/tick). Color de la tarjeta: rojo = activa sin ack; ámbar = reconocida; gris = silenciada; verde = métrica OK.

No crear alarmas HI/LO paralelas sobre CPU: el tag BOOL es la única fuente. No hacer poll extra; Socket `on.alarm` actualiza Redux.

