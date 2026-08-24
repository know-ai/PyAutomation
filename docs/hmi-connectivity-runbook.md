# Runbook: conectividad HMI (Socket.IO + TLS)

Guía operativa para diagnosticar clientes HMI desconectados, reconexiones y fallos TLS en edges PyAutomationIO.

## Síntomas rápidos

| Síntoma | Badge header | Adquisición / SAF | Causa probable |
|---|---|---|---|
| Gráficos RT congelados | SKT rojo / amarillo | OK | Socket.IO caído; revisar Events `HMI client disconnected` |
| BD roja pero SKT verde | BD rojo, SKT verde | OK | Historiador caído; tiempo real (CVT) sigue; SAF acumula |
| No carga HMI / certificado | — | OK | TLS; revisar `HMI TLS handshake failure` |
| Login OK pero vuelve al login | — | OK | Token rechazado en connect; evento `HMI client connection rejected` |
| Curva con hueco breve | Verde tras pausa | OK | Reconnect + backfill historiador (120 s) |

## Dónde mirar

1. **HMI → Events** — filtrar clasificación `HMI` o mensajes:
   - `HMI client connected`
   - `HMI client disconnected`
   - `HMI client reconnected`
   - `HMI client connection rejected`
   - `HMI TLS handshake failure`
2. **Campo description** — patrones:
   - `username=` operador
   - `origin=` IP cliente
   - `sid=` sesión Socket.IO
   - `edge=` línea/nodo
   - `active_clients=` conteo global (PostgreSQL `hmi_sessions`)
   - `reason=` motivo (disconnect / rechazo)
3. **Indicadores header** — independientes:
   - **SKT** (Socket.IO): conexión WebSocket con **este edge**; alimenta CVT, alarmas activas y tendencias RT.
   - **BD** (Base de datos): sonda `GET /api/health/db` al historiador remoto; no debe apagarse el SKT cuando solo falla la BD.
4. **Badge Socket** (header HMI) — estado **local** del navegador; no sustituye Events del servidor.

## Conteo global de clientes

El edge mantiene filas en **`hmi_sessions`** (PostgreSQL):

- **Insert** en cada connect válido
- **Delete** en disconnect
- **Heartbeat** cada 30 s (`ping` desde HMI)
- **Limpieza** cada 60 s: filas con `last_heartbeat` > 2 min (workers caídos)

Consulta manual (ops):

```sql
SELECT sid, username, origin, area, connected_at, last_heartbeat
FROM hmi_sessions
WHERE node_id = '<AUTOMATION_NODE_ID>'
ORDER BY last_heartbeat DESC;
```

## Troubleshooting por escenario

### A. Cliente remoto con certificado autofirmado

- **Events:** `HMI TLS handshake failure` con `origin=<IP>`
- **Logs:** sin traceback (suprimido en gunicorn)
- **Acción:** instalar CA de planta en el navegador o usar cert firmado por PKI interna
- Rate-limit: 1 evento / IP / 5 min

### B. Red intermitente (VPN, Wi‑Fi OT)

- **Events:** pareja `disconnected` → `reconnected` mismo `username` + `origin`
- **HMI:** badge amarillo → verde; StripChart rellena ~120 s si historiador responde
- **Acción:** revisar latencia/red; adquisición no se detiene

### C. Token inválido o sesión superseded

- **Events:** `HMI client connection rejected` (`reason=invalid_token` o `session_superseded`)
- **HMI:** toast + redirección a login
- **Acción:** operador debe volver a autenticarse; segundo login en otra estación revoca la anterior

### D. Historiador PostgreSQL caído

- **Connect:** puede rechazarse (`reason=session_store_unavailable`) — fail-closed A+
- **Events / SAF:** journal local conserva eventos hasta reconexión PG
- **Acción:** restaurar historiador; no vaciar journal SAF

### E. Worker Gunicorn caído sin disconnect limpio

- Filas huérfanas en `hmi_sessions` expiran a los **2 min** sin heartbeat
- **Events:** puede faltar `disconnected` para ese `sid`; cleanup corrige conteo

## Variables de entorno

| Variable | Default | Efecto |
|---|---|---|
| `AUTOMATION_HMI_TLS_IP_EVENT_WINDOW_S` | 300 | Ventana rate-limit TLS por IP (segundos) |

## Pruebas de humo (post-despliegue)

1. Login → ver `HMI client connected` con IP correcta
2. Abrir segunda estación → `active_clients=2`
3. Cerrar pestaña → `disconnected`, conteo baja
4. Simular corte red 30 s → `reconnected`
5. Token revocado → `connection rejected` + login HMI

## Referencias

- Auditoría: [audits/AUDIT_HMI_SOCKET_TRACEABILITY.md](../audits/AUDIT_HMI_SOCKET_TRACEABILITY.md)
- Spec: [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md)
- Events (dev): [docs/Developments_Guide/API/events.md](../docs/Developments_Guide/API/events.md)
