# Auditoría compacta: sincronización NTP y reloj de sistema en despliegues multi-edge

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) + imagen Docker |
| **Alcance** | Disciplina del reloj del SO/host; verificación periódica; visibilidad operativa; correlación temporal entre N edges contra un historiador compartido |
| **Fecha** | 2026-08-19 (Fase A+B+v2.0 monitor universal) |
| **Spec** | [specs/03-NTP-EDGE-CLOCK-MONITOR.md](../specs/03-NTP-EDGE-CLOCK-MONITOR.md) v2.0 |
| **Complementa** | [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) (presentación IANA), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) §3 («tiempo» en backlog de planta), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) (timestamps UTC en journal), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) (alarma de sistema) |
| **Veredicto vigente** | **A** — Monitor universal v2.0: IPv4/IPv6 (`getaddrinfo`), reintentos backoff, detección salto brusco, diagnóstico HMI/API, runbook `docs/ntp-deployment.md`. **A+** tras soak 2-edge (CA-NTP-20). Auth simétrica/NTS = P3 |
| **Clasificación** | Auditoría de arquitectura temporal · multi-edge · operación 24/7 |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-19) |
|---|---|
| ¿En qué nivel estamos con NTP / sync multi-edge? | **Nivel 2 — monitor en producto.** Multi-edge Fase 1 + verificación SNTP periódica, alarma BOOL, HMI y health. **No** garantiza por sí solo disciplina del reloj; eso es Capa 1 (SO) |
| ¿Cada PyAutomation debe tener un **cliente NTP** apuntando al mismo servidor? | **No como disciplinador dentro del proceso Python.** La disciplina del reloj es responsabilidad del **SO/host** (chrony, w32time, systemd-timesyncd). **Sí:** todos los edges deben usar **las mismas fuentes NTP** de planta (2–3 servidores Stratum 1–2 OT; no `pool.ntp.org` en producción). El monitor PyAutomation debe apuntar a **los mismos servidores** para verificar |
| ¿PyAutomation debe implementar algo? | **Implementado v2.0:** `query_ntp_server` dual-stack, backoff 1s/2s (×2 reintentos), salto brusco (`ntp_step_threshold_ms`), `last_error`/`last_address_used`/`auth_required_detected`/`jump_detected` en API y HMI |
| ¿Se necesitan **credenciales** para conectar a un servidor NTP? | **No** para NTP/SNTP estándar (UDP 123). Sin usuario/contraseña ni certificados. **Excepciones no soportadas hoy:** NTP con clave simétrica (`ntp.conf restrict … key`) y **NTS** (Network Time Security, TLS) |
| ¿Funciona con servidores **Linux** y **Windows Server**? | **Sí**, si el servidor responde NTP/SNTP en **UDP/123** sin autenticación obligatoria. Linux (`chrony`, `ntpd`) suele venir listo; Windows (`w32time`) requiere configuración explícita de servidor NTP + firewall |
| ¿La estrategia es «infalible»? | **No.** «Infalible» en OT = **NTP redundante en VLAN OT + disciplina en el host + monitor con alarmas**. El cliente Python **verifica**; no mueve el reloj del SO. Ver §3.2 limitaciones del monitor |
| ¿Scheduler no bloqueante configurable? | **Implementado.** `NtpMonitorWorker` (hilo daemon); probe UDP en threadpool (`run_uncooperative_db_call`); intervalo 60–86400 s (default 3600). **No** en hot path OPC/CVT |
| ¿Estrategia clase mundial / grado nuclear? | **Capas:** (1) PTP/IEEE 1588 o NTP Stratum bajo en red OT; (2) chrony/w32time en host con `makestep` acotado; (3) contenedor hereda reloj del host; (4) PyAutomation **verifica** offset y eleva alarma; (5) historiador correlaciona por `node_id` + timestamp; (6) consola central agrega salud temporal de todos los edges |

### 0.1 Distinción crítica: «Hora Única» ≠ «Reloj sincronizado»

| Capacidad | [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) | Esta auditoría |
|---|---|---|
| Almacenar en UTC | ✅ | Prerrequisito |
| Mostrar planta vs local en HMI | ✅ | Independiente |
| Disciplinar el reloj del edge | ❌ (SO) | **Objetivo Capa 1 — fuera del proceso Python** |
| Detectar deriva / salto de reloj | ✅ monitor | **Implementado** (`offset_ms`, `jump_detected`, evento `NTP clock step detected`) |
| Alarmar operador si Δ > umbral | ✅ | **Implementado** (`ALM.NTP.OutOfSync`) |
| Evidencia en despliegue multi-edge | Parcial (`Nodes.ntp_*`) | **Fase C soak pendiente** |

Un edge con reloj adelantado 45 s **sigue guardando «UTC»** en TagValue, pero es **UTC incorrecto**. Dos edges desincronizados producen historiales **no correlacionables** en el mismo PostgreSQL aunque la partición multi-edge sea correcta.

### 0.2 Integración con cualquier servidor NTP (guía operativa)

| Tema | Detalle |
|---|---|
| **Protocolo** | SNTP cliente (RFC 4330), compatible con servidores NTPv3/v4 que respondan en UDP 123 |
| **Credenciales** | **Ninguna** en modo estándar. Active Directory afecta al *cliente Windows del SO*, no al monitor Python |
| **Formato de servidor en HMI** | IP (`192.168.10.5`) o hostname (`ntp.planta.local`), lista CSV con failover automático |
| **Prioridad de configuración** | **`app_config.json` (HMI Settings → NTP Sync) > env bootstrap (`AUTOMATION_NTP_*`) > defaults**. Las variables de entorno son **opcionales** en primer arranque |
| **Linux como servidor** | `chrony`/`ntpd`: permitir subred OT (`allow 192.168.x.0/24`). Responde sin login |
| **Windows Server como servidor** | Servicio **Windows Time** activo; registro `NtpServer` / `AnnounceFlags`; **UDP 123 entrante** en firewall. En dominio, validar que responda a edges Linux fuera del dominio |
| **Red** | Salida **UDP 123** desde cada edge hacia servidores NTP; DNS si se usan nombres |
| **Anti-patrón producción** | `pool.ntp.org`, un solo servidor sin respaldo, NTP solo dentro del contenedor |

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

| Riesgo | Sin NTP verificado | Con estrategia implementada + SO disciplinado |
|---|---|---|
| Correlación cross-line en trends/alarms | ❌ Sesgo invisible | ✅ Δ offset expuesto por nodo (`GET /api/system/clock`, `Nodes.ntp_offset_ms`) |
| SAF / exact-once `(tag_id, timestamp)` | Colisiones o orden invertido si salto grande | ✅ Detección de offset → alarma + evento |
| `machine.cycle_timestamp` / LDS | Ventanas desalineadas entre líneas | ✅ Misma epoch si chrony/w32time OK en todos los hosts |
| Cumplimiento / auditoría | Sin evidencia de sync | ✅ Log + Events + health exportable |
| Fail-closed multi-edge | Solo identidad de nodo | ✅ Opcional `ntp_fail_closed` → `acquisition_ready=False`, razón `clock_unsync` |

[AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) ya señala: *«El aislamiento de planta (red, BD, **tiempo**, operación 24/7) no.»* Esta auditoría cierra el gap **tiempo** a nivel monitor; la disciplina del SO sigue siendo responsabilidad de despliegue.

---

## 2. Inventario de código (evidencia 2026-08-19)

### 2.1 Componentes NTP en producto (vigente)

| Artefacto | Estado |
|---|---|
| `automation/time/ntp_monitor.py` | ✅ SNTP dual-stack (`getaddrinfo`), `used_family`/`used_address`, kiss-o-death AUTH |
| `automation/time/ntp_config.py` | ✅ HMI > env > defaults; `ntp_step_threshold_ms`; `ntp_auth_type` reservado P3 |
| `automation/workers/ntp_monitor.py` | ✅ Backoff 1s/2s, failover, salto brusco, auth sin alarma sync |
| `automation/utils/clock_alarms.py` | ✅ `{area}.ALM.NTP.OutOfSync` |
| `automation/core.py` | ✅ Arranque/parada worker NTP |
| `automation/dbmodels/nodes.py` + `managers/db.py` | ✅ `ntp_offset_ms`, `ntp_synced`, `ntp_updated_at` |
| API | ✅ `GET/PUT /api/settings/clock`, `GET/POST /api/system/clock(/check)` + campos diagnóstico |
| `/api/health/system` | ✅ Bloque `clock` (+ `last_error`, `jump_detected`, …) |
| HMI | ✅ `ClockSyncPanel`, `ClockBadge`, errores/auth tooltip Windows/Linux |
| Tests | ✅ `test_ntp_monitor.py` — **18 tests** CA-NTP-01…06, 14…18 |
| Docs | ✅ `docs/ntp-deployment.md`, § NTP en `docs/multi-edge.md` |

### 2.2 De dónde sale el tiempo hoy

| Origen | Mecanismo | Dependencia del reloj SO |
|---|---|---|
| OPC UA DAS | `SourceTimestamp` → `ensure_utc`; fallback `datetime.now(pytz.utc)` | Fallback **sí**; fuente de campo puede traer su propio reloj |
| DAQ / tags internos | `datetime.now(timezone.utc)` en varios caminos | **Sí** |
| State machines | `quantize_datetime_ms(datetime.now(timezone.utc))` | **Sí** |
| SAF / TagValue | epoch ms UTC en journal | **Sí** |
| Monitor NTP | Compara reloj host vs servidor SNTP | **Lee** reloj SO; **no** lo corrige |
| HMI header clock | Hora del **navegador** (cliente) | **No** es reloj del edge — `ClockBadge` muestra estado NTP del **servidor** |

**Conclusión:** PyAutomation **verifica** el reloj del sistema; **no** lo disciplina. Sin chrony/w32time correcto en el host, el monitor detectará desfase pero no lo corregirá.

### 2.3 Imagen Docker

| Aspecto | Estado | Riesgo |
|---|---|---|
| Reloj del contenedor | Hereda del host Linux (namespace `TIME` compartido por defecto) | Si el **host** está mal, el contenedor también |
| `--privileged` / `SYS_TIME` | No requerido ni documentado | Correcto: la app **no** debe llamar `settimeofday` |
| Red del contenedor | Debe permitir **UDP 123 saliente** hacia servidores NTP | Firewall bloqueado → probe falla → alarma tras 3 ciclos |
| TZ del contenedor | No fijado en Dockerfile | OK para UTC lógico; no sustituye NTP |

---

## 3. Estándares de referencia (grado industrial / nuclear)

| Estándar / práctica | Relevancia |
|---|---|
| **IEC 62439-3 / IEEE 1588 PTP** | Sub-ms en buses de proceso; overkill para muchos SCADA, obligatorio en algunas nucleares |
| **RFC 5905 NTPv4** | Sync ms–sub-ms con Stratum 1–2 en LAN OT |
| **SNTP (RFC 4330)** | Sonda ligera **solo lectura** — **implementada** en `ntp_monitor.py` |
| **RFC 8915 NTS** | Autenticación TLS para NTP público; **no implementada** en PyAutomation |
| **ISA-95 / IEC 62264** | Eventos L2/L3 deben ser ordenables en línea de tiempo de planta |
| **ISA-18.2** | Marca temporal inequívoca en alarmas |
| **NERC CIP / IEC 62443** | Servidores NTP en zona OT; no depender de Internet en producción |
| **Vendor SCADA (PI, Ignition, WinCC)** | NTP en SO + indicador de sync en consola; la app **no** reemplaza chrony |

### 3.1 Objetivos numéricos recomendados (planta típica multi-edge)

| Clase | \|offset\| vs NTP planta | \|offset\| entre edges | Acción |
|---|---|---|---|
| **Normal** | ≤ 50 ms | ≤ 100 ms | Verde en HMI (`ntp_warn_offset_ms` default 50) |
| **Advertencia** | 50 ms – 1 s | 100 ms – 500 ms | Badge amarillo + `warn=true` |
| **Alarma** | > 1 s | > 500 ms | BOOL `ALM.NTP.OutOfSync` (`ntp_alarm_offset_ms` default 1000) |
| **Crítico (opcional fail-closed)** | > umbral alarma sostenido | > 2 s | `ntp_fail_closed=true` → pausar adquisición |

Ajustar con ingeniería de planta. iDetectFugas con ventanas de segundos tolera ~100 ms; correlación de alarmas entre líneas exige **< 1 s** entre edges.

### 3.2 Limitaciones del monitor SNTP v2.0 (no «infalible»)

| Limitación | Impacto | Mitigación / estado v2.0 |
|---|---|---|
| **IPv4 + IPv6** dual-stack | — | ✅ `getaddrinfo` + failover por dirección (CA-NTP-14/15) |
| Solo **UDP 123** | No NTP-over-TCP ni NTS | Servidor NTP clásico en VLAN OT |
| **Sin autenticación** NTP (claves simétricas / NTS) | Fallo si el servidor exige auth | ✅ `auth_required_detected` + evento; usar servidor sin auth o P3 |
| **SNTP simple** (1 request/response) | Menos filtrado que cliente NTP completo | Suficiente para **monitor**; disciplina la hace chrony |
| **Timeout 2 s** + 2 reintentos backoff | Red lenta → más tolerante | ✅ Backoff 1s/2s por servidor (CA-NTP-17) |
| **3 fallos consecutivos** → alarma | Evita falsos positivos | Documentar en runbook |
| **No disciplina reloj** | chrony caído → deriva hasta alarma | Monitorizar servicio chrony/w32time en host |
| **Contenedor** | Hereda reloj del host | chrony en **host**, no dentro del contenedor |

**P3 pendiente:** implementación real de `ntp_auth_type` symmetric/NTS.

---

## 4. Estrategia recomendada — arquitectura en capas

```
┌─────────────────────────────────────────────────────────────────┐
│  Capa 0 — Infraestructura OT                                     │
│  2× NTP Stratum 1–2 (GPS/PTP grandmaster) en VLAN OT             │
│  Linux (chrony) o Windows Server (w32time) — sin credenciales    │
│  Mismo dominio para TODOS los edges + servidor PG + HMI central  │
└───────────────────────────────▲─────────────────────────────────┘
                                │ UDP 123 (sin login)
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 1 — Host / bare-metal / VM del edge                        │
│  Linux: chrony (preferido) o systemd-timesyncd                   │
│  Windows: w32time → mismos servidores que el panel HMI           │
│  makestep 1.0 3  (solo al arranque; luego slew)                   │
└───────────────────────────────▲─────────────────────────────────┘
                                │ reloj del kernel
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 2 — Contenedor Docker PyAutomation                         │
│  Hereda CLOCK_REALTIME del host — NO correr ntpd dentro         │
│  Red: UDP 123 saliente hacia servidores NTP                      │
└───────────────────────────────▲─────────────────────────────────┘
                                │ lectura + probe UDP
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 3 — PyAutomation monitor ✅ IMPLEMENTADO                   │
│  NtpMonitorWorker + query_ntp_server (SNTP)                      │
│  Config: HMI app_config.json → servers[], interval, thresholds   │
│  Health: bloque clock; alarma ALM.NTP.OutOfSync                  │
│  Failover: prueba servidores en orden; 3 fallos → alarma         │
└───────────────────────────────▲─────────────────────────────────┘
                                │ API + HMI
┌───────────────────────────────┴─────────────────────────────────┐
│  Capa 4 — HMI + consola multi-edge (parcial)                     │
│  Settings «Sincronización NTP» + ClockBadge en header ✅          │
│  Consola planta agregada — Fase C pendiente                      │
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
| Asumir que PyAutomation «se conecta a cualquier NTP» sin red/firewall | UDP 123 debe estar permitido; Windows Server debe estar **configurado** como servidor |

### 4.2 Piezas implementadas en PyAutomation

| Pieza | Ruta | Rol |
|---|---|---|
| Cliente SNTP | `automation/time/ntp_monitor.py` | UDP :123, timeout 2 s; offset, delay, stratum |
| Config | `automation/time/ntp_config.py` | HMI > env > defaults |
| Worker | `automation/workers/ntp_monitor.py` | Daemon; threadpool; failover; fail-closed |
| Alarmas | `automation/utils/clock_alarms.py` | `{area}.ALM.NTP.OutOfSync` |
| API / Health | `modules/settings`, `modules/system`, `modules/health` | Clock settings + snapshot + check on-demand |
| HMI | `ClockSyncPanel.tsx`, `ClockBadge.tsx` | Config + estado; texto: disciplina = SO |
| Tests | `automation/tests/test_ntp_monitor.py` | CA-NTP-01 … CA-NTP-06 |

### 4.3 Compatibilidad Linux / Windows Server (servidor NTP)

| Plataforma | Rol típico | Requisitos para que el monitor PyAutomation funcione |
|---|---|---|
| **Linux** (`chrony`, `ntpd`) | Servidor NTP OT | `allow` subred edges; UDP 123 abierto; responde SNTP sin auth |
| **Windows Server** (`w32time`) | Servidor NTP OT / DC | Servicio Windows Time activo; `NtpServer` habilitado; firewall UDP 123 **entrante**; validar respuesta desde edge Linux |
| **Edge Linux** | Cliente disciplina + monitor | `chrony` → mismos servidores que HMI; PyAutomation solo verifica |
| **Edge Windows** | Cliente disciplina + monitor | `w32time` → mismos servidores; PyAutomation en proceso Python igual (UDP 123) |
| **Hipervisor / VM** | Fuente indirecta | Desactivar sync de reloj del hypervisor que compita con chrony (`vmware.tools.timesync`, etc.) |

PyAutomation **no distingue** SO del servidor: envía paquete SNTP estándar y parsea respuesta.

---

## 5. Diseño de producto (implementado)

### 5.1 Configuración (HMI + env bootstrap)

| Parámetro | Default | Descripción |
|---|---|---|
| `ntp_servers` (HMI / JSON) | *(vacío)* | Lista CSV: `192.168.10.5,192.168.10.6` o hostnames |
| `ntp_check_interval_s` | `3600` | Periodo de verificación (60 … 86400) |
| `ntp_warn_offset_ms` | `50` | Umbral advertencia |
| `ntp_alarm_offset_ms` | `1000` | Umbral alarma BOOL |
| `ntp_fail_closed` | `false` | Si true: bloquear adquisición si crítico |
| `ntp_enabled` | `true` | Monitor activo cuando hay servidores |
| `AUTOMATION_NTP_*` | — | **Opcional:** bootstrap si clave no persistida en HMI |

**HMI — sección «Sincronización NTP»** (`Settings.tsx` → `ClockSyncPanel.tsx`):

- Servidores NTP (**IP o nombre**; placeholder `192.168.10.5, 192.168.10.6`)
- Intervalo, umbrales warn/alarm, fail-closed
- Estado: Sincronizado / Desincronizado / No configurado
- Offset (ms), stratum, RTT, última/próxima comprobación (UTC)
- Badge en header (`ClockBadge`)
- Texto: «La disciplina del reloj la realiza el sistema operativo (chrony). PyAutomation verifica el cumplimiento. No hace falta definir variables de entorno.»

### 5.2 API (implementada)

```
GET  /api/system/clock              → snapshot completo
GET  /api/health/system             → bloque clock
PUT  /api/settings/clock            → intervalo + servers (admin)
POST /api/system/clock/check        → probe inmediato (rate-limited 60 s)
```

Payload ejemplo:

```json
{
  "enabled": true,
  "synced": true,
  "server_used": "192.168.10.5",
  "offset_ms": 12.4,
  "delay_ms": 0.8,
  "stratum": 2,
  "last_check_utc": "2026-08-19T14:32:01.123Z",
  "next_check_utc": "2026-08-19T15:32:01.123Z",
  "check_interval_s": 3600,
  "warn_offset_ms": 50,
  "alarm_offset_ms": 1000,
  "fail_closed": false,
  "host_time_utc": "2026-08-19T14:32:01.135Z",
  "node_id": "edge-linea1"
}
```

### 5.3 Scheduler no bloqueante (implementado)

```
NtpMonitorWorker (Thread daemon)
  loop:
    config = load_ntp_config(app_config)   # HMI > env > defaults
    for server in ntp_servers_list:        # failover
      result = threadpool.submit(query_ntp_server, server, timeout=2.0)
    evaluate offset vs thresholds; 3 failures → alarm
    persist Nodes.ntp_* ; set ALM.NTP.OutOfSync
    sleep(ntp_check_interval_s)
```

| Requisito | Estado |
|---|---|
| No bloquear hub gevent | ✅ `run_uncooperative_db_call` |
| No bloquear OPC | ✅ Worker separado |
| Intervalo configurable | ✅ Persistido HMI; `reconfigure()` |
| Failover multi-servidor | ✅ Primer servidor que responde |
| Probe manual | ✅ `POST /api/system/clock/check` (60 s rate limit) |

### 5.4 Alarma de planta (implementada)

| Artefacto | Nombre |
|---|---|
| Tag BOOL | `{area}.SYS.NTP.OutOfSync` |
| Alarma | `{area}.ALM.NTP.OutOfSync` |
| Verdadero cuando | `\|offset_ms\| > alarm_threshold` **o** 3 probes fallidos consecutivos |
| HMI | `ClockBadge` + banner alarmas scoped al edge |

### 5.5 Multi-edge: consola central (Fase C — pendiente)

Extender agregación planta con `max_inter_edge_skew_ms` y vista HMI multi-nodo. Columnas `Nodes.ntp_*` ya persisten por edge.

---

## 6. Hallazgos (IDs) y estado

| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| **NTP-C1** | Crítica | Sin monitor NTP; multi-edge asume relojes correctos | **Cerrado** (Fase A) |
| **NTP-C2** | Crítica | Fallback OPC `datetime.now()` si falta SourceTimestamp | **Abierto** (mitigación parcial: OPC con timestamp bueno) |
| **NTP-C3** | Alta | Docker/host sin documentar requisito chrony en despliegue edge | **Cerrado** — `docs/ntp-deployment.md`, § NTP en `docs/multi-edge.md` |
| **NTP-H1** | Alta | `/api/health/system` sin métricas de reloj | **Cerrado** |
| **NTP-H2** | Alta | Sin alarma ISA de desincronización | **Cerrado** |
| **NTP-H3** | Media | Settings HMI sin sección reloj/NTP | **Cerrado** |
| **NTP-H4** | Media | Reloj header HMI = navegador, puede ocultar deriva del edge | **Parcial** — `ClockBadge` muestra estado NTP servidor; reloj display sigue siendo navegador |
| **NTP-M1** | Media | Sin evento de auditoría en transición sync/unsync | **Cerrado** (`persist_system_event`) |
| **NTP-M2** | Baja | `core.py` usa `datetime.now()` naive en mensajes de log | **Abierto** — higiene |
| **NTP-M3** | Media | Monitor solo IPv4/UDP; sin NTS ni claves simétricas | **Parcial** — IPv6 ✅; auth detectada ✅; implementación auth P3 |
| **NTP-M4** | Media | Windows Server como NTP no documentado en runbook | **Cerrado** — `docs/ntp-deployment.md` § Windows Server |
| **NTP-M5** | Media | Sin detección salto brusco de reloj | **Cerrado** — `jump_detected`, CA-NTP-18 |
| **NTP-M6** | Media | Sin diagnóstico de fallo en HMI (`last_error`) | **Cerrado** — API + `ClockSyncPanel`, CA-NTP-19 |
| **NTP-B1** | Baja | Sin tests soak multi-edge (2 edges, Δ offset 24 h) | **Abierto** — Fase C |

---

## 7. Roadmap de implementación

### Fase A — Monitor mínimo viable (P0) ✅

| Entrega | Estado |
|---|---|
| `ntp_monitor.py`, `NtpMonitorWorker`, `clock_alarms.py` | ✅ |
| Health + API clock | ✅ |
| `test_ntp_monitor.py` CA-NTP-01…06 | ✅ |

### Fase B — HMI y settings (P1) ✅

| Entrega | Estado |
|---|---|
| `ClockSyncPanel`, `ClockBadge`, i18n | ✅ |
| PUT settings clock (admin) | ✅ |
| Config HMI > env (sin obligar `.env`) | ✅ |

### Fase B+ — Monitor universal v2.0 (P0/P1) ✅

| Entrega | Evidencia |
|---|---|
| IPv4/IPv6 `getaddrinfo` | CA-NTP-14, CA-NTP-15 |
| Reintentos backoff 1s/2s | CA-NTP-17, `_MAX_RETRIES=2` |
| Detección salto brusco | CA-NTP-18, `ntp_step_threshold_ms` |
| API/HMI diagnóstico | `last_error`, `auth_required_detected`, `jump_detected` |
| Runbook + multi-edge doc | `docs/ntp-deployment.md` |
| Tests | 18 tests OK en `test_ntp_monitor.py` |

### Fase C — Planta multi-edge (P2) — pendiente

| Entrega | Superficie |
|---|---|
| Soak 2-edge | Lab: desplazar chrony en A +500 ms → alarma A, B OK |
| Consola planta | HMI o `/api/system/clock/plant` |
| Docs deploy | `docs/multi-edge.md` ✅, `docs/ntp-deployment.md` ✅ |
| **CA-NTP-06** | Dos edges, mismo NTP; `\|offset_A - offset_B\| < 100 ms` tras 24 h |
| **CA-NTP-07** | Edge A chrony detenido 10 min → alarma + evento; B sin afectación |

### Fase D — Endurecimiento protocolo (P3) — opcional

| Entrega | Notas |
|---|---|
| Autenticación simétrica / NTS (`ntp_auth_type`) | Config reservada; detección kiss-o-death ✅ |
| PTP grandmaster vía chrony `refclock PHC` | Fuera del repo |
| Comparación OPC SourceTimestamp vs recepción | Reloj de campo malo (independiente de NTP edge) |
| Consola planta agregada | `/api/system/clock/plant` |

---

## 8. Despliegue recomendado (documentación operativa)

### 8.1 Host Linux (edge bare-metal o VM)

```ini
# /etc/chrony/chrony.conf (ejemplo planta)
server 192.168.10.5 iburst
server 192.168.10.6 iburst
makestep 1.0 3
rtcsync
```

```bash
timedatectl set-ntp true
chronyc tracking
chronyc sources -v
```

**Hipervisor:** desactivar sincronización de reloj invasiva si compite con chrony.

### 8.2 Host Windows (edge)

```powershell
# Sincronizar contra servidores de planta (ejemplo)
w32tm /config /manualpeerlist:"192.168.10.5,192.168.10.6" /syncfromflags:manual /update
net stop w32time && net start w32time
w32tm /query /status
```

Usar **los mismos servidores** que en HMI → Configuración → Sincronización NTP.

### 8.3 Windows Server como servidor NTP (para edges)

| Paso | Acción |
|---|---|
| Servicio | **Windows Time** en ejecución |
| Registro | Habilitar `NtpServer`; revisar `AnnounceFlags` (documentación Microsoft) |
| Firewall | Regla **entrante UDP 123** desde VLAN OT |
| Prueba | Desde edge Linux: `ntpdate -q 192.168.10.5` o botón «Comprobar ahora» en HMI |
| Dominio | Si solo responde a miembros AD, usar servidor NTP Linux dedicado para edges OT |

### 8.4 Docker Compose

```yaml
# El contenedor NO lleva chrony. El HOST debe estar sincronizado.
services:
  automation:
    # NO usar cap_add: SYS_TIME salvo política explícita de OT
    # Config NTP preferida vía HMI → app_config.json (no obligatorio en environment)
    networks:
      - ot_vlan   # debe permitir UDP 123 saliente hacia servidores NTP
```

### 8.5 Checklist de aceptación en planta

**Red y servidores NTP**

```text
[ ] Salida UDP 123 desde cada edge hacia servidores NTP (y respuesta asociada)
[ ] DNS resuelve hostnames si se usan nombres (no solo IP)
[ ] 2–3 fuentes NTP de planta (primario + respaldo); no pool.ntp.org en producción OT
[ ] Mismo par de servidores en todos los edges de la planta
[ ] Servidor Linux: chrony allow subred OT — o Windows: w32time + firewall UDP 123
```

**Host del edge (disciplina — Capa 1)**

```text
[ ] Linux: chrony active + sources reach* — o Windows: w32time sincronizado
[ ] Servidores chrony/w32time = mismos que panel HMI NTP
[ ] Hipervisor no pisa el reloj del host
```

**PyAutomation (monitor — Capa 3)**

```text
[ ] HMI → Configuración → Sincronización NTP: servidores + intervalo configurados
[ ] POST /api/system/clock/check → synced=true, |offset| < 50 ms (condiciones normales)
[ ] ClockBadge en header en verde
[ ] Simular stop chrony 5–10 min → ALM.NTP.OutOfSync + evento auditoría
[ ] Simular firewall UDP 123 bloqueado → 3 fallos → alarma
[ ] (Opcional) ntp_fail_closed: verificar acquisition_ready=False con reloj malo
```

**Multi-edge (Fase C)**

```text
[ ] Soak 24 h: dos edges, mismo NTP; |offset_A - offset_B| < 100 ms
[ ] Historiador: tendencia multi-tag cross-line alineada (evento de prueba)
[ ] Runbook operativo para ALM.NTP.OutOfSync documentado
```

---

## 9. Relación con auditorías existentes

| Auditoría | Interacción |
|---|---|
| [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md) | Complementaria. TZ = presentación; NTP = epoch. `ClockBadge` coexiste con selector planta/local |
| [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) | Cierra hueco «tiempo» monitor. `NODE_ID` en payload clock. `ntp_fail_closed` suma a `ACQUISITION_BLOCKED_REASON` |
| [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) | Timestamps journal UTC del SO; NTP reduce colisiones `(tag_id, timestamp)` por salto |
| [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) | Eventos sync/unsync → L3 Events |
| [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) | `cycle_timestamp` depende del reloj; monitor no cambia tres relojes SM |

---

## 10. Archivos clave

| Área | Implementado |
|---|---|
| Cliente SNTP | `automation/time/ntp_monitor.py` |
| Config | `automation/time/ntp_config.py` |
| Worker | `automation/workers/ntp_monitor.py` |
| Alarmas | `automation/utils/clock_alarms.py` |
| Core integración | `automation/core.py` (`ntp_worker`) |
| Health | `automation/modules/health/resources/health.py` |
| Settings API | `automation/modules/settings/resources/settings.py` |
| System clock API | `automation/modules/system/` (clock endpoints) |
| HMI | `hmi/src/components/ClockSyncPanel.tsx`, `ClockBadge.tsx`, `services/clock.ts` |
| Multi-edge nodos | `automation/dbmodels/nodes.py` (`ntp_offset_ms`, `ntp_synced`, `ntp_updated_at`) |
| Tests | `automation/tests/test_ntp_monitor.py` |
| Runbook | `docs/ntp-deployment.md` |
| Spec | `specs/03-NTP-EDGE-CLOCK-MONITOR.md` v2.0 |

---

## 11. Veredicto y scorecard

| ID | Capacidad | Pre-implementación | Vigente (2026-08-19) | Objetivo clase mundial |
|---|---|---|---|---|
| NTP-01 | Disciplina de reloj en SO (chrony/w32time) | No documentada | §8 documentado; **deploy OT** | Verificada en cada edge |
| NTP-02 | Misma fuente NTP en todos los edges | No enforced | HMI + runbook | Consola planta (Fase C) |
| NTP-03 | Monitor offset en PyAutomation | ❌ | ✅ SNTP v2 dual-stack | ✅ |
| NTP-04 | Visibilidad HMI | ❌ | ✅ Settings + badge + errores | ✅ |
| NTP-05 | Alarma operador | ❌ | ✅ BOOL ISA | ✅ |
| NTP-06 | Health / observabilidad | ❌ | ✅ `/api/health/system` + diagnóstico | ✅ |
| NTP-07 | Evidencia multi-edge 24 h | ❌ | Pendiente soak | CA-NTP-20 |
| NTP-08 | Fail-closed opcional | ❌ | ✅ `ntp_fail_closed` | Política planta |
| NTP-09 | Compatibilidad servidores (Linux/Win, sin credenciales) | N/A | ✅ IPv4/IPv6 + tooltip HMI | NTS P3 |
| NTP-10 | Robustez (backoff, salto, failover) | N/A | ✅ CA-NTP-16…18 | ✅ |

**Scorecard pre-implementación: 0/8 — grado F.**  
**Scorecard v2.0 (2026-08-19): 8/10 — grado A** (falta soak 2-edge + auth P3 para A+).  
**Tras CA-NTP-20 soak: 9/10 — grado A+.**  
**Tras P3 auth NTS/symmetric: 10/10.**

---

## 12. Respuesta ejecutiva para el equipo

1. **Sí**, todos los edges deben apuntar al **mismo par de servidores NTP de planta**, configurados en el **SO** (chrony en Linux, w32time en Windows), **no** como disciplinador dentro del proceso Python.
2. **Sí**, PyAutomation incorpora un **monitor SNTP ligero** (implementado): scheduler no bloqueante, intervalo configurable desde HMI, alarma cuando el edge está fuera de sync o no alcanza los servidores.
3. **No**, no se necesitan **credenciales** para NTP estándar en VLAN OT (UDP 123). Servidores con autenticación obligatoria (claves simétricas, NTS) **no** están soportados hoy.
4. **Sí**, el monitor funciona con servidores **Linux y Windows Server** siempre que respondan SNTP/NTP en UDP/123; Windows requiere configuración explícita de servidor y firewall.
5. **No**, la estrategia **no es infalible** solo con PyAutomation: la fiabilidad industrial exige **red OT + NTP redundante + disciplina en el host + monitor con alarmas**. PyAutomation detecta; chrony/w32time corrige.
6. La operación «Hora Única» ([AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md)) **no sustituye** esta capacidad; ambas son necesarias para multi-edge de clase mundial.

**Próximo paso:** Fase C — soak 2-edge en planta (CA-NTP-20). Opcional P3: autenticación symmetric/NTS.
