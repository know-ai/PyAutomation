# Arquitectura multi-edge

PyAutomation opera en modo multi-edge por defecto. Cada instancia de adquisición es un nodo con identidad propia. La API y el HMI permanecen disponibles si falta configuración; la hidratación y la adquisición se bloquean (fail-closed) hasta que existan `NODE_ID` y un área (`AUTOMATION_AREA` o `AUTOMATION_SEGMENT`).

## Variables obligatorias

| Variable | Obligatorio | Default | Rol |
|---|---|---|---|
| `AUTOMATION_MULTI_EDGE_ENABLED` | No | `true` | Activa partición, single-writer y fail-closed. `false` restaura el modo monolítico. |
| `AUTOMATION_NODE_ID` | Sí (si multi-edge está activo) | — | Identidad estable del edge. Máximo 64 caracteres. |
| `AUTOMATION_SEGMENT` | Sí (si multi-edge está activo; alias de `AREA`) | — | Clave de partición de línea (`Linea1`, `Linea2`, …). Es el nombre que ya usan las aplicaciones. |
| `AUTOMATION_AREA` | Alias de `SEGMENT` | — | Mismo valor. Si ambos existen, **deben coincidir**. |
| `AUTOMATION_MANUFACTURER` | No (alias de `SITE`) | — | Sitio / fabricante / cliente de planta. Es el nombre que ya usan las aplicaciones. |
| `AUTOMATION_SITE` | Alias de `MANUFACTURER` | — | Mismo valor. Si ambos existen, **deben coincidir**. |

No hace falta declarar `AREA` y `SEGMENT` a la vez, ni `SITE` y `MANUFACTURER`. En iDetectFugas basta `AUTOMATION_SEGMENT` y `AUTOMATION_MANUFACTURER`.

Los tags creados por API/HMI se cualifican con el área (`Linea1.FI_01`). Las alarmas de aplicación no: la frontera es el **tag asociado** (`area` + `owner_node`). iDetectFugas sigue usando `alarm.{máquina}.leak` y tags internos `{MANUFACTURER}.{SEGMENT}.{máquina}.*`.

Hay dos planos de datos:

| Plano | Qué | Filtro de área |
|---|---|---|
| Runtime / catálogo activo | CVT, alarmas activas, OPC, CRUD, Socket.IO `on.tag`/`on.alarm` | Obligatorio (cada edge solo opera su línea) |
| Histórico / gestión | AlarmSummary, Events, Logs, TagValue, Users | Global por defecto; `area` es opcional |

## Sesiones HMI / API (multi-edge)

Con PostgreSQL compartido, **no** se usa un único `Users.token` global para invalidar sesiones entre líneas.

| Aspecto | Comportamiento |
|---|---|
| Token API/HMI | Hash de sesión en memoria + fila en `user_api_sessions` (`token`, `username`, `node_id`, `area`). En multi-edge **no** se sobrescribe `Users.token` en PostgreSQL al hacer login |
| Login en un edge | Revoca solo tokens previos del **mismo** `AUTOMATION_NODE_ID` en `user_api_sessions`; otras líneas conservan su sesión |
| Login de usuarios | Read-Through al historiador si está vivo; `catalog.db` solo es fallback offline. Tras signup/password/rol se emite `pg_notify(pya_user_invalidate)` (y Redis Pub/Sub si hay `AUTOMATION_REDIS_URL`) para que los otros edges borren su fila local en <2 s |
| Socket.IO | Valida token vía `Api._resolve_session_user` — **no** compara `node_id` del token con el edge. El hot path connect/disconnect usa Redis (`hmi:sess:{sid}`) o memoria; PostgreSQL `hmi_sessions` es snapshot en background |
| `AUTOMATION_REDIS_URL` | URL del sidecar Redis **local al edge** (`redis://redis-session:6379/0`). Jamás un Redis de planta. Si falta o el sidecar cae, las sesiones HMI siguen en RAM |
| `AUTOMATION_APP_SECRET_KEY` | Solo firmas TPT (integraciones); debe ser idéntica en todos los edges si se usan TPT |
| TLS HMI | Fallos de handshake (`HMI TLS handshake failure`) son independientes de la sesión API; revisar certificado/clave en cada Moxa |

Tras desplegar esta versión, reiniciar cada edge para crear la tabla `user_api_sessions` (`create_tables=True` en arranque).

## Receta N-edge

1. Un PostgreSQL compartido para catálogo e histórico.
2. Un proceso (o contenedor) por línea, con `AUTOMATION_NODE_ID` y `AUTOMATION_SEGMENT` únicos.
3. Journal SAF local por nodo: `./db/saf/<node_id>/journal.db`.
4. Clientes OPC UA con `owner_node` igual al `NODE_ID` del edge que los abre.
5. Comprobar `/api/health/system`: `ACQUISITION_READY=true`, `NODE_ID`, `NODE_AREA`, `SAF_QUEUE_DEPTH` y `DB_CONNECTIONS_COUNT` ≤ 4 idle por edge.

Ejemplo:

```ini
# Edge A (nombres de aplicación; AREA/SITE son alias)
AUTOMATION_MULTI_EDGE_ENABLED=true
AUTOMATION_NODE_ID=edge-linea1
AUTOMATION_SEGMENT=Linea1
AUTOMATION_MANUFACTURER=Test

# Edge B
AUTOMATION_MULTI_EDGE_ENABLED=true
AUTOMATION_NODE_ID=edge-linea2
AUTOMATION_SEGMENT=Linea2
AUTOMATION_MANUFACTURER=Test
```

`application_name` de PostgreSQL queda `PyAutomationIO:<node_id>:<rol>` (máximo 63 caracteres).

## Rollback

1. Detener adquisición en todos los edges.
2. Arrancar una sola instancia con `AUTOMATION_MULTI_EDGE_ENABLED=false`.
3. No se infieren propietarios históricos: las columnas `area`/`owner_node` nulas permanecen nulas.
4. Restaurar el journal común `./db/saf/journal.db` si se usaba el layout legado.

## Evidencia CA-EDGE

| Criterio | Qué demuestra | Cómo verificar |
|---|---|---|
| CA-EDGE-1 | Tras reboot, el CVT no contiene tags de otra área | Suite `test_multi_edge_acceptance.TestAcceptanceCriteria.test_ca_edge_1_*` y reboot de un edge |
| CA-EDGE-2 | El edge no abre sesión OPC UA ajena | `test_ca_edge_2_*` y `test_opc_client_never_connects_for_foreign_owner` |
| CA-EDGE-3 | Samples trazables al nodo | `application_name` y `owner_node` en TagValue / `test_ca_edge_3_*` |
| CA-EDGE-4 | Caída de A: B sigue y no escribe tags de A | journals aislados + `test_ca_edge_4_*` |
| CA-EDGE-5 | Sin `NODE_ID`: no hay `read_all()` de tags/OPC | fail-closed en `connect_to_db` + `test_ca_edge_5_*` |
| CA-EDGE-6 | Homólogos cualificados coexisten | `Linea1.FI_01` y `Linea2.FI_01` + `test_ca_edge_6_*` |
| CA-EDGE-7 | Idle PG ≤ 4 por edge | `/api/health/system` → `DB_CONNECTIONS_EXPECTED_MAX` |
| CA-EDGE-8 | Runtime local no lista puntos ajenos; el histórico es de planta | CVT/activas/Socket.IO acotados + `test_ca_edge_8_*`; lecturas históricas sin filtro de área por defecto (`test_filter_by_is_plant_wide_*`) |

Integración 2-edge opt-in:

```bash
AUTOMATION_TWO_EDGE_IT=1 \
AUTOMATION_TWO_EDGE_EVIDENCE=/ruta/evidencia.txt \
python -m unittest automation.tests.test_multi_edge_acceptance.TestTwoEdgeLive
```

Soak 24 h (operación): dos edges, dos OPC UA, PostgreSQL compartido. No-Go ante escritura cruzada, sesión OPC ajena, crecimiento sostenido de `SAF_QUEUE_DEPTH`/`PENDING_ROWS` o contaminación del HMI/CVT.

Checklist operativo:

1. Arrancar Edge A (`Linea1`) y Edge B (`Linea2`) contra el mismo PostgreSQL.
2. Confirmar `/api/health/system`: `ACQUISITION_READY=true`, `DB_CONNECTIONS_COUNT` ≤ 4 idle, `SAF_QUEUE_DEPTH` estable.
3. Reboot de A: el CVT de A no lista `Linea2.*`; B sigue adquiriendo.
4. Caer OPC de A: A no abre el cliente de B; B no encola samples de A.
5. HMI de cada edge: CVT, alarmas activas, máquinas y clientes OPC solo del área local. Resumen de alarmas, eventos, logs, tendencias y datalogger ven toda la planta (selector de área opcional).
6. Tras 24 h, `PENDING_ROWS` no crece de forma sostenida y no hay writes cruzados en TagValue (`owner_node`).

## Sincronización NTP (multi-edge)

Todos los edges deben compartir la **misma epoch UTC** para correlacionar alarmas, TagValue y eventos en el historiador compartido.

| Capa | Responsable | Acción |
|---|---|---|
| Disciplina | SO del host (`chrony` / `w32time`) | Mismos 2–3 servidores NTP OT en todos los edges |
| Verificación | PyAutomation `NtpMonitorWorker` | Mismos servidores en HMI → Sincronización NTP |
| Red | VLAN OT | UDP **123** saliente desde cada edge; IPv4/IPv6 dual-stack soportado |

Checklist NTP por edge:

1. Host sincronizado (`chronyc tracking` o `w32tm /query /status`).
2. HMI → Sincronización NTP en verde; `|offset_ms| < 50` en condiciones normales.
3. `GET /api/health/system` → bloque `clock.synced=true`.
4. Mismos servidores que el resto de la planta (no `pool.ntp.org` en producción).

Runbook detallado: [ntp-deployment.md](./ntp-deployment.md). Auditoría: [audits/AUDIT_NTP_TIME_SYNC.md](../audits/AUDIT_NTP_TIME_SYNC.md).

## Dashboard de rendimiento por edge

Cada proceso tiene su propio `MetricsSamplerWorker` y su propio `GET /api/health/node`. El snapshot es **local al nodo**: CPU, disco, HTTP, cola SAF, clientes HMI (`HMI_ACTIVE_CLIENTS` = `SCARD` de Redis o conteo en memoria, filtrado por `node_id`) y adquisición de esa instancia. Linea1 no muestra métricas de Linea2.

La pantalla HMI `/performance` (roles admin/supervisor/sudo) hace poll de 3 s contra el edge al que está conectada. Runbook: [node-performance-runbook.md](./node-performance-runbook.md). Spec: [05-NODE-PERFORMANCE-DASHBOARD.md](../specs/05-NODE-PERFORMANCE-DASHBOARD.md).
