# Auditoría compacta: trazabilidad de conectividad Socket.IO HMI

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) + Gunicorn/gevent |
| **Alcance** | Ciclo de vida Socket.IO (connect / disconnect / reconnect); telemetría TLS; conteo multi-worker; **LED RT del header**; correlación freeze de tendencias vs estado de transporte |
| **Fecha** | 2026-08-24 (v2.3 — timeouts ≤45s + watchdog frescura) · v2.2 gap documentado · base v2.1 2026-08-19 |
| **Spec** | [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md) v2.1 + especificación timeouts/watchdog 2026-08-24 |
| **Runbook** | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |
| **Complementa** | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) §2 Events, [AUDIT_HMI.md](./AUDIT_HMI.md) §2 socket/EventBus, [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_DB.md](./AUDIT_DB.md) |
| **Veredicto vigente** | **A** transporte (detección ≤45s) · **A−** plano de datos (watchdog `on.tag` 5 s → LED amarillo) — soak planta pendiente |
| **Clasificación** | Auditoría operativa · conectividad HMI · trazabilidad multi-equipo · UX indicadores |

---

## 0. Respuesta directa (actualizada 2026-08-24)

| Pregunta | Respuesta |
|---|---|
| ¿Connect/disconnect Socket se registran en **Events**? | **Sí** — `HMI client connected` / `disconnected` / `reconnected` / `connection rejected` |
| ¿Se identifica el cliente? | **Sí** — `username=`, `origin=`, `sid=`, `edge=` |
| ¿El LED **RT** del header refleja desconexión Socket.IO? | **Sí (transporte)** + **watchdog de frescura**: sin `on.tag` ≥5 s con socket up → LED amarillo (`data-stale`). |
| ¿Por qué la tendencia RT puede congelarse con LED RT verde? | Mitigado por **SKT-H7 cerrado (código)**: watchdog `useDataFreshness`. Validar en planta (tags lentos pueden generar warn legítimo). |
| ¿Hay watchdog de “último `on.tag`”? | **Sí** — `socketService.onTagActivity` + `useDataFreshness` (umbral 5 s). |
| ¿Toasts de pérdida/recuperación? | **Sí**, con debounce **2 s** (`useSocketConnectionNotifications`). |
| ¿Token inválido? | Fail-closed + evento `connection rejected` + logout HMI. |

### 0.1 Tres capas de conectividad HMI

| Capa | Qué ocurre | Trazabilidad L3 Events | Indicador HMI |
|---|---|---|---|
| **A — TLS / WSGI** | Cert, HTTP vs TLS, EOF | `"HMI TLS handshake failure"` — 1/IP/5 min | Ninguno dedicado |
| **B — Transporte Socket.IO** | connect / disconnect / reconnect / reject | 1 evento por sesión (`HMI`) | LED **RT** (header) |
| **C — Plano de datos RT** | Emisión `on.tag` / `on.alarm` / CVT | Sin evento L3 de stall (aún) | LED **RT** amarillo si silence ≥5 s; banner tendencias |
| **D — HTTP sesión / BD** | login, health probe | `User logged in\|out`; health HTTP | LED **BD** (independiente) |

### 0.2 Flujo operativo (transporte)

```
Login HTTP     → Event: User logged in
Connect socket → UPSERT hmi_sessions + Event: connected + LED RT verde
Heartbeat 30s  → HMI emit "ping" → UPDATE last_heartbeat (sin evento, sin LED)
Disconnect     → DELETE hmi_sessions + Event: disconnected
                 → LED RT amarillo (reconnecting) hasta 30 s
                 → LED RT rojo (disconnected) si outage ≥ 30 s
Reconnect      → Event: reconnected + GET /history/backfill (ventana 2–5 min, ISO UTC) + LED verde
Token inválido → Event: rejected + logout HMI
```

### 0.3 Flujo de datos RT (independiente del LED)

```
Adquisición / OPC / workers → CVT.set_value → sio.emit("on.tag")
  → HMI socketService.onTagUpdate → buffer 250 ms → Redux tagHistory
  → StripChart lee tagHistory

Si este pipeline se detiene y Engine.IO sigue vivo → curva plana + LED RT verde.
```

---

## 1. Por qué importa el síntoma «curva congelada / LED verde»

| Riesgo | Con solo v2.1 (transporte) | Con gap SKT-H7 |
|---|---|---|
| Operador asume “RT OK” porque LED verde | Correcto solo si el socket está up | **Falso positivo** si CVT/OPC/fanout fallan |
| Correlacionar freeze con Events | Busca `disconnected` | Puede **no** haber disconnect |
| Distinguir BD down vs socket down | LED BD vs LED RT separados | Correcto para capas B/D; **no** cubre capa C |
| Diagnóstico en planta | “¿Se cayó el socket?” | Preguntar también: ¿siguen llegando `on.tag`? ¿OPC/adquisición? |

---

## 2. Inventario de código (evidencia 2026-08-24)

### 2.1 Backend — sesiones + auditoría + fanout

| Artefacto | Rol | Estado |
|---|---|---|
| `automation/dbmodels/hmi_sessions.py` | Tabla sesiones HMI | ✅ |
| `automation/utils/hmi_session_store.py` | upsert / remove / count / heartbeat / cleanup | ✅ |
| `automation/utils/hmi_socket_audit.py` | Events + connect fail-closed | ✅ |
| `automation/workers/hmi_session_cleanup.py` | Huérfanas > 2 min sin heartbeat | ✅ |
| `automation/core.py` `define_socketio` | `ping_interval=15`, `ping_timeout=30` (s) → detección ≤45 s; handlers connect/disconnect/ping | ✅ v2.3 |
| `automation/tags/cvt.py` | `sio.emit("on.tag", …)` en hot path de valor | ✅ (capa C) |
| `automation/utils/hmi_tls_telemetry.py` | TLS por IP | ✅ |

### 2.2 HMI — LED RT y fases

| Artefacto | Rol | Estado |
|---|---|---|
| `hmi/src/services/socket.ts` | Fases transporte; `DISCONNECTED_PHASE_MS=15_000`; reconnect 500–5000 ms; `timeout=15_000`; `onTagActivity` / `DATA_STALE_MS=5_000`; heartbeat app 15 s | ✅ v2.3 |
| `hmi/src/hooks/useSocketConnection.ts` | Suscribe `onConnectionChange` → fase | ✅ |
| `hmi/src/hooks/useDataFreshness.ts` | Watchdog: sin `on.tag` ≥5 s → `dataStale` | ✅ v2.3 |
| `hmi/src/hooks/useSystemHealth.ts` | `socketHealth` = transporte ∪ frescura; `transportHealth` separado; `rtReason` | ✅ v2.3 |
| `hmi/src/components/SocketBadge.tsx` | LED header **RT** (ok/warn/alarm) + tooltip data-stale | ✅ v2.3 |
| `hmi/src/hooks/useSocketConnectionNotifications.ts` | Toasts pérdida/recuperación, debounce **2 s** | ✅ |
| `hmi/src/hooks/useSocket.ts` | Suscribe `on.tag` → Redux; backfill al reconnect vía `/history/backfill` | ✅ v2.4 |
| `hmi/src/utils/tagHistoryBackfill.ts` | `from=max(último punto, now−ventana)`; ventana = time span charts | ✅ v2.4 |
| `hmi/src/services/history.ts` | Cliente `GET /history/backfill` | ✅ v2.4 |
| `automation/modules/history/` | Endpoint backfill TagValue → ISO UTC | ✅ v2.4 |
| `hmi/src/pages/RealTimeTrends.tsx` | Banner transporte + banner `dataStalled` | ✅ v2.3 |
| `hmi/src/components/StripChart.tsx` | Serie desde `tagHistory` Redux | ✅ sin watchdog propio |
| Locales `socket.*` | Tooltips LED / toasts | ✅ |
| CSS `.socket-badge--ok\|warn\|alarm` | Verde / amarillo / rojo | ✅ |

### 2.3 Evolución

| Capacidad | v2.1 | v2.2 (esta auditoría) |
|---|---|---|
| Events connect/disconnect | ✅ | Sin cambio |
| LED RT por fase de transporte | ✅ | **Documentado** mapeo + umbrales |
| Separación LED RT vs LED BD | ✅ | Confirmado |
| Watchdog frescura `on.tag` → LED | ❌ | **✅ v2.3** (`useDataFreshness`, umbral 5 s) |
| Evento L3 “RT data stalled” | ❌ | **Gap abierto** (solo UX LED/banner) |

---

## 3. Configuración del LED RT (header)

### 3.1 Cadena de estado

```
Engine.IO events (connect / disconnect / connect_error / reconnect_attempt)
  → SocketService.computePhase()
  → emitConnection → useSocketConnection()
  → useSystemHealth().socketStatus / socketHealth
  → SocketBadge (clase CSS + tooltip i18n)
```

`HeaderClock` monta `SocketBadge` junto al LED BD (`DatabaseStatus`). Son **independientes**.

### 3.2 Mapa fase → LED

| `SocketConnectionPhase` | `socketHealth` | CSS | Color | Tooltip (ES) |
|---|---|---|---|---|
| `connected` | `connected` | `socket-badge--ok` | Verde | «Socket HMI conectado — datos en tiempo real activos» |
| `connecting` | `reconnecting` | `socket-badge--warn` | Amarillo | «Socket HMI conectando…» |
| `reconnecting` | `reconnecting` | `socket-badge--warn` | Amarillo | «Socket HMI reconectando…» |
| `disconnected` | `disconnected` | `socket-badge--alarm` | Rojo | «Socket HMI desconectado — reintentando…» |

**Nota UX:** el tooltip de “datos en tiempo real activos” es **aspiracional**: el código solo garantiza socket transport connected, no llegada de muestras.

### 3.3 Umbrales y temporizadores (código actual)

| Constante / config | Valor | Efecto en LED / UX |
|---|---|---|
| `SocketService.DISCONNECTED_PHASE_MS` | **15 000 ms** | Tras `disconnect`, amarillo hasta 15 s; luego rojo |
| Toast debounce | **2 000 ms** | Blips < 2 s no muestran toast de pérdida |
| Heartbeat HMI → backend `ping` | **15 s** | Actualiza `hmi_sessions.last_heartbeat`; no cambia el LED |
| Backend `ping_interval` | **15 s** | Engine.IO ping servidor→cliente |
| Backend `ping_timeout` | **30 s** | Detección peer muerto ≤ **45 s** (15+30) |
| Cliente `timeout` | **15 000 ms** | Timeout de conexión inicial |
| Reconnect delay | **500–5000 ms** + jitter | Reintentos más agresivos (≤2 s típico) |
| `DATA_STALE_MS` / watchdog | **5 000 ms** | Socket up + silencio `on.tag` → LED amarillo + banner |
| Buffer Redux tags | **250 ms** | Agrupa `on.tag` |

### 3.4 Banner en RealTimeTrends

Solo se muestra si `socketStatus !== "connected"`:

- `disconnected` → alerta danger (`realTimeTrends.waitingSocket`)
- `reconnecting` / `connecting` → alerta warning

Si el socket sigue `connected` y no hay `on.tag`, **no hay banner** y la curva se queda en el último valor histórico.

---

## 4. Tabla `hmi_sessions` (estado global sin Redis)

Sin cambios respecto a v2.1. Ver §3 del audit histórico: connect requiere PG; heartbeat 30 s; cleanup 60 s / stale 2 min.

```sql
SELECT sid, username, origin, connected_at, last_heartbeat
FROM hmi_sessions WHERE node_id = '<AUTOMATION_NODE_ID>'
ORDER BY last_heartbeat DESC;
```

---

## 5. Modelo de eventos L3 (transporte)

Clasificación: **`HMI`**.

| `message` | Cuándo | priority | criticity |
|---|---|---|---|
| `HMI client connected` | Primera conexión válida | 2 | 2 |
| `HMI client disconnected` | disconnect limpio | 3 | 3 |
| `HMI client reconnected` | `auth.reconnect=true` | 2 | 2 |
| `HMI client connection rejected` | Token inválido / store no disponible | 3 | 4 |
| `HMI TLS handshake failure` | Fallo TLS por IP (rate 5 min) | 2 | 2 |

**No existen** mensajes L3 del tipo:

- `HMI RT data stalled`
- `HMI on.tag silence`
- `HMI CVT fanout stopped`

---

## 6. Diagnóstico: tendencia congelada vs LED RT

### 6.1 Matriz de síntomas

| Síntoma HMI | LED RT | Events esperados | Causa más probable |
|---|---|---|---|
| Curva plana, LED **verde** | `connected` | Ningún `disconnected` reciente | **SKT-H7** — capa C: OPC/adquisición/CVT sin emitir; o half-open aún no detectado por Engine.IO |
| Curva plana, LED **amarillo** ≤30 s | `reconnecting` | Posible `disconnected` | Outage corto o en curso; operador puede no notar “alarma” |
| Curva plana, LED **rojo** ≥30 s | `disconnected` | `HMI client disconnected` | Transporte caído — esperado |
| Hueco + reanudación, LED verde de nuevo | connected tras reconnect | `reconnected` | Normal; `GET /history/backfill` si PG up |
| Logout inesperado | — | `connection rejected` | Token / sesión |

### 6.2 Cómo validar en planta (checklist)

1. **DevTools → Network → WS**: ¿el frame Socket.IO sigue abierto? ¿llegan paquetes `2`/`3` (ping/pong Engine.IO)?
2. **Consola / Redux**: ¿entran payloads `on.tag` mientras la curva está plana?
3. **Events** (mismo edge, ventana del freeze): ¿hay `HMI client disconnected`?
4. **`hmi_sessions`**: ¿`last_heartbeat` se actualiza cada ~30 s?
5. **Adquisición / OPC**: ¿el tag cambia en CVT/backend aunque la HMI no pinte?
6. **LED BD**: independiente; puede estar rojo (BD down) con LED RT verde y curvas vivas (valores desde memoria CVT).

### 6.3 Por qué el LED “no se activa” en el caso reportado

Hallazgo operativo confirmado por código:

1. El LED **solo** escucha fase de transporte (`socket.ts` → `useSystemHealth` → `SocketBadge`).
2. Las tendencias leen **historial Redux** alimentado por `on.tag`, no por el LED.
3. Si Engine.IO no dispara `disconnect` (conexión half-open, servidor aún hace ping, proceso gevent vivo pero sin emitir tags), la fase permanece `connected` → LED verde.
4. Incluso con `disconnect` real, los primeros **30 s** el LED es **amarillo** (`reconnecting`), no rojo; toasts solo tras **2 s**.
5. El copy del tooltip («datos en tiempo real activos») **sobrepromete** respecto a lo instrumentado.

---

## 7. Hallazgos y residuales

| ID | Hallazgo | Estado |
|---|---|---|
| **SKT-H1…H6** | Disconnect, Events, TLS, conteo, fail-closed, TLS/IP | ✅ Cerrados (v2.1) |
| **SKT-H7** | LED RT no reflejaba silencio de `on.tag` | **✅ Cerrado (código v2.3)** — watchdog 5 s; soak tags lentos pendiente |
| **SKT-H8** | Tooltip i18n “datos RT activos” engañoso | **Mitigado** — `badgeDataStale` cuando aplica; copy connected sigue siendo aspiracional si tags fluyen |
| **SKT-R1** | Connect requiere PG para sesión | Aceptado |
| **SKT-R2** | Cierre pestaña sin HTTP logout | Por diseño |
| **SKT-R3** | Soak multi-worker 2-edge | Pendiente planta |
| **SKT-R4** | Detección Engine.IO peer muerto | **Mejorado** — ≤45 s (antes ~85 s) |

### 7.1 Criterios de aceptación (transporte — sin cambio)

| ID | Criterio | Evidencia |
|---|---|---|
| CA-SKT-11…17 | Reject, PG, heartbeat, TLS, logout, runbook | Ver v2.1 |
| CA-SKT-01…10 | Soak operativo | Pendiente planta |

### 7.2 Criterios propuestos (plano de datos — pendientes de implementación)

| ID | Criterio | Estado |
|---|---|---|
| **CA-SKT-18** | Sin `on.tag` ≥5 s con socket connected → LED warn + banner | ✅ código `useDataFreshness` / RealTimeTrends |
| **CA-SKT-19** | Evento L3 / métrica `last_on_tag_age_ms` | **Pendiente** |
| **CA-SKT-20** | Tooltip distingue socket up vs datos fluyendo | ✅ `badgeDataStale` |
| **CA-SKT-21** | Detección transporte ≤45 s (`ping_interval=15` + `ping_timeout=30`) | ✅ `core.py` |
| **CA-SKT-22** | Reconnect delay 500–5000 ms | ✅ `socket.ts` |

Tests actuales (transporte):

```bash
./venv/bin/python3 -m unittest automation.tests.test_hmi_session_store automation.tests.test_hmi_tls_telemetry -v
```

No hay tests HMI automatizados que fallen si `on.tag` deja de llegar con fase `connected`.

---

## 8. Veredicto

| Dimensión | Nota | Comentario |
|---|---|---|
| Trazabilidad L3 Socket.IO (transporte) | **A+** | connect/disconnect/reconnect/reject + IP/usuario/sid |
| Conteo global multi-worker | **A+** | `hmi_sessions` |
| LED RT vs LED BD | **A** | Separados correctamente |
| Fidelidad LED RT ↔ “hay datos RT” | **A−** | Watchdog 5 s (SKT-H7); tags muy lentos pueden warn |
| Resiliencia UX (fases 15 s, toasts 2 s, detect ≤45 s) | **A** | Timeouts v2.3 |
| Cobertura tests plano datos | **C** | Sin e2e stall automatizado |

**Veredicto global v2.3: A (transporte) / A− (RT completo en código)** — Timeouts Engine.IO 15/30 s y watchdog de frescura implementados. Cierre formal tras soak planta (falsos positivos por tags lentos + CA-SKT-10/13).

---

## 9. Referencias

| Tema | Ruta |
|---|---|
| Spec v2.1 | [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md) |
| Runbook | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |
| Handlers Socket.IO | `automation/core.py` — `define_socketio` |
| Fanout tags | `automation/tags/cvt.py` — `emit("on.tag")` |
| Fases + umbrales | `hmi/src/services/socket.ts` |
| Watchdog frescura | `hmi/src/hooks/useDataFreshness.ts` |
| LED header | `hmi/src/components/SocketBadge.tsx` |
| Salud agregada | `hmi/src/hooks/useSystemHealth.ts` |
| Pipeline RT → Redux | `hmi/src/hooks/useSocket.ts` |
| Tendencias | `hmi/src/pages/RealTimeTrends.tsx`, `StripChart.tsx` |
| Sesiones / Events | `hmi_session_store.py`, `hmi_socket_audit.py` |

---

## 10. Changelog

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-08-19 AM | v1 | Badge, backfill RT, Events connect/disconnect in-memory, TLS agregado |
| 2026-08-19 PM | v2.1 | PG `hmi_sessions`, fail-closed, heartbeat/cleanup, TLS/IP; veredicto A+ código transporte |
| 2026-08-24 | v2.2 | Documenta gap LED vs frescura (SKT-H7); umbrales legacy 25/60 ≈85 s |
| 2026-08-24 | **v2.3** | `ping_interval=15`/`ping_timeout=30`; reconnect 500–5s; `DISCONNECTED_PHASE_MS=15s`; watchdog `useDataFreshness` 5 s; cierra SKT-H7 en código |
| 2026-08-24 | **v2.4** | `GET /api/history/backfill` (ISO UTC); ventana = time span tendencia (2–5 min); merge dedupe por epoch ms; corrige huecos por formato MM/DD vs ISO |

---

## 11. Notas operativas

- **python-socketio** usa `ping_interval` / `ping_timeout` en **segundos** (15 y 30), no milisegundos.
- El cliente mantiene `autoConnect: false` (token antes de conectar); no se adoptó `autoConnect: true` de la spec de ejemplo.
- Tags con periodo de actualización >5 s dispararán LED amarillo de forma esperada; si molesta en planta, subir `DATA_STALE_MS` o armar el watchdog solo para tags suscritos a stripcharts.
