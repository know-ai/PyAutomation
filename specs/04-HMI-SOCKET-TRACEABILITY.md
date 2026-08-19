# Spec 04 — Trazabilidad Socket.IO y TLS (estándar A+ sin Redis)

| Campo | Valor |
|---|---|
| **Versión** | 2.1 |
| **Producto** | PyAutomationIO (`automation/` + HMI React) |
| **Estado** | Implementado en código (2026-08-19) |
| **Auditoría** | [audits/AUDIT_HMI_SOCKET_TRACEABILITY.md](../audits/AUDIT_HMI_SOCKET_TRACEABILITY.md) |
| **Runbook** | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |

## Objetivo

Alcanzar trazabilidad **A+** de conectividad HMI (Socket.IO + TLS) **sin Redis**, usando PostgreSQL (`hmi_sessions`) y workers ligeros.

## Premisas

- Sin nuevas dependencias de infraestructura
- Carga PG mínima (connect/disconnect esporádicos; heartbeat 30 s/cliente)
- Conteo global correcto con múltiples workers Gunicorn/gevent

## Arquitectura

### Tabla `hmi_sessions`

| Columna | Tipo | Descripción |
|---|---|---|
| `sid` | PK varchar(64) | Session ID Socket.IO |
| `node_id` | varchar(64) | Edge (`AUTOMATION_NODE_ID`) |
| `username` | varchar(64) | Operador autenticado |
| `origin` | varchar(45) | IP cliente |
| `area` | varchar(64) | Área del nodo |
| `connected_at` | timestamp UTC | Primera conexión |
| `last_heartbeat` | timestamp UTC | Último ping HMI |

Índice compuesto: `(node_id, last_heartbeat)`.

### Flujos

1. **Connect** — validar token (fail-closed) → UPSERT fila → evento + `COUNT(*)`
2. **Disconnect** — DELETE fila → evento + conteo
3. **Heartbeat** — HMI `emit('ping')` cada 30 s → UPDATE `last_heartbeat`
4. **Cleanup** — `HmiSessionCleanupWorker` cada 60 s → DELETE stale > 2 min
5. **TLS** — evento por IP rate-limit 5 min: `HMI TLS handshake failure`

### Eventos L3

| message | classification |
|---|---|
| `HMI client connected` | HMI |
| `HMI client disconnected` | HMI |
| `HMI client reconnected` | HMI |
| `HMI client connection rejected` | HMI |
| `HMI TLS handshake failure` | HMI |

## Componentes

| Módulo | Rol |
|---|---|
| `automation/dbmodels/hmi_sessions.py` | Modelo Peewee |
| `automation/utils/hmi_session_store.py` | CRUD + count + cleanup |
| `automation/utils/hmi_socket_audit.py` | Events + connect gate |
| `automation/workers/hmi_session_cleanup.py` | Worker limpieza |
| `automation/utils/hmi_tls_telemetry.py` | TLS por IP |
| `hmi/src/services/socket.ts` | ping + auth + connect_error |

## Criterios de aceptación

| ID | Criterio |
|---|---|
| CA-SKT-11 | Token inválido → rechazo + evento `connection rejected` |
| CA-SKT-12 | Token válido → fila en `hmi_sessions` |
| CA-SKT-13 | Conteo global multi-worker vía `COUNT(*)` PG |
| CA-SKT-14 | Heartbeat + cleanup huérfanas 2 min |
| CA-SKT-15 | TLS por IP rate-limit 5 min |
| CA-SKT-16 | HMI `connect_error` Authentication failed → logout |
| CA-SKT-17 | Runbook publicado |

Tests automáticos: `automation/tests/test_hmi_session_store.py`, `test_hmi_tls_telemetry.py`.

## Rendimiento (orden de magnitud)

| Operación | Frecuencia típica |
|---|---|
| INSERT connect | Decenas / hora / edge |
| UPDATE heartbeat | 1 / 30 s / cliente |
| DELETE cleanup | 1 / 60 s / worker |
| SELECT COUNT | 1 / connect + disconnect |

## Veredicto objetivo

**A+** tras soak multi-cliente 2-edge (CA-SKT-10 + CA-SKT-13 en producción).
