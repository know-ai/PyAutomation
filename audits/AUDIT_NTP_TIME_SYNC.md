# Auditoría compacta: sincronización NTP y reloj de sistema en despliegues multi-edge

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) + imagen Docker |
| **Alcance** | Disciplina del reloj del SO/host; verificación periódica; visibilidad operativa; correlación temporal entre N edges contra un historiador compartido |
| **Fecha** | 2026-08-19 — evidencia de código y contenedor |
| **Complementa** | [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) (presentación IANA), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) §3 («tiempo» en backlog de planta), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) (timestamps UTC en journal), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) (alarma de sistema) |
| **Veredicto vigente** | **F** respecto a sincronización de reloj. PyAutomation **asume** un reloj correcto del SO; no hay cliente/monitor NTP, ni API, ni HMI, ni alarma, ni health. `AUDIT_TIMEZONE` cerró **presentación** UTC/planta; **no** cerró **disciplina** ni **verificación** del reloj |
| **Clasificación** | Auditoría de arquitectura temporal · multi-edge · operación 24/7 |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-19) |
|---|---|
| ¿En qué nivel estamos con NTP / sync multi-edge? | **Nivel 0 — inexistente en producto.** Multi-edge Fase 1 particiona I/O y ownership; **no** garantiza que Edge A y Edge B compartan la misma epoch UTC dentro de una ventana aceptable |
| ¿Cada PyAutomation debe tener un **cliente NTP** apuntando al mismo servidor? | **No como disciplinador dentro del proceso Python.** La disciplina del reloj es responsabilidad del **SO/host** (chrony, systemd-timesyncd, NTP del hipervisor). **Sí:** todos los edges de planta deben usar **las mismas fuentes NTP** (idealmente 2–3 servidores Stratum 1–2 de la OT, no `pool.ntp.org` en producción) |
| ¿PyAutomation debe implementar algo? | **Sí, pero como monitor y visibilidad**, no como reemplazo de chrony: sonda SNTP/NTP ligera, métricas, alarma BOOL, sección en Configuración, evento de auditoría y agregación en health multi-edge |
| ¿Scheduler no bloqueante configurable? | **Sí, recomendado.** Hilo/worker dedicado o tick en `LoggerWorker` con probe UDP en **threadpool** (patrón `ping_throwaway` / probes DB). Intervalo configurable (p. ej. 3600 s por defecto, mínimo 60 s). **No** usar el hot path OPC/CVT |
| ¿Estrategia clase mundial / grado nuclear? | **Capas:** (1) PTP/IEEE 1588 o NTP Stratum bajo en red OT; (2) chrony en host con `makestep` acotado; (3) contenedor hereda reloj del host; (4) PyAutomation **verifica** offset y eleva alarma; (5) historiador correlaciona por `node_id` + timestamp; (6) consola central agrega salud temporal de todos los edges |

### 0.1 Distinción crítica: «Hora Única» ≠ «Reloj sincronizado»

| Capacidad | [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) | Esta auditoría |
|---|---|---|
| Almacenar en UTC | ✅ | Prerrequisito |
| Mostrar planta vs local en HMI | ✅ | Independiente |
| Disciplinar el reloj del edge | ❌ | **Objetivo** |
| Detectar deriva / salto de reloj | ❌ | **Objetivo** |
| Alarmar operador si Δ > umbral | ❌ | **Objetivo** |
| Evidencia en despliegue multi-edge | ❌ | **Objetivo** |

Un edge con reloj adelantado 45 s **sigue guardando «UTC»** en TagValue, pero es **UTC incorrecto**. Dos edges desincronizados producen historiales **no correlacionables** en el mismo PostgreSQL aunque la partición multi-edge sea correcta.

---

## 1. Por qué importa en multi-edge

Escenario: Edge A (`edge-linea1`) y Edge B (`edge-linea2`), historiador compartido, ~20 tags/línea, detección iDetectFugas con timestamps de alarma y TagValue en ms.

```
Edge A (reloj +30 s)          Historiador PG          Edge B (reloj OK)
     │                              │                        │
     │  TagValue t=10:00:30Z        │   TagValue t=10:00:00Z │
     └──────────────────────────────┼────────────────────────┘
                                    │
                    El operador ve eventos «en el futuro» mezclados
                    con eventos correctos; correlación de fuga falla
```

| Riesgo | Sin NTP verificado | Con estrategia propuesta |
|---|---|---|
| Correlación cross-line en trends/alarms | ❌ Sesgo invisible | ✅ Δ offset expuesto por nodo |
| SAF / exact-once `(tag_id, timestamp)` | Colisiones o orden invertido si salto grande | ✅ Detección de salto → alarma + evento |
| `machine.cycle_timestamp` / LDS | Ventanas de detección desalineadas entre líneas | ✅ Misma epoch en todos los edges |
| Cumplimiento / auditoría | Sin evidencia de sync | ✅ Log + Events + health exportable |
| Fail-closed multi-edge | Solo identidad de nodo | Opcional: **fail-closed adquisición** si `\|offset\| > T_critical` (política de planta) |

[AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) ya señala: *«El aislamiento de planta (red, BD, **tiempo**, operación 24/7) no.»* Esta auditoría cierra el gap **tiempo**.

---

## 2. Inventario de código (evidencia 2026-08-19)

### 2.1 Búsqueda explícita NTP / chrony / timesync

| Artefacto | Resultado |
|---|---|
| `grep -ri ntp\|chrony\|timesync` en repo | **0** referencias productivas (solo bundles JS minificados) |
| `Dockerfile` | No instala `chrony`, `ntp`, `systemd-timesyncd`; no documenta sync |
| `healthcheck.py` | Solo HTTP `/api/health/ping`; **no** comprueba reloj |
| `/api/health/system` | RSS, OPC, SAF, `NODE_*`, timing SM; **sin** `CLOCK_*` / `NTP_*` |
| `Settings` API / HMI | Logger, logs, backup, apariencia, DB; **sin** sección NTP |
| Tests | **Cero** `test_ntp_*` / `test_clock_*` |
| Env vars | `AUTOMATION_TIMEZONE` (IANA presentación); **no** `AUTOMATION_NTP_*` |

### 2.2 De dónde sale el tiempo hoy

| Origen | Mecanismo | Dependencia del reloj SO |
|---|---|---|
| OPC UA DAS | `SourceTimestamp` → `ensure_utc`; fallback `datetime.now(pytz.utc)` | Fallback **sí**; fuente de campo puede traer su propio reloj |
| DAQ / tags internos | `datetime.now(timezone.utc)` en varios caminos | **Sí** |
| State machines | `quantize_datetime_ms(datetime.now(timezone.utc))` | **Sí** |
| SAF / TagValue | epoch ms UTC en journal | **Sí** |
| Alarmas conexión | `datetime.now(timezone.utc)` | **Sí** |
| Eventos / bitácora | timestamps al persistir | **Sí** |
| HMI header clock | Hora del **navegador** (cliente) | **No** es reloj del edge |

**Conclusión:** PyAutomation es un **consumidor pasivo** del reloj del sistema. No valida ni corrige.

### 2.3 Imagen Docker

| Aspecto | Estado | Riesgo |
|---|---|---|
| Reloj del contenedor | Hereda del host Linux (namespace `TIME` compartido por defecto) | Si el **host** está mal, el contenedor también |
| `--privileged` / `SYS_TIME` | No requerido ni documentado | Correcto: la app **no** debe llamar `settimeofday` |
| TZ del contenedor | No fijado en Dockerfile | OK para UTC lógico; no sustituye NTP |

---

## 3. Estándares de referencia (grado industrial / nuclear)

| Estándar / práctica | Relevancia |
|---|---|
| **IEC 62439-3 / IEEE 1588 PTP** | Sub-ms en buses de proceso; overkill para muchos SCADA, obligatorio en algunas nucleares |
| **RFC 5905 NTPv4** | Sync ms–sub-ms con Stratum 1–2 en LAN OT |
| **SNTP (RFC 4330)** | Sonda ligera **solo lectura** — adecuada para monitor PyAutomation |
| **ISA-95 / IEC 62264** | Eventos L2/L3 deben ser ordenables en línea de tiempo de planta |
| **ISA-18.2** | Marca temporal inequívoca en alarmas |
| **NERC CIP / IEC 62443** | Servidores NTP en zona OT; no depender de Internet en producción |
| **Vendor SCADA (PI, Ignition, WinCC)** | NTP en SO + indicador de sync en consola; la app **no** reemplaza chrony |

### 3.1 Objetivos numéricos recomendados (planta típica multi-edge)

| Clase | \|offset\| vs NTP planta | \|offset\| entre edges | Acción |
|---|---|---|---|
| **Normal** | ≤ 50 ms | ≤ 100 ms | Verde en HMI |
| **Advertencia** | 50 ms – 1 s | 100 ms – 500 ms | Badge amarillo + evento |
| **Alarma** | > 1 s | > 500 ms | BOOL `ALM.NTP.OutOfSync` + log ERROR |
| **Crítico (opcional fail-closed)** | > 5 s o salto > 2 s en 1 min | > 2 s | Pausar adquisición (`acquisition_ready=False`, razón `clock_unsync`) |

Ajustar con ingeniería de planta. iDetectFugas con ventanas de segundos tolera ~100 ms; correlación de alarmas entre líneas exige **< 1 s** entre edges.

---

## 4. Estrategia recomendada — arquitectura en capas

```
┌─────────────────────────────────────────────────────────────────┐
│  Capa 0 — Infraestructura OT                                     │
│  2× NTP Stratum 1–2 (GPS/PTP grandmaster) en VLAN OT             │
│  Mismo dominio para TODOS los edges + servidor PG + HMI central  │
└───────────────────────────────▲─────────────────────────────────┘
                                │ UDP 123 (y 319/320 si PTP)
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 1 — Host / bare-metal / VM del edge                        │
│  chrony (preferido) o systemd-timesyncd                          │
│  makestep 1.0 3  (solo al arranque; luego slew)                   │
│  Config: server ntp.planta.local iburst + backup                 │
└───────────────────────────────▲─────────────────────────────────┘
                                │ reloj del kernel
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 2 — Contenedor Docker PyAutomation                         │
│  Hereda CLOCK_REALTIME del host — NO correr ntpd dentro         │
│  Compose: documentar requisito «host sincronizado»               │
└───────────────────────────────▲─────────────────────────────────┘
                                │ lectura
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 3 — PyAutomation **monitor** (NUEVO — propuesto)           │
│  NtpMonitorWorker: SNTP query async, offset, stratum, jitter     │
│  Persist config: servers[], check_interval_s, thresholds           │
│  Health: CLOCK_OFFSET_MS, NTP_SYNCED, NTP_LAST_CHECK             │
│  Alarma: {area}.ALM.NTP.OutOfSync (patrón connection_alarms)     │
└───────────────────────────────▲─────────────────────────────────┘
                                │ API + Socket.IO badge (opcional)
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 4 — HMI Configuración + consola multi-edge (futuro)        │
│  Sección «Sincronización de reloj» + estado en header del edge   │
│  GET /api/system/nodes enriquecido con salud NTP por nodo        │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Qué NO hacer (anti-patrones)

| Anti-patrón | Por qué |
|---|---|
| Cliente NTP completo en Python disciplinando el SO con `settimeofday` | Requiere privilegios; compite con chrony; drift bajo gevent; no auditable por OT |
| Cada contenedor con `ntpd` propio | Relojes divergentes entre contenedores del mismo host |
| Usar solo `pool.ntp.org` en producción | Dependencia WAN; latencia/jitter impredecible; ciberseguridad |
| Confiar en reloj del navegador para validar el edge | El HMI puede estar en laptop del ingeniero |
| «Arreglar» multi-edge solo con `AUTOMATION_TIMEZONE` | Corrige **huso**, no **epoch** |
| Probe NTP en hot path OPC | Bloquearía adquisición; viola [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) |

### 4.2 Qué SÍ hacer en PyAutomation

| Pieza | Rol |
|---|---|
| **`automation/time/ntp_monitor.py`** | SNTP client (socket UDP, timeout 2 s); calcula offset, delay, stratum |
| **`NtpMonitorWorker`** | Hilo daemon; `call_later(check_interval)`; probe en threadpool |
| **Config** | Env `AUTOMATION_NTP_SERVERS` (csv); DB/settings `ntp_servers`, `ntp_check_interval_s`, umbrales |
| **Health** | Extender `/api/health/system` con bloque `clock` |
| **Alarma** | `ensure_ntp_sync_alarm()` análogo a `connection_alarms.py` |
| **HMI Settings** | Capítulo `#settings-clock` entre Estación e Historiador |
| **Events** | Transiciones synced→unsynced en `persist_system_event` |
| **Tests** | Mock UDP; CA-NTP-01..05 |

---

## 5. Diseño de producto propuesto

### 5.1 Configuración (env + API + HMI)

| Parámetro | Default | Descripción |
|---|---|---|
| `AUTOMATION_NTP_SERVERS` | *(vacío)* | Lista CSV: `ntp1.planta.local,ntp2.planta.local` |
| `AUTOMATION_NTP_CHECK_INTERVAL_S` | `3600` | Periodo de verificación (60 … 86400) |
| `AUTOMATION_NTP_WARN_OFFSET_MS` | `50` | Umbral advertencia |
| `AUTOMATION_NTP_ALARM_OFFSET_MS` | `1000` | Umbral alarma BOOL |
| `AUTOMATION_NTP_FAIL_CLOSED` | `false` | Si true: bloquear adquisición si crítico |
| `AUTOMATION_NTP_ENABLED` | `true` cuando hay servers | Permite desactivar monitor en dev |

**HMI — sección «Sincronización de reloj»** (`Settings.tsx`, nuevo `ClockSyncPanel.tsx`):

- Servidor(es) NTP (solo lectura si vienen de env en producción; editable si admin y política lo permite)
- Intervalo de verificación (slider o select: 1 h / 6 h / 24 h / personalizado)
- **Estado actual:** Sincronizado / Desincronizado / No configurado
- **Última comprobación** (UTC + planta)
- **Offset** vs servidor (ms), stratum, RTT
- Badge en header junto al reloj de estación (icono reloj + verde/amarillo/rojo)
- Texto de ayuda: «La disciplina del reloj la realiza el sistema operativo (chrony). PyAutomation verifica el cumplimiento.»

### 5.2 API propuesta

```
GET  /api/system/clock              → snapshot completo (público o auth ligero)
GET  /api/health/system             → añadir CLOCK_OFFSET_MS, NTP_SYNCED, …
PUT  /api/settings/clock            → intervalo + servers (admin; validar FQDN/IP)
POST /api/system/clock/check        → probe inmediato (on-demand, rate-limited)
```

Payload ejemplo:

```json
{
  "enabled": true,
  "synced": true,
  "servers": ["ntp.planta.local"],
  "server_used": "ntp.planta.local",
  "offset_ms": 12.4,
  "delay_ms": 0.8,
  "stratum": 2,
  "last_check_utc": "2026-08-19T14:32:01.123Z",
  "next_check_utc": "2026-08-19T15:32:01.123Z",
  "check_interval_s": 3600,
  "thresholds": { "warn_ms": 50, "alarm_ms": 1000 },
  "host_time_utc": "2026-08-19T14:32:01.135Z",
  "node_id": "edge-linea1"
}
```

### 5.3 Scheduler no bloqueante

Patrón alineado con workers existentes ([AUDIT_DB.md](./AUDIT_DB.md) probes, `LoggerWorker`):

```
NtpMonitorWorker (Thread daemon)
  loop:
    if due(check_interval) and servers configured:
      future = threadpool.submit(sntp_query, server, timeout=2.0)
      result = future.result(timeout=3.0)   # fuera del hub gevent
      update metrics + alarm + last_check
    sleep(min(60, time_until_next))         # wake barato, no busy-wait
```

| Requisito | Cómo |
|---|---|
| No bloquear hub gevent | Threadpool OS, igual que DB throwaway |
| No bloquear OPC | Worker separado del DAS |
| Intervalo configurable | Persistido en settings; recarga en caliente |
| Arranque | Probe inmediato al boot si `servers` definidos |
| Detección de salto | Comparar `\|offset_now - offset_prev\|` > 2000 ms → evento `clock_step_detected` |
| Coste | 1 datagrama UDP / intervalo / edge ≈ despreciable |

**No reutilizar `logger_period`** para NTP: mezclaría responsabilidades ([AUDIT_LOGGING.md](./AUDIT_LOGGING.md) §0).

### 5.4 Alarma de planta

Siguiendo [connection_alarms.py](../automation/utils/connection_alarms.py):

| Artefacto | Nombre |
|---|---|
| Tag BOOL | `{area}.SYS.NTP.OutOfSync` |
| Alarma | `{area}.ALM.NTP.OutOfSync` |
| Verdadero cuando | `\|offset_ms\| > alarm_threshold` **o** probe falló N veces seguidas |
| Mensaje | «Reloj del edge desincronizado respecto a NTP planta (Δ = X ms)» |

Integrar en banner HMI y `GET /api/alarms` scoped al edge.

### 5.5 Multi-edge: consola central (Fase 2)

Extender `GET /api/system/nodes` o nuevo `GET /api/system/clock/plant`:

| Campo por nodo | Uso |
|---|---|
| `last_seen` (ya existe) | Heartbeat |
| `clock_offset_ms` | Salud temporal |
| `ntp_synced` | Semáforo |
| `max_inter_edge_skew_ms` | *(futuro)* PG calcula max Δ entre edges activos |

Permite al operador ver **todos los edges** sin SSH a cada caja.

---

## 6. Hallazgos (IDs) y estado

| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| **NTP-C1** | Crítica | Sin monitor NTP; multi-edge asume relojes correctos | **Abierto** |
| **NTP-C2** | Crítica | Fallback OPC `datetime.now()` si falta SourceTimestamp — reloj SO erróneo contamina CVT | **Abierto** (mitigación parcial: OPC con timestamp bueno) |
| **NTP-C3** | Alta | Docker/host sin documentar requisito chrony en despliegue edge | **Abierto** |
| **NTP-H1** | Alta | `/api/health/system` sin métricas de reloj | **Abierto** |
| **NTP-H2** | Alta | Sin alarma ISA de desincronización | **Abierto** |
| **NTP-H3** | Media | Settings HMI sin sección reloj/NTP | **Abierto** |
| **NTP-H4** | Media | Reloj header HMI = navegador, puede ocultar deriva del edge | **Abierto** — mostrar **dos** relojes: «Edge (servidor)» vs «Estación (display)» o badge offset |
| **NTP-M1** | Media | Sin evento de auditoría en transición sync/unsync | **Abierto** |
| **NTP-M2** | Baja | `core.py` usa `datetime.now()` naive en mensajes de log (no crítico para historian) | **Abierto** — higiene |
| **NTP-B1** | Baja | No hay tests de contrato temporal multi-edge (2 edges, mismo evento, Δ offset) | **Abierto** |

---

## 7. Roadmap de implementación

### Fase A — Monitor mínimo viable (P0)

| Entrega | Archivos / superficie |
|---|---|
| Módulo SNTP + worker | `automation/time/ntp_monitor.py`, `automation/workers/ntp_monitor.py` |
| Env + boot | `automation/__init__.py`, `core.py` start worker |
| Health | `modules/health/resources/health.py` |
| Alarma | `automation/utils/clock_alarms.py` |
| Tests | `automation/tests/test_ntp_monitor.py` |

**CA-NTP-01:** Con mock NTP, offset 500 ms → `NTP_SYNCED=false`, alarma TRUE.  
**CA-NTP-02:** Probe no bloquea request HTTP (p99 `/api/health/ping` estable).  
**CA-NTP-03:** Sin servers configurados → `enabled=false`, sin alarma.

### Fase B — HMI y settings (P1)

| Entrega | Superficie |
|---|---|
| API settings clock | `modules/settings/resources/settings.py` |
| Panel HMI | `ClockSyncPanel.tsx`, `#settings-clock`, i18n `es`/`en` |
| Badge header | Componente junto a `header-clock` |

**CA-NTP-04:** Operador ve estado «Sincronizado» y offset < 50 ms en verde.  
**CA-NTP-05:** Cambiar intervalo a 86400 s persiste y respeta en worker.

### Fase C — Planta multi-edge (P2)

| Entrega | Superficie |
|---|---|
| Tabla `Nodes` o columnas: `clock_offset_ms`, `ntp_synced_at` | `dbmodels/nodes.py` |
| UPSERT en cada check | `core._register_node` |
| Consola planta | HMI o `/api/system/clock/plant` |
| Soak 2-edge | Lab: desplazar chrony en A +500 ms → alarma A, B OK |
| Docs deploy | `docs/multi-edge.md`, README, compose ejemplo chrony en host |

**CA-NTP-06:** Dos edges, mismo NTP; `\|offset_A - offset_B\| < 100 ms` tras 24 h soak.  
**CA-NTP-07:** Edge A con chrony detenido 10 min → alarma + evento; B sin afectación.

### Fase D — Opcional grado nuclear (P3)

| Entrega | Notas |
|---|---|
| PTP grandmaster en OT | Fuera del repo PyAutomation; integración vía chrony `refclock PHC` |
| Fail-closed adquisición | `AUTOMATION_NTP_FAIL_CLOSED=true` |
| Comparación OPC SourceTimestamp vs recepción | Detección de reloj de campo malo (independiente de NTP edge) |

---

## 8. Despliegue recomendado (documentación operativa)

### 8.1 Host Linux (edge bare-metal o VM)

```ini
# /etc/chrony/chrony.conf (ejemplo planta)
pool ntp1.planta.local iburst
pool ntp2.planta.local iburst
makestep 1.0 3
rtcsync
```

```bash
timedatectl set-ntp true
chronyc tracking
chronyc sources -v
```

### 8.2 Docker Compose

```yaml
# El contenedor NO lleva chrony. El HOST debe estar sincronizado.
services:
  automation:
    # NO usar cap_add: SYS_TIME salvo política explícita de OT
    environment:
      AUTOMATION_NTP_SERVERS: "ntp1.planta.local,ntp2.planta.local"
      AUTOMATION_NTP_CHECK_INTERVAL_S: "3600"
```

### 8.3 Checklist de aceptación en planta

```text
[ ] Host edge: chrony active + sources reach*
[ ] Mismo par NTP en todos los edges de la planta
[ ] PyAutomation: GET /api/system/clock → synced=true, |offset| < 50 ms
[ ] HMI Settings: sección reloj en verde
[ ] Simular stop chrony 5 min → alarma ALM.NTP.OutOfSync en < 2× intervalo
[ ] Historiador: tendencia multi-tag cross-line alineada (evento de prueba)
[ ] Documentar en runbook junto a AUDIT_PERFORMANCE § Runbook
```

---

## 9. Relación con auditorías existentes

| Auditoría | Interacción |
|---|---|
| [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) | Complementaria. TZ = presentación; NTP = epoch. Implementar badge reloj **sin** romper selector planta/local |
| [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) | Cierra hueco «tiempo» de §3. `NODE_ID` en payload clock. Opcional fail-closed suma a `ACQUISITION_BLOCKED_REASON` |
| [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) | Timestamps journal siguen siendo UTC del SO; NTP reduce riesgo de colisiones `(tag_id, timestamp)` por salto |
| [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) | Eventos sync/unsync van a L3 Events + L1 log INFO/ERROR |
| [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) | `cycle_timestamp` y buffers dependen del reloj; monitor NTP no cambia tres relojes SM |

---

## 10. Archivos clave

| Área | Hoy | Propuesto |
|---|---|---|
| Timebase UTC | `automation/timebase.py` | Sin cambio |
| OPC timestamps | `automation/opcua/subscription.py` L113–118 | Opcional: métrica `OPC_TS_FALLBACK_COUNT` |
| Health | `automation/modules/health/resources/health.py` | Bloque `clock` |
| Settings HMI | `hmi/src/pages/Settings.tsx` | `#settings-clock` |
| Alarmas sistema | `automation/utils/connection_alarms.py` | `clock_alarms.py` paralelo |
| Multi-edge nodos | `automation/dbmodels/nodes.py` | Columnas salud temporal |
| Docker | `Dockerfile` | Comentario + doc; **no** instalar ntpd |
| Tests TZ | `automation/tests/test_timezone_hora_unica.py` | Complementar con `test_ntp_monitor.py` |

---

## 11. Veredicto y scorecard

| ID | Capacidad | Hoy | Objetivo clase mundial |
|---|---|---|---|
| NTP-01 | Disciplina de reloj en SO (chrony) | Responsabilidad deploy, **no documentada** | Documentada + verificada |
| NTP-02 | Misma fuente NTP en todos los edges | **No enforced** | Config + consola |
| NTP-03 | Monitor offset en PyAutomation | ❌ | SNTP worker |
| NTP-04 | Visibilidad HMI | ❌ | Settings + badge |
| NTP-05 | Alarma operador | ❌ | BOOL ISA |
| NTP-06 | Health / observabilidad | ❌ | `/api/health/system` |
| NTP-07 | Evidencia multi-edge 24 h | ❌ | CA-NTP-06 soak |
| NTP-08 | Fail-closed opcional | ❌ | Política planta |

**Scorecard actual: 0/8 — grado F.**  
**Tras Fase A+B: 5/8 — grado B− (monitor + HMI).**  
**Tras Fase C + soak: 8/8 — grado A (paridad SCADA industrial).**

---

## 12. Respuesta ejecutiva para el equipo

1. **Sí**, todos los edges deben apuntar al **mismo par de servidores NTP de planta**, configurados en el **SO vía chrony**, no dentro del proceso Python.
2. **Sí**, PyAutomation debe incorporar un **monitor NTP ligero** (SNTP), un **scheduler no bloqueante** con intervalo configurable, una **sección en Configuración** y una **alarma** cuando el edge esté fuera de sync.
3. **No**, no implementar un cliente NTP «completo» que mueva el reloj del sistema desde la app — eso es anti-patrón industrial y un riesgo de seguridad.
4. La operación «Hora Única» ([AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md)) **no sustituye** esta capacidad; ambas son necesarias para multi-edge de clase mundial.

Próximo paso sugerido: abrir spec `03-NTP-EDGE-CLOCK-MONITOR.md` y ejecutar **Fase A** (worker + health + alarma + tests) antes del soak 2-edge de [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md).
