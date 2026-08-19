# Auditoría compacta: pantalla de performance del nodo (Node Performance Dashboard)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) |
| **Alcance** | Visibilidad en tiempo real del rendimiento por edge/nodo — sin degradar el hot path de adquisición ni el consumo del propio nodo al mostrar métricas |
| **Fecha** | 2026-08-19 |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) |
| **Veredicto vigente** | **D** — Base backend **B+** (`/health/system` rico pero costoso); **no existe** pantalla HMI de performance. Objetivo A+ requiere snapshot O(1) + `MetricsSamplerWorker` + ruta `/performance` |
| **Clasificación** | Auditoría operativa · observabilidad · dashboard edge |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-19) |
|---|---|
| ¿Existe una pantalla HMI para medir performance del nodo en tiempo real? | **No** — ruta `/performance` **comentada**; componente `Performance` **ausente** |
| ¿Hay API lista para alimentar ese dashboard sin matar el nodo? | **Parcial** — `GET /api/health/system` expone ~40 métricas pero **recalcula en cada GET** (OPC, PG `pg_stat_activity`, gateway SAF, NTP) → **no O(1)** para poll agresivo |
| ¿Socket.IO / TLS / clientes HMI visibles en health? | **No en API** — datos en PG `hmi_sessions` + Events; **SocketBadge** solo estado local del navegador |
| ¿Contadores HTTP (req/min, 5xx, latencia)? | **No** — sin middleware de conteo |
| ¿RAM / CPU / disco del host? | **RAM sí** (`RSS_MB`); **CPU y disco host no**; disco SAF journal sí (`/health/saf`) |
| ¿Métricas BD remota (TPS, conexiones, disco servidor PG)? | **Parcial** — `DB_ACTIVE_CONNECTIONS` vía `pg_stat_activity` (costoso); **sin TPS**, **sin disco del servidor PG** |
| ¿Poll 1 Hz desde 10 HMIs es seguro hoy? | **No** — multiplicaría carga de `/health/system` × clientes |
| ¿Qué falta para A+ industrial? | Snapshot cacheado O(1) + worker muestreador + pantalla HMI ligera + catálogo métrico unificado |

### 0.1 Principio rector

> **El observador no puede costar más que lo observado.**

En un edge OT con adquisición a 1 Hz, el dashboard de performance debe:

1. **Leer** un dict precomputado — O(1) por request HTTP.
2. **Escribir** contadores en el hot path solo con incrementos atómicos — O(1) por evento.
3. **Muestrear** CPU, PG, sesiones HMI en un **worker daemon** (5–30 s), nunca en cada poll del operador.
4. **Pausar** el poll HMI cuando `document.hidden` ([AUDIT_HMI.md](./AUDIT_HMI.md) HMI-H3).

---

## 1. Catálogo de métricas solicitadas vs estado actual

### 1.1 Conectividad Socket.IO / TLS / HMI

| Métrica | Fuente hoy | API health | HMI | Gap |
|---|---|---|---|---|
| Clientes HMI activos (global) | `hmi_sessions` COUNT(*) | ❌ | ❌ (solo badge local) | **NPD-H1** |
| Sesiones por username / IP | Tabla `hmi_sessions` | ❌ | ❌ | NPD-H2 |
| TLS handshake failures / IP | Events + `hmi_tls_telemetry` | ❌ | ❌ | NPD-H3 |
| Socket conectado (este cliente) | `socket.ts` | — | ✅ `SocketBadge` | OK local |
| Reconnect rate | Events `HMI client reconnected` | ❌ | ❌ | Derivable de Events, no RT |

Referencia: [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md).

### 1.2 HTTP / API REST

| Métrica | Fuente hoy | Gap |
|---|---|---|
| Requests totales | — | **NPD-H4** — sin middleware |
| Requests / min (ventana deslizante) | — | NPD-H4 |
| Requests in-flight | — | NPD-H4 |
| Errores 5xx / min | — | NPD-H4 |
| Latencia p50/p95 API | — | NPD-H5 (fase 2; ring buffer en worker) |
| Top endpoints (opcional) | — | NPD-H6 (fase 3; cardinalidad acotada LRU) |

Hoy solo existen proxies indirectos: `LOG_ERROR_RATE_PER_MIN`, `EVENTS_RATE_PER_MIN` ([AUDIT_LOGGING.md](./AUDIT_LOGGING.md)).

### 1.3 Recursos del proceso edge (host local)

| Métrica | `/health/system` | Notas |
|---|---|---|
| RSS memoria (`RSS_MB`) | ✅ | psutil / `resource` |
| Hilos (`THREAD_COUNT`) | ✅ | |
| CPU % proceso / sistema | ❌ | **NPD-H7** |
| Disco libre host (`/`, `/var`, journal) | ❌ | **NPD-H8** — solo `SAF_DISK_BYTES` en `/health/saf` |
| Load average | ❌ | NPD-H8 |
| FDs abiertos | ❌ | Opcional fase 2 |

### 1.4 Base de datos remota (historiador PostgreSQL)

| Métrica | Fuente hoy | Gap |
|---|---|---|
| Conectado + latencia probe | ✅ `/health/db` | Cache 1.5 s — OK para badge |
| Conexiones activas PG (`pg_stat_activity`) | ✅ `DB_ACTIVE_CONNECTIONS` | **Costoso** si en cada GET system |
| Conexiones libpq in-process | ✅ `DB_CONNECTIONS_COUNT` | [AUDIT_DB.md](./AUDIT_DB.md) |
| Alerta umbral conexiones | ✅ `DB_CONNECTIONS_ALERT` | |
| TPS / transacciones min | ❌ | **NPD-H9** — requiere `pg_stat_database` muestreado |
| Tamaño BD / disco servidor PG | ❌ | **NPD-H10** — requiere extensión o query remota 30 s |
| Replication lag (si aplica) | Parcial SAF | `SAF_REPLICATION_LAG` ≠ lag PG streaming |
| Locks / deadlocks | ❌ | Fase 3 |

### 1.5 Adquisición, SAF y hot path ([AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md))

| Métrica | `/health/system` | Uso dashboard |
|---|---|---|
| `OPC_MONITORED_COUNT` | ✅ | Carga OPC |
| `CVT_TAG_COUNT` | ✅ | Tamaño CVT |
| `CVT_LOCK_CONTENTION` | ✅ | Contención |
| `TAG_OBSERVER_COUNT` / `MACHINE_OBSERVER_COUNT` | ✅ | Observers vivos |
| `SAF_QUEUE_DEPTH` | ✅ | Cola historiador |
| `SAF_PENDING_CAP_HITS` | ✅ | Backpressure |
| `SAMPLE_LAG_MS` / `EXECUTION_CYCLE_US` | ✅ | State machines |
| `BUFFER_UTILIZATION_%` | ✅ | Buffers SM |
| `ACQUISITION_READY` | ✅ | Identidad multi-edge |

### 1.6 Otros parámetros recomendados para la pantalla

| Métrica | Fuente | Prioridad |
|---|---|---|
| NTP offset / synced | `/health/system` → `clock` | P0 |
| Log ERROR rate | `LOG_ERROR_RATE_PER_MIN` | P1 |
| Events rate | `EVENTS_RATE_PER_MIN` | P1 |
| Alarmas activas en memoria | `ALARM_COUNT` | P1 |
| `NODE_ID` / `NODE_AREA` / identidad | ✅ | P0 |
| Edad del snapshot (`METRICS_AGE_MS`) | ❌ | P0 — confianza operador |
| Versión / uptime proceso | ❌ | P2 |

---

## 2. Inventario de código (evidencia 2026-08-19)

### 2.1 Backend — endpoints existentes

| Ruta | Archivo | Coste por GET | Uso actual |
|---|---|---|---|
| `GET /api/health/ping` | `automation/modules/health/resources/health.py` | **Mínimo** | Docker liveness |
| `GET /api/health/system` | mismo | **Alto** — OPC + PG + SAF + NTP | Soak manual, scripts ops |
| `GET /api/health/db` | + `automation/health/service.py` | **Medio** — SELECT 1 cache 1.5 s | HMI `DatabaseStatus` poll 8 s |
| `GET /api/health/saf` | + `automation/persistence/health.py` | Medio | Ops / alertas 503 |
| `GET /api/system/nodes` | `automation/modules/system/resources/system.py` | Bajo | Catálogo multi-edge (sin métricas RT) |

Campos clave de `/health/system` (extracto):

```211:234:automation/modules/health/resources/health.py
        return {
            "status": "ok",
            "service": "pyautomation",
            "is_db_connected": db_connected,
            "RSS_MB": round(rss_mb, 2),
            "THREAD_COUNT": threading.active_count(),
            "OPC_MONITORED_COUNT": opc_monitored,
            ...
            **timing_metrics,
            **node_metrics,
            **conn_metrics,
            **clock_metrics,
            **_log_error_metrics(),
            **_event_rate_metrics(),
        }, 200
```

### 2.2 HMI — observabilidad parcial

| Componente | Poll | Endpoint | Limitación |
|---|---|---|---|
| `DatabaseStatusProvider` | 8 s | `/health/db` | Solo latencia/conexión BD |
| `ClockBadge` | 60 s | implícito vía clock API | NTP, no performance |
| `SocketBadge` | pub/sub local | — | No métricas servidor |
| `useMemoryWatchdog` | continuo | POST `/logs/add` | Heap **navegador**, no edge |
| `ServiceRuntimePanel` | — | settings | Solo logger period/level |
| **`/performance`** | — | — | **Ruta comentada, sin página** |

```22:22:hmi/src/routes/index.tsx
// import { Performance } from "../pages/Performance";
```

```67:67:hmi/src/routes/index.tsx
        {/* <Route path="/performance" element={<Performance />} /> */}
```

Servicio HMI: `hmi/src/services/health.ts` — **no** expone wrapper de `/health/system` completo.

### 2.3 Contadores existentes reutilizables (patrones O(1))

| Módulo | Patrón | Reutilizable para |
|---|---|---|
| `automation/utils/audit_metrics.py` | Ventana deslizante + rate/min | HTTP req/min |
| `automation/utils/log_filters.py` | DedupeFilter + snapshot | Errores/min |
| `automation/health/service.py` | Cache TTL 1.5 s | Modelo para `/health/node` |
| `automation/workers/hmi_session_cleanup.py` | Worker daemon 60 s | Modelo `MetricsSamplerWorker` |
| `automation/state_machine_timing.py` | Snapshot timing | Ya en system health |

---

## 3. Brechas vs requisito «ultra ligero, O(1), sin Big-O en el poll»

| ID | Severidad | Hallazgo | Impacto |
|---|---|---|---|
| **NPD-H1** | Alta | Clientes HMI no expuestos en health | Operador no ve carga socket global |
| **NPD-H4** | Alta | Sin contadores HTTP | Ciego a picos API / loops HMI |
| **NPD-H7** | Alta | Sin CPU % | No detecta saturación edge |
| **NPD-H8** | Alta | Sin disco host | Riesgo disco lleno (journal, logs, backups) |
| **NPD-H9** | Media | Sin TPS / txn min BD | Ciego a carga historiador |
| **NPD-H10** | Media | Sin disco servidor PG remoto | Capacidad BD en otro host invisible |
| **NPD-H11** | Alta | `/health/system` no es O(1) | Poll RT desde HMI **peligroso** |
| **NPD-H12** | Alta | Pantalla Performance ausente | Requisito producto sin cumplir |
| **NPD-H13** | Media | Sin histórico/sparklines en producto | Solo snapshot; aceptable en cliente (ring 60 pts) |
| **NPD-H14** | Baja | Sin export Prometheus | Ops externa manual |

### 3.1 Anti-patrones prohibidos

| Anti-patrón | Por qué |
|---|---|
| Poll `/health/system` cada 1 s desde N clientes | Multiplica OPC + PG queries — incidente tipo BE-H4 |
| `COUNT(*) hmi_sessions` en cada GET | O(n) filas — usar cache worker 30 s |
| `pg_stat_activity` en request path | Conexión throwaway + query — mover a sampler |
| Gráficos Plotly en dashboard performance | Pesado; preferir tarjetas + sparkline CSS/canvas ligero |
| Push Socket.IO métricas sin suscriptores | Emitir solo si hay listeners en room `node.metrics` |

---

## 4. Arquitectura objetivo A+ (especificación de diseño)

### 4.1 Capas

```
┌─────────────────────────────────────────────────────────────┐
│  HOT PATH (O(1) por evento)                                 │
│  • http_requests_total++, http_5xx_total++                  │
│  • http_in_flight++/--                                       │
│  • (existente) cvt_lock_contention, audit rates               │
└──────────────────────────┬──────────────────────────────────┘
                           │ cada 5–30 s
┌──────────────────────────▼──────────────────────────────────┐
│  MetricsSamplerWorker (daemon, 1 hilo)                       │
│  • psutil: CPU%, disk_usage('/')                             │
│  • count_sessions() — 30 s                                   │
│  • pg_stat_database / pg_stat_activity — 30 s                │
│  • gateway SAF parcial, OPC counts (mover lógica de system)  │
│  • escribe _NODE_METRICS_SNAPSHOT dict + METRICS_AGE_MS      │
└──────────────────────────┬──────────────────────────────────┘
                           │ GET O(1)
┌──────────────────────────▼──────────────────────────────────┐
│  GET /api/health/node  (o /health/system?lite=1)             │
│  • lectura dict + JSON serialize — sin I/O blocking           │
│  • Cache-Control: max-age=1                                  │
│  • auth: token (admin/supervisor)                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ poll 3 s (pause if hidden)
┌──────────────────────────▼──────────────────────────────────┐
│  HMI /performance — NodePerformancePanel                     │
│  • tarjetas + sparklines ring buffer cliente (60 pts)        │
│  • secciones: Host | HTTP | HMI | DB | SAF | Acquisition     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Payload objetivo `GET /api/health/node` (~35 campos)

```json
{
  "status": "ok",
  "METRICS_AGE_MS": 420,
  "NODE_ID": "edge-linea1",
  "uptime_s": 86412,

  "HOST_RSS_MB": 412.5,
  "HOST_CPU_PERCENT": 18.2,
  "HOST_DISK_FREE_GB": 42.1,
  "HOST_DISK_USED_PERCENT": 61.0,
  "HOST_THREADS": 24,

  "HTTP_REQUESTS_TOTAL": 184320,
  "HTTP_REQUESTS_1M": 38,
  "HTTP_5XX_1M": 0,
  "HTTP_IN_FLIGHT": 2,

  "HMI_ACTIVE_CLIENTS": 3,
  "HMI_SESSIONS_SAMPLE_AGE_MS": 12000,

  "DB_CONNECTED": true,
  "DB_LATENCY_MS": 4,
  "DB_ACTIVE_CONNECTIONS": 5,
  "DB_CONNECTIONS_LOCAL": 2,
  "DB_TXN_PER_MIN": 1240,
  "DB_DISK_FREE_GB": null,

  "SAF_QUEUE_DEPTH": 12,
  "SAF_REPLICATION_LAG_MS": 80,
  "SAF_DISK_BYTES": 524288000,

  "OPC_MONITORED_COUNT": 847,
  "CVT_TAG_COUNT": 920,
  "CVT_LOCK_CONTENTION": 0,
  "SAMPLE_LAG_MS": 1.2,
  "ACQUISITION_READY": true,

  "clock": { "synced": true, "offset_ms": 3 }
}
```

`DB_DISK_FREE_GB`: solo si query remota habilitada y permisos; si no → `null` + tooltip «requiere extensión ops».

### 4.3 Complejidad garantizada

| Operación | Complejidad | Notas |
|---|---|---|
| GET `/health/node` | **O(1)** | Copia dict precomputado |
| Incremento HTTP | **O(1)** | Atómico |
| HTTP req/min | **O(1)** amortizado | Mismo patrón `audit_metrics` |
| Worker sampler | **O(1)** por tick | Coste acotado fijo, no escala con tags |
| HMI render | **O(k)** k=60 puntos sparkline | Independiente de tags OPC |

**No** O(n_tags), **no** O(n_sessions) en request path.

### 4.4 UI HMI — layout propuesto

| Sección | Tarjetas | Fuente |
|---|---|---|
| **Identidad** | Node, area, uptime, metrics age | snapshot |
| **Host** | RSS, CPU, disco, threads | snapshot |
| **HTTP** | req/min, 5xx/min, in-flight | snapshot |
| **HMI / Socket** | clientes activos, link Events | snapshot + enlace |
| **Historiador** | latencia, conexiones, txn/min | snapshot + `/health/db` |
| **SAF** | queue, lag, disco journal | snapshot |
| **Adquisición** | OPC items, CVT, SM lag, lock | snapshot |
| **Reloj** | NTP badge inline | clock block |

Comportamiento: poll **3 s** en foco; **30 s** en `document.hidden`; un solo fetch paralelo por tick.

---

## 5. Criterios de aceptación (CA-NPD-01 … CA-NPD-15)

| ID | Criterio | Tipo |
|---|---|---|
| CA-NPD-01 | `GET /health/node` responde < 5 ms p95 local (dict precomputado) | Auto |
| CA-NPD-02 | 10 HMIs polleando 3 s no elevan RSS > 5 % vs baseline | Soak |
| CA-NPD-03 | `HMI_ACTIVE_CLIENTS` coincide con `SELECT COUNT(*) FROM hmi_sessions` ±0 | Auto |
| CA-NPD-04 | `HTTP_REQUESTS_1M` incrementa tras tráfico sintético | Auto |
| CA-NPD-05 | CPU y disco host presentes cuando psutil disponible | Auto |
| CA-NPD-06 | Pantalla `/performance` accesible admin/supervisor | Manual |
| CA-NPD-07 | Sparklines 60 pts sin memory leak 1 h | Manual |
| CA-NPD-08 | Poll pausa en pestaña oculta | Auto HMI |
| CA-NPD-09 | `/health/system` sin regresión (modo full sigue existiendo) | Auto |
| CA-NPD-10 | Worker sampler sobrevive reconnect BD | Integration |
| CA-NPD-11 | DB txn/min visible si PG reachable | Integration |
| CA-NPD-12 | Sin pool Peewee reintroducido | Review |
| CA-NPD-13 | Documentación runbook performance | Docs |
| CA-NPD-14 | Multi-edge: cada nodo muestra **solo** sus métricas | Manual 2-edge |
| CA-NPD-15 | Carga sampler < 1 % CPU media edge idle | Soak 24 h |

---

## 6. Plan de implementación recomendado

| Fase | Entregable | Prioridad |
|---|---|---|
| **P0** | `http_metrics.py` middleware O(1) + `MetricsSamplerWorker` + `GET /health/node` | Crítico |
| **P0** | Exponer `HMI_ACTIVE_CLIENTS`, CPU, disco host | Crítico |
| **P1** | Página HMI `/performance` + servicio `getNodePerformance()` | Alto |
| **P1** | PG `pg_stat_database` → txn/min (sampler 30 s) | Alto |
| **P2** | Disco remoto PG (si permisos) + latencia p95 HTTP | Medio |
| **P2** | Push opcional Socket.IO `node.metrics` si suscriptores | Medio |
| **P3** | Export Prometheus `/metrics` | Bajo |

Spec sugerida: `specs/05-NODE-PERFORMANCE-DASHBOARD.md` (pendiente de crear).

---

## 7. Veredicto por dimensión

| Dimensión | Nota | Comentario |
|---|---|---|
| Datos backend disponibles | **B+** | `/health/system` rico pero no apto como dashboard RT |
| Métricas socket HMI | **C** | PG existe; no expuesto en health |
| Métricas HTTP | **F** | No implementado |
| CPU / disco host | **F** | No implementado |
| Métricas BD remota | **C+** | Latencia + conexiones; sin TPS/disco |
| Pantalla HMI | **F** | Ruta comentada, sin UI |
| Diseño O(1) poll | **A** (diseño) / **F** (código) | Arquitectura definida; falta implementar |
| Impacto en hot path | **A** (diseño) | Worker + contadores atómicos |

**Veredicto global: D** — Hay **cimientos** de observabilidad (health, soak, audit rates) pero **no hay producto** de dashboard de performance de nodo. El operador hoy debe usar curl/scripts + Events + `/health/system` manual.

**Objetivo A+** tras P0+P1 + CA-NPD-01…15 en planta.

---

## 8. Referencias

| Tema | Ruta |
|---|---|
| Health system (full) | `automation/modules/health/resources/health.py` |
| Health DB cache | `automation/health/service.py` |
| PG connection metrics | `automation/utils/db_connections.py` |
| Audit rates (patrón) | `automation/utils/audit_metrics.py` |
| HMI sessions count | `automation/utils/hmi_session_store.py` |
| Socket traceability | [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md) |
| Hot path / runbook | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) |
| HMI poll patterns | [AUDIT_HMI.md](./AUDIT_HMI.md) |
| Ruta performance (stub) | `hmi/src/routes/index.tsx` |
| Soak tests | `automation/tests/test_performance_soak.py` |

---

## 9. Changelog

| Fecha | Cambio |
|---|---|
| 2026-08-19 | Creación auditoría; veredicto **D**; arquitectura objetivo A+ documentada |
