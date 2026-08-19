# Auditoría compacta: trazabilidad de conectividad Socket.IO HMI

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) + Gunicorn/gevent |
| **Alcance** | Ciclo de vida Socket.IO (connect / disconnect / reconnect); telemetría TLS previa al socket; conteo global multi-worker; correlación con tablas `Events` y `hmi_sessions` |
| **Fecha** | 2026-08-19 (v1 A− badge/backfill · v2.1 A+ PG `hmi_sessions`) |
| **Spec** | [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md) v2.1 |
| **Runbook** | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |
| **Complementa** | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) §2 Events, [AUDIT_HMI.md](./AUDIT_HMI.md) §2 socket/EventBus, [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) § SSLEOFError, [AUDIT_DB.md](./AUDIT_DB.md) (hot path `on.tag` sin PG) |
| **Veredicto vigente** | **A+** (código v2.1) — PG `hmi_sessions`, fail-closed token, conteo global multi-worker, TLS por IP, heartbeat + cleanup. Soak formal 2-edge (CA-SKT-10 + CA-SKT-13) **pendiente** en planta |
| **Clasificación** | Auditoría operativa · conectividad HMI · trazabilidad multi-equipo |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-19 v2.1) |
|---|---|
| ¿Las conexiones/desconexiones Socket HMI se registran en la tabla **Events**? | **Sí** — `HMI client connected`, `disconnected`, `reconnected`, `connection rejected` |
| ¿Se identifica **qué cliente** fue? | **Sí** — `username=`, `origin=` (IP), `sid=`, `edge=` (Site.Area + node_id) |
| ¿Se distingue **reconexión** de primera conexión? | **Sí** — HMI envía `auth.reconnect=true` → evento `reconnected` |
| ¿Cuántos clientes HMI hay conectados a la vez? | **Sí, global** — `active_clients=N` desde `COUNT(*)` en `hmi_sessions` por `node_id` (multi-worker) |
| ¿Ante una desconexión aparece un **log** en `app.log`? | **No** — desconexión → evento L3. TLS → evento L3 por IP; log L1 solo DEBUG |
| ¿El token Socket.IO se valida y rechaza si es inválido? | **Sí (fail-closed A+)** — `ConnectionRefusedError("Authentication failed")` + evento `connection rejected` |
| ¿Se usa Redis u otro servicio extra? | **No** — solo PostgreSQL (historiador existente) + worker de limpieza ligero |
| ¿Estaba «de clase mundial» antes del 2026-08-19? | **No** — v1 (misma jornada, mañana) cerró badge/backfill; v2.1 cierra seguridad, conteo global y TLS/IP |

### 0.1 Tres capas de conectividad HMI

| Capa | Qué ocurre | Trazabilidad L3 Events | Log L1 |
|---|---|---|---|
| **A — TLS / WSGI** | Cert autofirmado, HTTP vs TLS, EOF | `"HMI TLS handshake failure"` — **1 evento / IP / 5 min** con `origin=` | DEBUG; traceback suprimido |
| **B — Socket.IO lifecycle** | connect / disconnect / reconnect / reject | 1 evento por sesión (`HMI`); conteo vía PG | Ninguno |
| **C — HTTP sesión** | login / logout REST | `User logged in\|out` (`Security`, `origin=IP`) | Ninguno |

### 0.2 Flujo operativo (v2.1)

```
Login HTTP     → Event: User logged in (origin=IP)
Connect socket → UPSERT hmi_sessions + Event: HMI client connected (active_clients=COUNT(*))
Heartbeat 30s  → UPDATE last_heartbeat (sin evento)
Disconnect     → DELETE hmi_sessions + Event: HMI client disconnected
Reconnect      → Event: HMI client reconnected (+ backfill RT 120 s en HMI)
Token inválido → Event: connection rejected + connect_error en HMI → logout
Worker caído   → Cleanup 60 s elimina filas sin heartbeat > 2 min
```

---

## 1. Por qué importa en planta multi-cliente

| Riesgo | Sin auditoría B | Con v2.1 A+ |
|---|---|---|
| Correlacionar freeze RT con cliente | Inferencia por logs TLS | `disconnected` + IP + sid en Events |
| Contar clientes simultáneos | Imposible | `active_clients` + consulta `hmi_sessions` |
| Multi-worker Gunicorn | Conteo por proceso (v1) | **COUNT(*) PG** compartido |
| Forense TLS remoto | Agregado sin IP | Evento por IP rate-limited |
| Seguridad socket | Fail-open (v1) | **Fail-closed** token |

---

## 2. Inventario de código (evidencia 2026-08-19 v2.1)

### 2.1 Backend — sesiones PG + auditoría

| Artefacto | Rol | Estado |
|---|---|---|
| `automation/dbmodels/hmi_sessions.py` | Tabla `hmi_sessions` (sid, node_id, username, origin, area, timestamps) | ✅ v2.1 |
| `automation/utils/hmi_session_store.py` | upsert / remove / count / heartbeat / cleanup — fail-safe | ✅ v2.1 |
| `automation/utils/hmi_socket_audit.py` | Events + `attempt_hmi_socket_connect` fail-closed | ✅ v2.1 |
| `automation/workers/hmi_session_cleanup.py` | Limpieza huérfanas cada 60 s (> 2 min sin heartbeat) | ✅ v2.1 |
| `automation/core.py` | Handlers `connect` (reject), `disconnect`, `ping`; arranque cleanup worker | ✅ v2.1 |
| `automation/managers/db.py` | `HMISession` en `_tables` → `create_tables` / `ensure_schema` | ✅ v2.1 |
| `automation/utils/hmi_tls_telemetry.py` | TLS **por IP**; mensaje `HMI TLS handshake failure` | ✅ v2.1 |
| `gunicorn.conf.py` | IP cliente WSGI → telemetría TLS | ✅ v2.1 |
| `automation/tests/test_hmi_session_store.py` | 9 tests (store + audit + TLS/IP) | ✅ |
| `automation/tests/test_hmi_tls_telemetry.py` | 3 tests rate-limit por IP | ✅ |

### 2.2 HMI

| Artefacto | Rol | Estado |
|---|---|---|
| `hmi/src/components/SocketBadge.tsx` | Badge verde/amarillo/rojo en header | ✅ v1 |
| `hmi/src/services/socket.ts` | `auth.reconnect`, heartbeat `ping` 30 s, `connect_error` → logout | ✅ v2.1 |
| `hmi/src/utils/tagHistoryBackfill.ts` | Backfill 120 s al reconectar | ✅ v1 |
| Locales ES/EN | Eventos HMI + TLS + badge | ✅ v2.1 |

### 2.3 Evolución v1 → v2.1 (misma fecha)

| Capacidad | v1 (A−) | v2.1 (A+) |
|---|---|---|
| Registro sesiones | `dict` in-memory por worker | **`hmi_sessions` PostgreSQL** |
| Conteo `active_clients` | Por worker | **`COUNT(*)` global por `node_id`** |
| Token inválido | Fail-open (`username=unknown`) | **Fail-closed + evento rejected** |
| TLS Events | Agregado global sin IP | **Por IP, 5 min** |
| Heartbeat / cleanup | No | **ping 30 s + worker 60 s** |
| Handler `ping` | No | **Sí** |

---

## 3. Tabla `hmi_sessions` (estado global sin Redis)

```sql
-- Peewee crea esto vía create_tables; contrato lógico:
hmi_sessions (
  sid           VARCHAR(64) PRIMARY KEY,
  node_id       VARCHAR(64) NOT NULL,
  username      VARCHAR(64) NOT NULL,
  origin        VARCHAR(45) NOT NULL,
  area          VARCHAR(64) NOT NULL,
  connected_at  TIMESTAMPTZ NOT NULL,
  last_heartbeat TIMESTAMPTZ NOT NULL
);
-- Índice: (node_id, last_heartbeat)
```

| Operación | Cuándo | Carga típica |
|---|---|---|
| INSERT/UPSERT | connect válido | Esporádica |
| UPDATE | `ping` cada 30 s / cliente | Baja (10–20 clientes/edge) |
| DELETE | disconnect + cleanup | Esporádica |
| SELECT COUNT | connect + disconnect | Esporádica |

**Nota:** connect **requiere** PG disponible para upsert; si falla → reject (`session_store_unavailable`). Events siguen vía SAF si journal activo.

---

## 4. Modelo de eventos L3

Clasificación: **`HMI`**. FK: operador autenticado en connect OK; **`system`** en rejected/TLS.

| `message` | Cuándo | priority | criticity |
|---|---|---|---|
| `HMI client connected` | Primera conexión válida | 2 | 2 |
| `HMI client disconnected` | disconnect limpio | 3 | 3 |
| `HMI client reconnected` | `auth.reconnect=true` | 2 | 2 |
| `HMI client connection rejected` | Token inválido / PG sesiones no disponible | 3 | 4 |
| `HMI TLS handshake failure` | Fallo TLS por IP (rate 5 min) | 2 | 2 |

**Ejemplo description:**

```text
username=operator; origin=192.168.10.50; sid=Kx8f2Abc; edge=Intelcon.Line1 (edge-idf-01); active_clients=2; reason=transport close
```

Reglas: sin token en logs; clip 256; `journal_then_remote`; área = `node_area()`.

---

## 5. Arquitectura

### 5.1 SOLID

| Principio | Aplicación v2.1 |
|---|---|
| **S** | `hmi_session_store` (PG) ≠ `hmi_socket_audit` (Events) ≠ `hmi_tls_telemetry` (TLS) |
| **O** | Nuevas acciones → `_MESSAGE` sin cambiar handlers |
| **L** | Mismo contrato fail-safe que `opcua_audit`, `user_session_audit` |
| **D** | Reutiliza `persist_system_event`, `Api._resolve_session_user` |

### 5.2 Rendimiento

| Aspecto | Decisión |
|---|---|
| Hot path `on.tag` | Sin PG — sin cambios |
| Heartbeat | 1 UPDATE / 30 s / cliente |
| Cleanup | 1 DELETE batch / 60 s / worker |
| Backfill RT | 1 POST trends / reconnect (debounce 300 ms, rate 5 s) |

---

## 6. Correlación forense

Ver [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md).

| Síntoma | Eventos / datos | Acción |
|---|---|---|
| RT congelado, badge rojo | `disconnected` | Revisar red/VPN/firewall WS |
| Hueco curva + badge verde | `reconnected` | Normal; backfill si PG up |
| Cert no confiado | `HMI TLS handshake failure` + IP | Instalar CA en cliente |
| Vuelve al login tras abrir HMI | `connection rejected` | Re-autenticar; revisar sesión superseded |
| Conteo errado tras crash worker | Consultar `hmi_sessions`; esperar cleanup 2 min | Ops |

Consulta ops:

```sql
SELECT sid, username, origin, connected_at, last_heartbeat
FROM hmi_sessions WHERE node_id = '<AUTOMATION_NODE_ID>'
ORDER BY last_heartbeat DESC;
```

---

## 7. Hallazgos y residuales

| ID | Hallazgo | Estado v2.1 |
|---|---|---|
| **SKT-H1** | Sin handler disconnect | ✅ Cerrado |
| **SKT-H2** | Connect sin Events/IP/usuario | ✅ Cerrado |
| **SKT-H3** | Tracebacks TLS en log | ✅ Cerrado |
| **SKT-H4** | Conteo por worker | ✅ Cerrado — PG `hmi_sessions` |
| **SKT-H5** | Fail-open token | ✅ Cerrado — fail-closed |
| **SKT-H6** | TLS sin IP | ✅ Cerrado — por IP 5 min |
| **SKT-R1** | Connect requiere PG para sesión | **Aceptado** — fail-closed A+ |
| **SKT-R2** | Cierre pestaña sin HTTP logout | Por diseño ([AUDIT_LOGGING.md](./AUDIT_LOGGING.md) §2.5) |
| **SKT-R3** | Soak multi-worker 2-edge no ejecutado en planta | **Pendiente** CA-SKT-10/13 |

### 7.1 Criterios de aceptación

| ID | Criterio | Evidencia automática |
|---|---|---|
| CA-SKT-11 | Token inválido → reject + evento | ✅ `test_hmi_session_store` |
| CA-SKT-12 | Token válido → fila PG | ✅ `test_upsert_and_count` |
| CA-SKT-13 | Conteo global multi-worker | Manual 2 workers — **pendiente planta** |
| CA-SKT-14 | Heartbeat + cleanup 2 min | ✅ `test_touch_heartbeat`, `test_cleanup_stale_sessions` |
| CA-SKT-15 | TLS por IP rate-limit | ✅ `test_hmi_tls_telemetry` |
| CA-SKT-16 | HMI connect_error → logout | Manual |
| CA-SKT-17 | Runbook | ✅ `docs/hmi-connectivity-runbook.md` |
| CA-SKT-01…10 | Soak operativo | **Pendiente planta** |

Tests:

```bash
./venv/bin/python3 -m unittest automation.tests.test_hmi_session_store automation.tests.test_hmi_tls_telemetry -v
```

---

## 8. Veredicto

| Dimensión | Nota | Comentario |
|---|---|---|
| Trazabilidad L3 Socket.IO | **A+** | connect/disconnect/reconnect/reject + IP/usuario/línea/sid |
| Conteo global multi-worker | **A+** | `hmi_sessions` + COUNT(*) |
| Separación log vs evento | **A+** | Sin traceback L1; Events + DEBUG |
| Seguridad sesión socket | **A+** | Fail-closed token |
| TLS forense | **A** | Por IP; rate-limit 5 min (no cada handshake) |
| Resiliencia RT (HMI) | **A** | Badge + backfill 120 s |
| Cobertura tests | **A−** | 12 unit tests; falta e2e 2 workers en planta |

**Veredicto global: A+ (código)** — Especificación v2.1 implementada sin Redis. Cierre formal en planta tras CA-SKT-10 + CA-SKT-13 (soak 2-edge, 24 h).

---

## 9. Referencias

| Tema | Ruta |
|---|---|
| Spec v2.1 | [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md) |
| Runbook | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |
| Modelo PG | `automation/dbmodels/hmi_sessions.py` |
| Store PG | `automation/utils/hmi_session_store.py` |
| Auditoría Events | `automation/utils/hmi_socket_audit.py` |
| Cleanup worker | `automation/workers/hmi_session_cleanup.py` |
| Handlers Socket.IO | `automation/core.py` — `define_socketio` |
| TLS por IP | `automation/utils/hmi_tls_telemetry.py`, `gunicorn.conf.py` |
| HMI socket | `hmi/src/services/socket.ts` |
| Tests | `automation/tests/test_hmi_session_store.py`, `test_hmi_tls_telemetry.py` |

---

## 10. Changelog

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-08-19 AM | v1 | Badge, backfill RT, Events connect/disconnect in-memory, TLS agregado global |
| 2026-08-19 PM | v2.1 | PG `hmi_sessions`, fail-closed, heartbeat/cleanup, TLS/IP, runbook + spec 04; veredicto **A+** código |
