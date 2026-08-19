# Auditoría compacta: pantalla de performance del nodo (Node Performance Dashboard)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) |
| **Alcance** | Visibilidad en tiempo real del rendimiento por edge/nodo — sin degradar el hot path de adquisición ni el consumo del propio nodo al mostrar métricas |
| **Fecha** | 2026-08-19 (dashboard P0+P1 + alarmas ISA-18.2 + UI profesional spec 07) |
| **Spec** | [specs/05-NODE-PERFORMANCE-DASHBOARD.md](../specs/05-NODE-PERFORMANCE-DASHBOARD.md) v1.0 · [specs/06-PERFORMANCE-ALARMS.md](../specs/06-PERFORMANCE-ALARMS.md) v1.0 · [specs/07-PERFORMANCE-DASHBOARD-UI.md](../specs/07-PERFORMANCE-DASHBOARD-UI.md) v3.0 |
| **Runbook** | [docs/node-performance-runbook.md](../docs/node-performance-runbook.md) · índice [docs/runbook.md](../docs/runbook.md) |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) |
| **Veredicto vigente** | **A−** — Dashboard O(1) + alarmas ISA-18.2 + UI profesional en fuente. **A+** tras soak 24 h, prueba 2-edge y prueba manual de gauges/modales en planta (CA-UI-06…10, CA-PERF-09/10/13/14) |
| **Clasificación** | Auditoría operativa · observabilidad · dashboard edge |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-19) |
|---|---|
| ¿Existe una pantalla HMI para medir performance del nodo en tiempo real? | **Sí** — `/performance` (`Performance.tsx`), ítem sidebar speedometer, i18n `es`/`en`, roles **admin / supervisor / sudo** |
| ¿Hay API lista para alimentar ese dashboard sin matar el nodo? | **Sí** — `GET /api/health/node` copia un dict precomputado (`Cache-Control: max-age=1`). **`/health/system` no se tocó** — sigue recalculando OPC/PG/SAF; no usarlo para poll 3 s |
| ¿Clientes HMI visibles? | **Sí** — `HMI_ACTIVE_CLIENTS` = `count_sessions()` filtrado por `node_id` del edge local |
| ¿Contadores HTTP (req/min, 5xx, in-flight)? | **Sí** — `automation/utils/http_metrics.py` (lock + deque 60 s); middleware Flask con `teardown_request` anti-fuga |
| ¿RAM / CPU / disco del host? | **Sí** — `psutil` en el sampler (`HOST_CPU_PERCENT`, `HOST_RSS_MB`, `HOST_DISK_*`); fallback `resource`/`threading` si psutil falla |
| ¿Métricas BD (txn/min, conexiones)? | **Parcial A** — `DB_TXN_PER_MIN` vía `pg_stat_database` throwaway; `DB_ACTIVE_CONNECTIONS` en sampler; `DB_DISK_FREE_GB` siempre `null` (P2 opcional) |
| ¿Poll 3 s desde N HMIs es seguro? | **Diseño sí** — GET es O(1). Soak 10 clientes × 24 h **pendiente** (CA-NPD-02) |
| ¿El observador cuesta más que lo observado? | **No en el request path.** El coste vive en `MetricsSamplerWorker` (hilo daemon, default 5 s) |
| ¿Hay alarmas de rendimiento gestionables desde el dashboard y Alarmas? | **Sí** — 7 BOOL ISA-18.2 (`ALM.PERF.*`). Campana + umbral en tarjeta; clic → modal ack/shelve/unshelve; engranaje → umbral. Misma instancia en `/alarms`. |

### 0.1 Principio rector

> **El observador no puede costar más que lo observado.**

| Capa | Regla | Implementación |
|---|---|---|
| Hot path HTTP | O(1) por evento | `on_request()` / `on_response()` — incrementos bajo lock |
| Poll operador | O(1) por GET | `get_snapshot()` — `dict()` + `METRICS_AGE_MS` |
| Muestreo | Coste acotado, fuera del poll | `MetricsSamplerWorker` — psutil, COUNT(*), 1–2 queries throwaway |
| HMI | Pausa en background | `usePerformancePoll` — 3 s foco / 30 s `document.hidden` |

### 0.2 Evolución del veredicto

| Fecha | Estado | Resumen |
|---|---|---|
| 2026-08-19 (mañana) | **D** | Sin pantalla `/performance`; `/health/system` costoso; sin contadores HTTP ni CPU/disco host |
| 2026-08-19 (tarde) | **A−** | P0+P1+P2 txn/min en código; 14 unit tests OK; HMI y docs en fuente; soak planta pendiente |
| 2026-08-19 (alarmas) | **A−** | Alarmas ISA-18.2 unificadas; evaluador debounce; Settings hot-reload; modal HMI; 13 tests CA-PERF |
| 2026-08-19 (UI v3.0) | **A−** | Spec 07: gauges, paneles, umbral en tarjeta, modal de configuración; CA-UI-06…10 en código fuente (build HMI pendiente en este host) |

---

## 1. Catálogo de métricas: antes vs ahora

### 1.1 Conectividad HMI / Socket

| Métrica | Antes (D) | Ahora (A−) | Fuente |
|---|---|---|---|
| Clientes HMI activos (global edge) | ❌ | ✅ `HMI_ACTIVE_CLIENTS` | `hmi_session_store.count_sessions()` |
| Edad del muestreo de sesiones | ❌ | ✅ `HMI_SESSIONS_SAMPLE_AGE_MS` | `_sample_hmi` |
| TLS / reconnect rate | ❌ | ❌ | Derivable de Events; fuera de alcance P0 |

### 1.2 HTTP / API REST

| Métrica | Antes | Ahora | Fuente |
|---|---|---|---|
| Requests totales | ❌ | ✅ `HTTP_REQUESTS_TOTAL` | `http_metrics.py` |
| Requests / min | ❌ | ✅ `HTTP_REQUESTS_1M` | deque 60 s |
| In-flight | ❌ | ✅ `HTTP_IN_FLIGHT` | before/after/teardown |
| 5xx total / min | ❌ | ✅ `HTTP_5XX_TOTAL` / `HTTP_5XX_1M` | idem |
| Latencia p50/p95 API | ❌ | ❌ (P2) | No implementado |

### 1.3 Host local

| Métrica | Antes | Ahora | Fuente |
|---|---|---|---|
| RSS | Solo en `/health/system` | ✅ `HOST_RSS_MB` | psutil / `resource` |
| CPU % | ❌ | ✅ `HOST_CPU_PERCENT` | psutil (primed al arranque) |
| Disco libre / usado | ❌ | ✅ `HOST_DISK_FREE_GB`, `HOST_DISK_USED_PERCENT` | `psutil.disk_usage('/')` |
| Hilos | Solo en `/health/system` | ✅ `HOST_THREADS` | psutil |

### 1.4 Historiador PostgreSQL

| Métrica | Antes | Ahora | Fuente |
|---|---|---|---|
| Conectado + latencia | ✅ `/health/db` (cache 1.5 s) | ✅ `DB_CONNECTED`, `DB_LATENCY_MS` | sampler + `DatabaseHealthService` |
| Conexiones activas PG | ✅ en `/health/system` (costoso) | ✅ `DB_ACTIVE_CONNECTIONS` | sampler (throwaway) |
| Sockets libpq locales | ✅ | ✅ `DB_CONNECTIONS_LOCAL` | `snapshot_connection_metrics` |
| Txn / min | ❌ | ✅ `DB_TXN_PER_MIN` | `query_pg_txn_counters` + delta |
| Disco servidor PG | ❌ | ❌ `DB_DISK_FREE_GB=null` | P2 opcional |

### 1.5 Adquisición, SAF, reloj

| Métrica | Antes | Ahora | Fuente |
|---|---|---|---|
| OPC / CVT / SM lag | ✅ `/health/system` | ✅ en snapshot | `_sample_acquisition` |
| SAF queue / lag / disco | ✅ `/health/saf` | ✅ `SAF_*` | `get_persistence_gateway().snapshot()` |
| NTP | ✅ bloque `clock` en system | ✅ `clock` en snapshot | `ntp_worker.get_status()` |
| `ACQUISITION_READY` | ✅ | ✅ | `app.acquisition_ready` |

---

## 2. Arquitectura implementada

```
┌─────────────────────────────────────────────────────────────────┐
│  HOT PATH — O(1) por evento                                    │
│  • Flask before_request → on_request()                           │
│  • after_request + teardown_request → on_response()             │
│  • (existente) CVT, SAF, OPC ya tienen contadores O(1)           │
└───────────────────────────┬─────────────────────────────────────┘
                            │ cada tick (default 5 s, clamp 5–30)
┌───────────────────────────▼─────────────────────────────────────┐
│  MetricsSamplerWorker (hilo daemon, BaseWorker)                  │
│  • psutil: CPU, RSS, disk, threads                               │
│  • count_sessions(node_id)                                       │
│  • pg_stat_database (txn/min) + pg_stat_activity (throwaway)    │
│  • gateway SAF, timing SM, NTP status                            │
│  • http_metrics.snapshot()                                       │
│  • _publish → dict merge (conserva último valor si sub-muestra │
│    falla o devuelve None)                                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ lectura O(1)
┌───────────────────────────▼─────────────────────────────────────┐
│  GET /api/health/node                                            │
│  • node_metrics_payload() → worker.get_snapshot()                │
│  • @token_required + @auth_roles admin|supervisor|sudo           │
│  • Cache-Control: max-age=1                                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ poll 3 s (30 s si document.hidden)
┌───────────────────────────▼─────────────────────────────────────┐
│  HMI /performance                                                │
│  • Tarjetas por sección + Sparkline canvas (60 pts, sin Plotly)  │
│  • Umbrales visuales ok/warn/error (CPU, disco, age, 5xx, SAF)  │
└─────────────────────────────────────────────────────────────────┘
```

**Orden de arranque** (`core.py`): BD conectada → `NtpMonitorWorker` → `HmiSessionCleanupWorker` → **`MetricsSamplerWorker`**. Parada simétrica en `__stop_workers`.

**Variable de entorno:** `AUTOMATION_METRICS_SAMPLE_INTERVAL_S` (default 5, rango 5–30).

---

## 3. Inventario de código (evidencia 2026-08-19)

### 3.1 Backend

| Artefacto | Estado | Notas |
|---|---|---|
| `automation/utils/http_metrics.py` | ✅ | Lock + deque; `install_http_metrics`; flag `g._pya_http_open` |
| `automation/workers/metrics_sampler.py` | ✅ | `MetricsSamplerWorker`; `_publish` last-value-on-fault |
| `automation/utils/db_connections.py` | ✅ | `query_pg_txn_counters` — psycopg2 throwaway, sin pool Peewee |
| `automation/modules/health/resources/health.py` | ✅ | `GET /health/node`; `node_metrics_payload()` |
| `GET /api/health/system` | ✅ sin regresión | Sigue recalculando en cada GET |
| `automation/core.py` | ✅ | `install_http_metrics(server)` + start/stop `metrics_worker` |
| `requirements.txt` | ✅ | `psutil==6.1.1` añadido (única dependencia nueva) |

Extracto endpoint O(1):

```65:90:automation/modules/health/resources/health.py
def node_metrics_payload():
    """O(1) copy of the sampler snapshot. Safe when the worker is not running."""
    worker = getattr(app, "metrics_worker", None)
    if worker is None or not hasattr(worker, "get_snapshot"):
        return {
            "status": "warming",
            "METRICS_AGE_MS": None,
            "message": "Metrics sampler is not running",
        }
    return worker.get_snapshot()


@ns.route("/node")
class HealthNodeResource(Resource):
    ...
    def get(self):
        """Read-only copy of the sampler dict. No historian, OPC or psutil on this path."""
        return node_metrics_payload(), 200, {"Cache-Control": "max-age=1"}
```

### 3.2 HMI

| Artefacto | Estado | Notas |
|---|---|---|
| `hmi/src/pages/Performance.tsx` | ✅ | 8 secciones: Identidad, Host, HTTP, HMI, BD, SAF, Adquisición, Reloj |
| `hmi/src/services/performance.ts` | ✅ | `getNodePerformance()`, `pollIntervalMs`, `pushRing`, `canViewPerformance` |
| `hmi/src/hooks/usePerformancePoll.ts` | ✅ | `visibilitychange` → re-arma intervalo |
| `hmi/src/components/Sparkline.tsx` | ✅ | Canvas 2D, sin Plotly |
| `hmi/src/routes/index.tsx` | ✅ | `<Route path="/performance" …>` activa |
| `hmi/src/layouts/Sidebar.tsx` | ✅ | Nav oculta si rol no autorizado |
| `hmi/src/styles/global.css` | ✅ | `.performance-page`, `.perf-grid`, `.perf-tile--ok/warn/error` |
| `hmi/src/locales/{es,en}.json` | ✅ | Bloque `performance` + `navigation.performance` |

Seguridad HMI: sin rol → `<Navigate to="/events" />`; API → 403 con JWT válido pero rol insuficiente.

### 3.3 Tests automatizados

Suite: `automation/tests/test_node_performance.py` — **14 tests, OK** (2026-08-19).

| Clase | Test | CA |
|---|---|---|
| `TestHttpMetrics` | `test_request_window_increments` | CA-NPD-04 |
| | `test_in_flight_tracks_open_requests` | — |
| | `test_flask_middleware_counts` | CA-NPD-04 |
| | `test_middleware_exception_does_not_leak_in_flight` | robustez HTTP |
| `TestMetricsSampler` | `test_sample_interval_clamped` | env clamp |
| | `test_get_snapshot_is_o1_copy` | CA-NPD-01 |
| | `test_get_snapshot_p95_under_5ms` | CA-NPD-01 |
| | `test_psutil_fields_when_available` | CA-NPD-05 |
| | `test_survives_db_outage` | CA-NPD-10 |
| | `test_hmi_active_clients_uses_store_count` | CA-NPD-03 |
| `TestHealthNodeEndpoint` | `test_node_endpoint_reads_snapshot_only` | CA-NPD-01 |
| | `test_system_endpoint_still_present` | CA-NPD-09 |
| | `test_sampler_does_not_use_peewee_pool` | CA-NPD-12 |
| | `test_hmi_poll_hidden_contract` | CA-NPD-08 |

Comando:

```bash
python -m unittest automation.tests.test_node_performance -q
```

---

## 4. Contrato del payload `GET /api/health/node`

Ejemplo representativo (~35 campos):

```json
{
  "status": "ok",
  "METRICS_AGE_MS": 420,
  "uptime_s": 86412,
  "NODE_ID": "edge-linea1",
  "NODE_AREA": "Linea1",
  "NODE_SITE": "Test",
  "MULTI_EDGE_ENABLED": true,

  "HOST_RSS_MB": 412.5,
  "HOST_CPU_PERCENT": 18.2,
  "HOST_DISK_FREE_GB": 42.1,
  "HOST_DISK_USED_PERCENT": 61.0,
  "HOST_THREADS": 24,

  "HTTP_REQUESTS_TOTAL": 184320,
  "HTTP_REQUESTS_1M": 38,
  "HTTP_5XX_TOTAL": 2,
  "HTTP_5XX_1M": 0,
  "HTTP_IN_FLIGHT": 1,

  "HMI_ACTIVE_CLIENTS": 3,
  "HMI_SESSIONS_SAMPLE_AGE_MS": 4.2,

  "DB_CONNECTED": true,
  "DB_LATENCY_MS": 4.1,
  "DB_ACTIVE_CONNECTIONS": 5,
  "DB_CONNECTIONS_LOCAL": 2,
  "DB_TXN_PER_MIN": 1240.0,
  "DB_DISK_FREE_GB": null,

  "SAF_QUEUE_DEPTH": 0,
  "SAF_REPLICATION_LAG_MS": 80.0,
  "SAF_DISK_BYTES": 524288000,

  "OPC_MONITORED_COUNT": 847,
  "CVT_TAG_COUNT": 920,
  "CVT_LOCK_CONTENTION": 0,
  "SAMPLE_LAG_MS": 1.2,
  "ACQUISITION_READY": true,

  "clock": {
    "enabled": true,
    "synced": true,
    "warn": false,
    "offset_ms": 3.0
  }
}
```

| Campo clave | Interpretación operativa |
|---|---|
| `METRICS_AGE_MS` | Confianza del operador. Warning UI ≥ 15 s; crítico ≥ 60 s |
| `DB_TXN_PER_MIN` | `null` en primer tick o si PG no responde; no invalida el resto |
| `DB_DISK_FREE_GB` | Reservado P2; siempre `null` hoy |
| `HTTP_*` | Ventana deslizante 60 s; no incluye latencia por ruta |

---

## 5. Brechas cerradas y pendientes

### 5.1 Cerradas (P0–P1)

| ID | Hallazgo original | Resolución |
|---|---|---|
| NPD-H1 | Clientes HMI no expuestos | `HMI_ACTIVE_CLIENTS` |
| NPD-H4 | Sin contadores HTTP | Middleware O(1) |
| NPD-H7 | Sin CPU % | psutil en sampler |
| NPD-H8 | Sin disco host | `disk_usage('/')` |
| NPD-H9 | Sin txn/min | `query_pg_txn_counters` |
| NPD-H11 | `/health/system` no O(1) para poll RT | Nuevo `/health/node` |
| NPD-H12 | Pantalla ausente | `/performance` |
| NPD-H13 | Sin sparklines | Canvas + ring 60 pts |

### 5.2 Abiertas (P2–P3)

| ID | Item | Prioridad |
|---|---|---|
| NPD-H5 | Latencia p50/p95 HTTP por ruta | P2 |
| NPD-H10 | Disco remoto PG (`DB_DISK_FREE_GB`) | P2 opcional |
| NPD-H14 | Export Prometheus `/metrics` | P3 |
| — | Push Socket.IO `node.metrics` | P2 opcional |
| — | Soak 24 h multi-cliente | Requerido para A+ |

### 5.3 Anti-patrones prohibidos (verificados)

| Anti-patrón | Estado |
|---|---|
| Poll `/health/system` cada 1–3 s desde N HMIs | **Evitado** — HMI usa `/health/node` |
| `COUNT(*) hmi_sessions` en cada GET HTTP | **Evitado** — solo en sampler |
| `pg_stat_*` en request path de `/node` | **Evitado** — throwaway en worker |
| Pool Peewee en sampler | **Ausente** — test estático CA-NPD-12 |
| Plotly en dashboard performance | **Evitado** — canvas ligero |

---

## 6. Criterios de aceptación (CA-NPD-01 … CA-NPD-15)

| ID | Criterio | Evidencia 2026-08-19 |
|---|---|---|
| CA-NPD-01 | GET dict &lt; 5 ms p95 local | `test_get_snapshot_p95_under_5ms` — p95 &lt; 5 ms en 200 iteraciones |
| CA-NPD-02 | 10 HMIs polleando 3 s, RSS &lt; +5 % vs baseline | **Pendiente** soak 24 h |
| CA-NPD-03 | `HMI_ACTIVE_CLIENTS` = COUNT store | `test_hmi_active_clients_uses_store_count`; SQL real: `WHERE node_id = :edge` |
| CA-NPD-04 | `HTTP_REQUESTS_1M` tras tráfico | `test_request_window_increments` + `test_flask_middleware_counts` |
| CA-NPD-05 | CPU y disco si psutil | `test_psutil_fields_when_available` |
| CA-NPD-06 | `/performance` admin/supervisor; 403 otro | `@auth_roles` + `canViewPerformance` + redirect Events; **manual** |
| CA-NPD-07 | Sparklines 60 pts sin leak 1 h | `pushRing` acota; **manual** DevTools |
| CA-NPD-08 | Poll 30 s si pestaña oculta | `pollIntervalMs` + `usePerformancePoll`; `test_hmi_poll_hidden_contract` |
| CA-NPD-09 | `/health/system` sin regresión | `test_system_endpoint_still_present` |
| CA-NPD-10 | Sampler sobrevive BD down | `test_survives_db_outage` |
| CA-NPD-11 | txn/min visible o null sin error | `_sample_db` + `_publish` last-value |
| CA-NPD-12 | Sin pool Peewee reintroducido | `test_sampler_does_not_use_peewee_pool` |
| CA-NPD-13 | Runbook performance | `docs/node-performance-runbook.md`, `docs/runbook.md`, § multi-edge |
| CA-NPD-14 | Multi-edge: solo métricas locales | `count_sessions(node_id)`; **manual** 2-edge |
| CA-NPD-15 | Sampler &lt; 1 % CPU idle | **Pendiente** soak 24 h |

**Automatizados hoy:** 11/15 (73 %). **Pendientes de planta:** CA-NPD-02, 06 (parcial), 07, 14, 15.

---

## 7. Veredicto por dimensión

| Dimensión | Nota | Comentario |
|---|---|---|
| Poll O(1) | **A+** | Copia dict; p95 &lt; 5 ms en unit test |
| Contadores HTTP | **A** | Lock + ventana 60 s; `teardown_request` evita in-flight leak |
| Sampler | **A** | Daemon; last-value on fault; intervalo 5–30 s configurable |
| Métricas host | **A** | psutil; fallback `resource` |
| HMI dashboard | **A** | Tarjetas + canvas + modal ISA-18.2; poll hidden; RBAC |
| Alarmas de rendimiento | **A** | 7 BOOL; debounce; Settings hot-reload; misma fuente que `/alarms` |
| BD txn/min | **A−** | Throwaway OK; disco PG remoto no implementado |
| Multi-edge scope | **A** (diseño) / **manual pendiente** | Filtro `node_id` en código |
| Prometheus | **N/A** | P3 explícito |
| Soak planta | **Pendiente** | CA-NPD-02, 14, 15 |

**Veredicto global: A−.** Observabilidad operativa + alarmas ISA-18.2 unificadas, sin tocar el hot path. **A+** cuando soaks 24 h, 2-edge y prueba manual CA-PERF-09/10/13/14 en planta estén cerrados.

---

## 8. Despliegue y rollout

| Paso | Acción |
|---|---|
| 1 | `pip install` wheel con `psutil==6.1.1` (incluido en `requirements.txt`) |
| 2 | `npm run build` en `hmi/` — la HMI empaquetada no incluye `/performance` hasta rebuild |
| 3 | Rebuild wheel + `pip install --force-reinstall` en venv de planta |
| 4 | Verificar `GET /api/health/node` con token admin (debe responder &lt; 5 ms) |
| 5 | HMI → **Rendimiento del nodo**; confirmar `METRICS_AGE_MS` &lt; 10 s en idle |
| 6 | Multi-edge: repetir en cada edge; confirmar `NODE_ID` distinto por instancia |

**No usar** `/api/health/system` como sustituto del dashboard — multiplica consultas OPC/PG por cliente.

---

## 9. Referencias

| Tema | Ruta |
|---|---|
| Spec | [specs/05-NODE-PERFORMANCE-DASHBOARD.md](../specs/05-NODE-PERFORMANCE-DASHBOARD.md) |
| Runbook | [docs/node-performance-runbook.md](../docs/node-performance-runbook.md) |
| Multi-edge | [docs/multi-edge.md](../docs/multi-edge.md) § Dashboard |
| Changelog | [CHANGELOG.md](../CHANGELOG.md) |
| Health node | `automation/modules/health/resources/health.py` |
| Sampler | `automation/workers/metrics_sampler.py` |
| HTTP metrics | `automation/utils/http_metrics.py` |
| Txn PG | `automation/utils/db_connections.py` → `query_pg_txn_counters` |
| HMI sessions | `automation/utils/hmi_session_store.py` → `count_sessions` |
| Tests | `automation/tests/test_node_performance.py` (14) + `test_performance_alarms.py` (13) |
| Spec alarmas | [specs/06-PERFORMANCE-ALARMS.md](../specs/06-PERFORMANCE-ALARMS.md) |
| Hot path (contraste) | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) |

---

## 11. Alarmas de rendimiento unificadas (ISA-18.2)

Fuente de verdad: **tag BOOL + AlarmManager**. El dashboard no duplica estado: se suscribe a `alarmsSlice` (Socket `on.alarm` + hidratación `GET /alarms/`). Ack/shelve/unshelve usan los endpoints de alarmas.

### 11.1 Catálogo (7)

| Key | Alarma | Métrica | Default | Debounce |
|---|---|---|---|---|
| cpu | `{area}.ALM.PERF.CPU` | `HOST_CPU_PERCENT` | 85 % | 3 ticks |
| disk | `{area}.ALM.PERF.DISK` | `HOST_DISK_USED_PERCENT` | 90 % | 3 |
| saf_queue | `{area}.ALM.PERF.SAF_QUEUE` | `SAF_QUEUE_DEPTH` | 5000 | 3 |
| saf_lag | `{area}.ALM.PERF.SAF_LAG` | `SAF_REPLICATION_LAG_MS` | 10000 ms | 3 |
| metrics_age | `{area}.ALM.PERF.METRICS_AGE` | `METRICS_AGE_MS` (edad al inicio del tick) | 30000 ms | 3 |
| db_conn | `{area}.ALM.PERF.DB_CONN` | `DB_ACTIVE_CONNECTIONS` | 10 | 3 |
| http_5xx | `{area}.ALM.PERF.HTTP_5XX` | `HTTP_5XX_1M` | 5 / min | 3 |

Descripción persistida: `System · …`. El modelo `Alarms` **no** tiene columna `classification`; Events de transición usan `classification=System`. La página Alarmas las lista como cualquier BOOL.

### 11.2 Evaluación

`PerfAlarmEvaluator` corre **solo** en el sampler (O(7) por tick). Activación con debounce; retorno a normal inmediato. `None` no dispara. PUT Settings llama `metrics_worker.reconfigure()` y reevalúa el último snapshot **en el mismo ciclo** (CA-PERF-12).

`GET /health/node` no evalúa umbrales. Incluye `PERF_ALARMS` (catálogo + umbrales + nombres) en el dict precomputado.

### 11.3 HMI

| Pieza | Comportamiento |
|---|---|
| `MetricTile` / `MetricGauge` | Variante gauge o tile; campana vs ℹ️; engranaje Configurar; badge ACTIVA/ACK/SILENCIADA/OK; umbral; sparkline |
| `PerfPanel` | Subsistemas HTTP / HMI / BD / SAF / Adquisición |
| `PerformanceAlarmModal` | Valor, umbral, estado ISA-18.2; Ack; Shelve 1 h; Unshelve; Configurar abre modal de umbral; enlace Events |
| `PerformanceThresholdModal` | Umbral, debounce, habilitado; PUT `/settings/performance`; preview would-alarm vs último snapshot |
| `usePerformanceAlarms` | Selector Redux + hidrata `GET /alarms/?limit=500` |
| `PerformanceAlarmConfig` | Settings capítulo 03; enabled, debounce, umbral por alarma (admin/supervisor/sudo) |
| Página Alarmas | Misma instancia; sync vía `alarmsSlice` (CA-PERF-14) |

`POST /api/alarms/unshelve/<name>` envuelve `Alarm.unshelve()` (antes no había ruta HTTP).

### 11.4 CA-PERF-09 … 14

| ID | Criterio | Evidencia 2026-08-19 |
|---|---|---|
| CA-PERF-09 | Clic en tarjeta con alarma → modal correcto | Código: `onOpen` + `PerformanceAlarmModal`; **manual** |
| CA-PERF-10 | Ack → tarjeta amarilla | `acknowledgeAlarm` + `toneFromLifecycle("ack")=warn`; shelved → gris; contrato unitario; **manual** Socket |
| CA-PERF-11 | Shelve / Unshelve | Modal + `POST /alarms/shelve` / `unshelve`; **manual** |
| CA-PERF-12 | Umbral Settings &lt; 1 ciclo sampler | `test_reconfigure_evaluates_last_snapshot`; `update_performance_alarm_config` → `reconfigure()` |
| CA-PERF-13 | Aparecen en Alarmas como System | Descripción `System ·`; nombres `ALM.PERF.*`; **manual** filtro |
| CA-PERF-14 | Dashboard y Alarmas sincronizados | Un AlarmManager + `alarmsSlice` + `on.alarm`; **manual** |

Tests automáticos: `automation.tests.test_performance_alarms` — debounce, clear, disable, None, reconfigure, ensure ×7, contrato de tono.

### 11.5 Anti-patrones evitados

- No HI/LO sobre CPU (solo BOOL).
- No pool Peewee / no eval en GET `/node`.
- No Plotly; modal Bootstrap ligero.
- No segundo store de alarmas en el dashboard.

---

## 12. UI profesional (spec 07 / CA-UI-06 … 10)

Fuente: `hmi/src/pages/Performance.tsx` + `MetricTile` + `PerfPanel` + dos modales. El backend de evaluación **no** cambia.

Layout: header (nodo, área, uptime, edad del snapshot, NTP) → fila gauges (CPU, RSS, disco, cola SAF, NTP) → paneles de subsistema → tendencias colapsables.

| ID | Criterio | Evidencia 2026-08-19 |
|---|---|---|
| CA-UI-06 | Indicador de estado + umbral en tarjetas alarmables | Campana, badge, `thresholdLine`; tono `toneFromLifecycle` (shelved = gris) |
| CA-UI-07 | Engranaje abre modal de umbrales | `PerformanceThresholdModal`; stopPropagation en el gear |
| CA-UI-08 | Cambio de umbral &lt; 1 ciclo | PUT existente + `reconfigure()`; `onSaved` → `load()` |
| CA-UI-09 | Modal alarma Ack / Shelve / Unshelve / Configurar | `PerformanceAlarmModal` |
| CA-UI-10 | Responsivo ≥ 1024×768 | 5 gauges / 3 paneles desde 1024 px; 2 columnas entre 700 y 1023 |

**Limitación de este host:** no hay `npm`; los cambios en `hmi/src/` no se ven en el bundle empaquetado hasta `npm run build`.

---

## 10. Changelog

| Fecha | Cambio |
|---|---|
| 2026-08-19 | Creación auditoría; veredicto **D**; arquitectura objetivo A+ documentada |
| 2026-08-19 | Implementación P0+P1+P2 txn/min; veredicto **A−**; 14 unit tests; docs runbook/spec/multi-edge |
| 2026-08-19 | Actualización auditoría: catálogo antes/ahora, arquitectura, payload, despliegue, mapa CA↔tests |
| 2026-08-19 | Alarmas de rendimiento unificadas (spec 06); CA-PERF-09…14; veredicto **A−** se mantiene (soaks + prueba manual de modal pendientes para A+) |
| 2026-08-19 | UI profesional `/performance` (spec 07); CA-UI-06…10; umbrales PUT para supervisor; veredicto **A−** |
