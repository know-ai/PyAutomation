# Runbook de deriva de rendimiento — Operación «Engranaje Perfecto»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO + HMI |
| **Alcance** | Detectar y corregir degradación 24/7 (RSS, handles OPC, colas SAF, heap HMI) |
| **Fecha** | 2026-08-13 (actualizado: incidente + reversión BE-H4) |

## 1. Señales y umbrales

Fuente backend: `GET /api/health/system` y `GET /api/health/saf`.

| Métrica | Umbral | Acción |
|---|---|---|
| `RSS_MB` | +20 % en 24 h vs baseline | Soak + `tracemalloc`; revisar observers/alarmas/DAS |
| `OPC_MONITORED_COUNT` | Crecimiento sin cambio de config | Verificar `DAS.reset_client` en reconnect; una subscription por cliente |
| `SAF_QUEUE_DEPTH` / `PENDING_ROWS` | > 10 000 sostenido | Historiador caído o replicador lento; no borrar PENDING |
| `SAF_PENDING_CAP_HITS` | Cualquier incremento | Backpressure a 5e6 filas; restaurar PG |
| `ALARM_COUNT` | Salto inexplicable | Reload duplicando alarmas / attach no idempotente |
| `POOL_CONNECTIONS_USED` | N/A (sin pool Peewee) | Si vuelve a >0 tras reintroducir pool: ver §5.1 |
| `CVT_LOCK_CONTENTION` | Crecimiento monotónico alto | Contención en `Tag._lock`; revisar tasa de `set_value` |
| `LOG_ERROR_RATE_PER_MIN` | **> 5** | Error recurrente (aunque el dedupe silencie el archivo). Ver `logs/app.log` y SM |
| `LOG_ERROR_ALERT` | `true` | Misma señal; no hace falta leer miles de líneas |
| Heap HMI | > 512 MB (`useMemoryWatchdog`) | Toast + `POST /logs/add`; revisar StripCharts y Redux |
| Socket listeners | `window.__pyaSocketListeners()` (DEV) | Debe ser 1 nativo / evento; callbacks = páginas montadas |
| Long task Trends RT | > 50 ms (`PerformanceObserver`) | Throttle Plotly / menos charts visibles |

Alertas Prometheus (orquestador):

```
# RSS deriva
(pya_rss_mb / pya_rss_mb offset 24h) > 1.20
# OPC handles
delta(pya_opc_monitored_count[1h]) > 0  AND  config_hash unchanged
# SAF
pya_saf_queue_depth > 10000 for 15m
# Logs (intentos ERROR, incluye suprimidos por dedupe)
pya_log_error_rate_per_min > 5
```

## 2. Procedimiento de diagnóstico

1. Capturar `/api/health/system` y `/api/health/saf` (T0).
2. Comparar con baseline de arranque (mismo worker gunicorn).
3. Si `OPC_MONITORED_COUNT` crece: dump `DAS.monitored_items` keys; confirmar `nodeid.to_string()`.
4. Si `PENDING_ROWS` crece: `SAF_REPLICATION_LAG`, circuit breaker, conectividad PG.
5. Si RSS crece y OPC/SAF planos: `tracemalloc` (ver §3) — buscar `Tag`, `Alarm`, `Buffer`.
6. HMI: DevTools Memory + `performance.memory`; navegación ×500 y `socket.listeners("on.tag").length`.
7. Si signup/login hacen timeout en HMI pero el arranque y `/health/db` parecen OK: mirar duración del POST en `logs/app.log` (~30 s + 503) → §5.1 (pool / gevent), no asumir “BD caída”.

## 3. tracemalloc (backend)

```bash
PERF_SOAK_SECONDS=86400 python -m unittest automation.tests.test_performance_soak
```

En planta, arrancar el worker con `tracemalloc.start()` al boot y comparar snapshots T+0 vs T+24h filtrando tipos `Tag`, `Alarm`, `Buffer`.

## 4. Soak operativo

| Prueba | Carga | Éxito |
|---|---|---|
| Backend 24 h / 7 d | 100 tags @ 10 Hz; reconnect OPC cada 5 min; outage PG 4 h | RSS ±15 %; `OPC_MONITORED_COUNT` plano; cola SAF baja a 0 tras PG |
| HMI 24 h | 8 StripCharts + 500 cambios de ruta | Heap < 512 MB; listeners nativos constantes |

## 5. Corrección típica

| Síntoma | Causa probable | Fix |
|---|---|---|
| RSS + handles OPC | Re-subscribe sin unsubscribe | `DAS.subscribe` por namespace + `reset_client` |
| CPU alarmas | Scan O(n) | Índices `_by_name` / `_by_tag_name` |
| Disco SAF | Outage largo | Cap 5e6 + alerta; no borrar PENDING |
| Footer lento | Hidratar 10k alarmas | Preview de 3 (`selectActiveAlarmsPreview`) |
| Charts acoplados | Selector global `tagHistory` | Selector por `tagNames` + throttle 300 ms |
| Heap HMI | Historial 10k / listeners huérfanos | 720 pts + EventBus; logout limpia slices |
| Signup/login timeout 15 s / 503 @ ~30 s | Pool Peewee + gevent sin `close()` | Ver §5.1 — **no** reintroducir pool a ciegas |

### 5.1 Incidente BE-H4 (2026-08-13) — pool PG bajo gevent

**Contexto:** Engranaje Perfecto introdujo `PooledPostgresqlDatabase(max_connections=8, timeout=30)` en `PyAutomation.set_db`.

**Evidencia en planta (idetectfugas):**

```
POST /api/users/signup HTTP/1.1" 503 … 30.196218
```

HMI: `timeout of 15000ms exceeded`. Arranque y carga de tags/alarmas OK; PostgreSQL alcanzable.

**Causa:** gunicorn `GeventWebSocketWorker` + greenlets/hilos retienen conexiones del pool Peewee (una por greenlet) porque el proceso no hace `db.close()` al terminar cada request. Al llenar 8 slots, el checkout espera `timeout=30` → error → API signup/login responde **503**. Axios corta a 15 s.

**Mitigación aplicada:** revertir a `PostgresqlDatabase` en `automation/core.py` (`set_db`). Rebuild wheel + reinstalar en el venv de planta + reiniciar gunicorn.

**Prohibido hasta nuevo diseño:** volver a `PooledPostgresqlDatabase` sin:

1. `before_request` / `teardown_request` (o middleware) con `connect` / `close`.
2. Prueba de carga: N signup/login concurrentes bajo el mismo worker gevent.
3. Confirmación de que `_in_use` no crece monotónicamente.

Detalle de auditoría: `audits/AUDIT_BACKEND_PERFORMANCE.md` §3.2 BE-H4.

---

## 6. Gestión de logs, stdout y retención (Operación «Log Eterno»)

Complementa: `audits/AUDIT_LOGGING.md`.

### 6.1 Runtime (`logs/app.log`)

- `RotatingFileHandler`: techo `log_max_bytes × (1 + log_backup_count)` (default **≤ 40 MiB**).
- Dedupe ERROR: `log_error_cooldown_seconds` (default **60**; `0` = off). Un error a 1 Hz → **1 línea/min** en archivo y stdout.
- `@logging_error_handler` **no** hace `print`; stdout ERROR pasa por `StreamHandler` con el mismo filtro (una decisión por record, no por handler).
- Caliente: `PUT /api/settings/update` con `log_error_cooldown_seconds`, `log_max_bytes`+`log_backup_count`, `log_level`.

### 6.2 Stdout / Docker / gunicorn (LOG-H3)

El framework **no** rota el journal del contenedor. Configurar el driver de logging del orquestador:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Compose:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

Si se usa systemd/journald, acotar `SystemMaxUse` / `RuntimeMaxUse`. Gunicorn access log: redirigir a journald o rotar con logrotate; no duplicar a un archivo sin techo.

### 6.3 Backups SQLite locales (LOG-H4)

`LoggerWorker` hace `VACUUM INTO db/backups/` cuando el historian SQLite local supera **1 GiB**. El framework **no** borra esos archivos (datos de durabilidad).

Política sugerida (ops, no código de producto):

```bash
# Conservar 14 días
find ./db/backups -name '*.db' -mtime +14 -delete
find ./db/backups -name '*.sha256' -mtime +14 -delete
```

### 6.4 Tablas PostgreSQL (LOG-H5)

`Logs`, `Events`, `TagValue`, `AlarmSummary` **no** tienen TTL en el framework. Retención = DBA/planta (particiones por mes + `DROP`/`DETACH` de particiones antiguas, o job de archive). No implementar `DELETE` masivo desde la app.

### 6.4 Soak de error controlado

Inyectar un `AttributeError` repetido en un `while_*` de prueba 24 h:

- `du -sb logs/` ≤ `maxBytes * (1+backup) * 1.1`
- `LOG_ERROR_RATE_PER_MIN` ≈ 60 (intentos) y `LOG_ERROR_SUPPRESSED_PER_MIN` ≈ 59
- `LOG_ERROR_ALERT=true`
- CPU del worker sin picos atribuibles a I/O de log

