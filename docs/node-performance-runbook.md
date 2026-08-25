# Runbook: dashboard de rendimiento del nodo

Vista operativa del edge en `HMI → Rendimiento del nodo` (`/performance`).
Cualquier rol autenticado **excepto guest** ve métricas. Las acciones de control
están reservadas a **admin / supervisor / sudo**; vaciar cola SAF y limpiar huérfanos
solo **admin / sudo**.

## Cómo leer el snapshot

El valor viene de `GET /api/health/node`. Es una copia del dict que escribe `MetricsSamplerWorker` cada 5 s (configurable con `AUTOMATION_METRICS_SAMPLE_INTERVAL_S`). Si **Snapshot age** supera ~15 s, el sampler se retrasó; si supera ~60 s, el worker no está actualizando. El HMI hace poll cada **3 s** (30 s si la pestaña está oculta).

## Umbrales recomendados y acciones

| Métrica | Warning | Crítico | Acción |
|---|---|---|---|
| CPU % | ≥ 70 | ≥ 90 | Revisar SM/OPC; no aumentar poll de `/health/system` |
| Disco usado % | ≥ 80 | ≥ 90 | Liberar journal SAF / logs rotados |
| 5xx / min | ≥ 1 | sostenido | Logs ERROR; no es el sampler (O(1) en GET /node) |
| Cola SAF | > 0 sostenida | backpressure | Historiador o red; ver `/api/health/saf`. Si > 1000, **Forzar replicación**. Si > 5000 y admin, **Vaciar cola** solo como último recurso |
| Filas huérfanas de catálogo | > 0 | sync atascado | **Forzar sincronización**; si persisten, **Limpiar huérfanos** (admin) |
| Worker inactivo / error | amarillo/rojo | ciclo detenido | **Reiniciar** el worker afectado |
| NTP unsynced | warn offset | alarma BOOL | Runbook NTP |
| Clientes HMI | — | mismatch vs `hmi_sessions` | Socket rechazado / heartbeat |

## Controles en caliente (misma vista)

Los botones **no** aparecen para `operator`. Acciones de bajo riesgo (forzar réplica / sync) no piden confirmación y el botón queda 30 s en cooldown. Acciones destructivas piden modal.

| Acción | Quién | Cuándo se muestra | Endpoint | Confirmación | Riesgo |
|---|---|---|---|---|---|
| Reiniciar worker (`LoggerWorker`, `CatalogReplicator`, `MetricsSampler`) | admin / supervisor / sudo | Siempre | `POST /api/admin/workers/restart?name=…` | Modal: breve interrupción de réplica | Medio |
| Forzar replicación SAF | admin / supervisor / sudo | `SAF_QUEUE_DEPTH > 1000` | `POST /api/admin/saf/retry` | No | Bajo |
| Vaciar cola SAF | **admin / sudo** | `SAF_QUEUE_DEPTH > 5000` | `POST /api/admin/saf/reset` `{confirm: true}` | Checkbox + escribir `CONFIRMAR` | **Crítico** — descarta PENDING |
| Forzar sync de catálogo | admin / supervisor / sudo | Siempre | `POST /api/admin/catalog/sync` | No | Bajo |
| Limpiar huérfanos | **admin / sudo** | `CATALOG_ORPHAN_ROWS > 0` | `POST /api/admin/catalog/clean-orphans` `{age_minutes}` | Checkbox + edad 5/10/30/60 min | Medio |
| Reconstruir tags `.f` | admin / supervisor / sudo | Siempre | `POST /api/admin/tags/rebuild-derived` | Modal | Medio |

Todas las acciones quedan en **Events** (`classification=System`) con usuario, timestamp y razón. Criticity 2 (bajo), 3 (medio) o 5 (vaciar SAF). El panel no se bloquea: restart responde 202 y el estado pasa a **Reiniciando…** hasta el siguiente poll.

**Vaciar cola SAF** es pérdida de histórico pendiente. Usar solo si el journal está irrecuperable y se acepta el hueco. El hot path sigue tratando PENDING como sagrado; este endpoint es el único discard intencional.

## Qué no hacer

- No hacer poll de `/api/health/system` cada 1–3 s desde N clientes: ese endpoint **recalcula** OPC/PG/SAF.
- No reintroducir pool Peewee para “acelerar” métricas PG. Las consultas de txn/conexiones usan **throwaway psycopg2**.
- No vaciar SAF para “acelerar” una cola que aún puede drenar. Primero forzar replicación y revisar el historiador.
- No limpiar huérfanos de catálogo con edad 5 min si el padre remoto todavía está llegando.

## Multi-edge

Cada proceso tiene su propio sampler, journal y workers. Un dashboard en Linea1 no muestra CPU ni colas de Linea2. Las acciones admin aplican **solo a ese edge**.

## Alarmas de rendimiento (ISA-18.2)

Siete alarmas BOOL de sistema: CPU, disco, cola SAF, lag SAF, antigüedad del snapshot, conexiones PG y HTTP 5xx/min. Viven en el AlarmManager (`{área}.ALM.PERF.*`).

| Acción | Dónde |
|---|---|
| Ver estado y ack/shelve sin cambiar de contexto | Clic en la tarjeta del dashboard `/performance` |
| Vista consolidada | Página **Alarmas** (buscar `ALM.PERF` o descripción `System ·`) |
| Cambiar umbral / debounce | Engranaje en la tarjeta (admin/supervisor/sudo) o Settings → Alarmas de rendimiento. `PUT /api/settings/performance` recarga el evaluador **sin reiniciar** |

Debounce default: **3** ticks del sampler (~15 s a 5 s/tick). Color de la tarjeta: rojo = activa sin ack; ámbar = reconocida; gris = silenciada; verde = métrica OK.

No crear alarmas HI/LO paralelas sobre CPU: el tag BOOL es la única fuente. No hacer poll extra; Socket `on.alarm` actualiza Redux.
