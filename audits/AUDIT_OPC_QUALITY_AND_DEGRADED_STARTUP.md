# Auditoría: calidad OPC UA, enlace OPC offline y historiador inalcanzable

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | (1) Señales GOOD/BAD/UNCERTAIN/NaN y alarmas de proceso; (2) arranque con cliente OPC UA configurado y servidor inactivo; (3) arranque sin alcanzar el historiador/BD y trazabilidad en Login |
| **Fecha** | 2026-08-20 |
| **Evidencia de código** | Revisión estática 2026-08-20 |
| **Complementa** | [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md), [docs/auditoria-modulo-alarmas-isa-18-2.md](../docs/auditoria-modulo-alarmas-isa-18-2.md) |
| **Normas de referencia** | OPC UA Part 4 (StatusCodes), ISA-18.2 (alarm management), IEC 61508 / IEC 61511 (ciclo de vida SIS — contraste, no certificación), prácticas DCS/SCADA de clase mundial (hold-last, inhibit, stale PV, degraded mode) |
| **Veredicto vigente** | **B− operativo** (sobrevive y reconecta) / **D nuclear-DCS** en calidad de señal. Enlace OPC y BD: resiliencia **A−**; semántica de calidad y trazabilidad de Login: **gaps críticos** |
| **Clasificación** | Auditoría de disponibilidad · calidad de señal · degradación segura |

---

## 0. Respuesta directa

| Escenario | ¿Qué hace hoy PyAutomation? | ¿Es grado nuclear / clase mundial? | Resultado esperado (norma / DCS) |
|---|---|---|---|
| **Servidor OPC envía BAD / UNCERTAIN / NaN** | La suscripción **ignora `StatusCode`**. El CVT recibe valor con calidad **GOOD por defecto**. NaN/inf se marcan en el tag como UNCERTAIN solo si alguien pasa `quality=` o el valor no es finito en `Tag.set_value`. Las alarmas de proceso evalúan **solo el valor**. El wavelet `.f` sí hace HOLD+UNCERTAIN **si** la calidad llega al ingest | **No.** Falta mapeo Part 4 → quality, hold-last en PV raw, inhibición ISA-18.2 y alarma de calidad de señal | Ver §1.2 |
| **Arranque con OPC configurado y servidor caído** | App **no bloquea**. Cliente queda en memoria; audit `CONNECTION_FAILED`; alarma BOOL `ALM.OPCUA.*`; reconnect en `LoggerWorker`. Tags de proceso **no** se ponen BAD | **Parcial (A− enlace).** Falta marcar PVs stale/BAD al perder enlace | Ver §2.2 |
| **Arranque sin alcanzar BD/historiador** | App **no bloquea**. SAF journal local. Login API **503** + HMI abre `DatabaseConfigForm` con mensaje i18n. Sin catálogo (tags/OPC/usuarios) desde BD | **Parcial (A− disponibilidad, B trazabilidad Login).** Falta modo degradado operador claro y Events visibles sin sesión | Ver §3.2 |

Cadena real de adquisición (hot path):

```
OPC UA datachange (subscription.py)
  → lee SourceTimestamp
  → NO lee StatusCode / Quality
  → cvt.set_value_fast(id, val, timestamp)   # quality default = GOOD (1.0)
  → Tag.set_value(..., quality=GOOD)
  → deadband → notify → Alarm.notify(value)  # sin gate de calidad
  → (si filter ON) ingest wavelet con quality del set_value
```

---

## 1. Calidad OPC UA (GOOD / BAD / UNCERTAIN / NaN) y alarmas

### 1.1. Inventario de código (hoy)

| Pieza | Archivo | Comportamiento actual |
|---|---|---|
| Suscripción DAS | `automation/opcua/subscription.py` → `datachange_notification` / `update_tag_value` | Solo `SourceTimestamp` + valor. **Sin `StatusCode`.** `set_value_fast` sin `quality` |
| Códigos internos | `automation/signal_conditioning/quality.py` | `GOOD=1.0`, `UNCERTAIN=0.5`, `BAD=0.0`. `is_good_quality`: `quality > 0` → **UNCERTAIN se trata como “bueno”** para el anillo wavelet |
| Tag | `automation/tags/tag.py` → `set_value` | Si muestra “mala” (`!is_good_sample`): incrementa `_bad_samples_dropped`, fija `self.quality = UNCERTAIN` (no conserva BAD), **sí sobrescribe `value`** (no hold-last en raw) |
| CVT | `automation/tags/cvt.py` | `CVT.set_value` y `set_value_fast` propagan `quality`. **`CVTEngine.set_value` descarta `quality`** (`return self.set_value_fast(id, value, timestamp)` sin el 4.º arg) |
| Wavelet `.f` | `wavelet_block.py` + `wavelet_worker.py` | BAD/NaN → no entran al ring; **HOLD** + publica último bueno con **UNCERTAIN**. Al recuperar GOOD → OK. Publicación vía `app.cvt.set_value(..., quality=...)` — afectada por el bug de `CVTEngine.set_value` |
| Alarmas de proceso | `automation/alarms/__init__.py` → `Alarm.notify` | Compara valor vs setpoint. **Sin quality, sin inhibit, sin stale** |
| Alarmas de enlace | `automation/utils/connection_alarms.py` | BOOL `SYS.OPCUA.*.Disconnected` / `SYS.DB.Disconnected` + ISA-18.2 lifecycle |
| Wire HMI / SAF | `serialize_socket`, journal | Campo `quality` existe; en adquisición live casi siempre GOOD |

### 1.2. Qué dice el estándar / práctica industrial de clase mundial

Referencias operativas (no es una certificación SIL; es el contrato que un DCS nuclear/industrial espera):

| Principio | Fuente típica | Requisito |
|---|---|---|
| **StatusCode → calidad de PV** | OPC UA Part 4 | `Good` / `Uncertain` / `Bad` (y subcódigos: sensor failure, last usable, etc.) deben llegar al sistema de control y a la HMI |
| **Hold last good** | Práctica DCS (ABB, Emerson, Siemens, Honeywell) | Ante `Bad` o NaN: **congelar** último valor bueno válido; no alimentar control/alarmas con basura |
| **Quality inhibit** | ISA-18.2 + guías de alarm management | Alarmas de proceso **no deben** dispararse / re-dispararse por un PV Bad/Uncertain salvo política explícita; o se genera alarma de **calidad/stale** separada |
| **Separación connection vs process** | ISA-18.2 | Pérdida de enlace ≠ violación de umbral de proceso. Ambas deben ser visibles y trazables |
| **Trazabilidad** | IEC 61511 mindset / NUREG alarm practices | Cada transición de calidad y cada inhibit debe poder auditarse (quién/qué/cuándo) |
| **HMI** | EEMUA 191 / ISA-18.2 HMI | Operador ve badge de calidad (G/U/B), stale age, y no confunde “último valor bueno” con “medición viva” |

### 1.3. Contraste norma vs PyAutomation

| Requisito | Hoy | Gap |
|---|---|---|
| Mapear `StatusCode` OPC → quality CVT | **No** | Crítico |
| Hold-last en tag **raw** ante Bad/NaN | **No** (solo wavelet `.f`) | Crítico para control/alarmas |
| Inhibir alarmas de proceso por Bad/Uncertain | **No** | Crítico ISA-18.2 |
| Alarma dedicada “PV Bad / Stale / No Data” | **No** | Alto |
| Distinguir BAD vs UNCERTAIN en el tag | Tag fuerza UNCERTAIN; UNCERTAIN≈good en wavelet | Medio |
| Propagar quality a `.f` por `CVTEngine.set_value` | **Bug:** se pierde el 4.º argumento | Alto (rompe diseño auditado) |
| Pérdida de enlace → Bad en tags suscritos | Solo alarma BOOL de cliente | Alto |
| Certificación IEC 61508 SIL | Sin V&V / IAD / golden | Fuera de alcance actual (veredicto nuclear **D** en calidad) |

### 1.4. Recomendaciones priorizadas (para cumplir clase mundial)

1. **P0 — Mapear StatusCode en `DAS.datachange_notification`**  
   Extraer `data.monitored_item.Value.StatusCode` → `GOOD` / `UNCERTAIN` / `BAD` y pasar `quality=` a `set_value_fast`.
2. **P0 — Hold-last en `Tag.set_value` para raw** cuando `!is_good_sample`: no sobrescribir valor de proceso; fijar quality BAD/UNCERTAIN; emitir evento/métrica.
3. **P0 — Gate de calidad en `Alarm.notify`**: no evaluar setpoint si quality es BAD (o política configurable BAD+UNCERTAIN); opcional alarma `ALM.QUALITY.<tag>`.
4. **P0 — Corregir `CVTEngine.set_value`** para propagar `quality` (una línea).
5. **P1 — Al perder enlace OPC**: marcar tags del cliente como BAD/stale + `stale_age_ms` en status/HMI.
6. **P1 — HMI**: badge G/U/B en Tags/Trends/Alarms; no mostrar NaN como número “normal”.
7. **P2 — IAD** (outlier/OOR/frozen) enganchado al hot path ([AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md)).

---

## 2. Arranque con Servidor OPC UA configurado e inactivo

### 2.1. Comportamiento actual (evidencia)

```
connect_to_db / hydrate
  → load_opcua_clients_from_db (si DB up)
  → OPCUAClientManager.add → Client.connect()
       · fallo → WARNING + audit CONNECTION_FAILED
       · cliente **permanece** en _clients
       · set_opcua_disconnected(True) → ALM.OPCUA.<client>
  → App continúa (workers, HMI, Socket.IO)
  → LoggerWorker.check_opcua_connection → Client.reconnect() periódico
       · éxito → re-subscribe tags + socket on.opcua.connected
```

| Aspecto | Estado |
|---|---|
| ¿Bloquea el arranque? | **No** — correcto para edge |
| ¿Alarma de conexión? | **Sí** — BOOL + ISA-18.2 |
| ¿Audit trail? | **Sí** — `opcua_audit.py` → Events (fail-safe / SAF) |
| ¿Reintento? | **Sí** — watchdog LoggerWorker + cooldown de spam audit |
| ¿PV de proceso marcados Bad? | **No** — quedan en último valor o vacíos; quality sigue aparentando GOOD |
| ¿HMI? | Toast/socket desconexión; alarma en lista si el catálogo de alarmas está hidratado |

Archivos ancla: `automation/managers/opcua_client.py`, `automation/opcua/models.py`, `automation/utils/connection_alarms.py`, `automation/utils/opcua_audit.py`, `automation/workers/logger.py`, `automation/core.py` (`load_opcua_clients_from_db`, `_hydrate_runtime_from_db_body`).

### 2.2. Resultado esperado (industrial)

| Expectativa | Cumple hoy |
|---|---|
| El runtime edge **no debe caer** si un servidor OPC está down | **Sí** |
| Debe existir alarma de **comunicación** separada de proceso | **Sí** |
| Debe haber reconnect automático con backoff/trazabilidad | **Sí** (mejorable: backoff exponencial formal) |
| Los tags suscritos deben pasar a **Bad/Stale** y no alimentar falsas alarmas de proceso | **No** |
| El operador debe ver claramente “enlace perdido” vs “proceso en alarma” | **Parcial** (alarma BOOL sí; PVs engañosos) |
| Fail-safe / fail-secure según política de planta | **Parcial** — no hay política de “fail position” por tag |

### 2.3. Veredicto y brechas

**Veredicto enlace OPC: A−** (robusto, no bloqueante, trazable a nivel de cliente).  
**Veredicto efecto sobre PVs: D** (no nuclear-grade).

Para clase mundial, además de lo actual:

1. Al detectar disconnect: `for tag in client_tags: set_value(..., quality=BAD)` o flag `stale=True` sin pisar last-good.
2. Suppress/inhibit alarmas de proceso de esos tags mientras el enlace esté Bad.
3. Contador `stale_age_ms` en `/tags/.../status` y Performance.
4. Runbook HMI: banner “OPC client X offline” persistente (no solo toast).

---

## 3. Arranque sin alcanzar el servidor de base de datos (historiador)

### 3.1. Comportamiento actual (evidencia)

```
__start_workers / run
  → connect_to_db(source="core-startup")
       · fallo → _fail_db_link
            · _db_live=False
            · database_connection_auditor.notify_connect_failure
            · set_db_disconnected(True) → ALM.DB.Connection
            · mark_remote_db_dead()
       · App sigue: "App started successfully"
  → SAF journal local operativo (si writers existen)
  → Sin hydrate: no tags/alarmas/usuarios/OPC desde BD
  → LoggerWorker.reconnect_to_db en watchdog
```

**Login / HMI**

| Capa | Comportamiento |
|---|---|
| API `POST /users/login` | **503** + `error_type: database_connection_error` + mensaje de conexión |
| HMI `Login.tsx` | Detecta 503 / hints → **no** muestra solo “credenciales inválidas”; abre **`DatabaseConfigForm`** |
| i18n | `auth.databaseUnavailable`: *“El servicio de autenticación no está disponible. Verifique la conexión a la base de datos.”* |
| Axios | 503 DB **no** fuerza logout de sesión previa |
| Tras configurar BD | `DatabaseConfigForm` → connect → reintento de login |

Archivos: `automation/core.py` (`connect_to_db`, `_fail_db_link`), `automation/utils/db_audit.py`, `automation/modules/users/resources/users.py`, `hmi/src/pages/Login.tsx`, `hmi/src/components/DatabaseConfigForm.tsx`, `hmi/src/locales/es.json` / `en.json`.

### 3.2. Resultado esperado (industrial + trazabilidad)

| Expectativa | Cumple hoy |
|---|---|
| Edge **no congela** el hub ni deja de adquirir si el journal SAF está listo | **Sí** ([AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) **A+**) |
| Alarma de historiador desconectado | **Sí** (`ALM.DB.Connection`) |
| Audit de fallo de conexión con cooldown (sin spam) | **Sí** (`db_audit`) |
| Login **no** debe aparentar “password incorrecto” | **Sí** — 503 + formulario BD |
| Mensaje claro al operador en Login | **Sí** — i18n `databaseUnavailable` + UI de reconfiguración |
| Operador puede ver Events/bitácora **sin** sesión cuando solo falló el historiador | **No** (Login es la puerta; sin token no hay HMI operativa) |
| Cold start sin BD: catálogo vacío es explícito en HMI (“sin configuración / degraded”) | **Parcial** — depende de si había estado en memoria |
| Exactamente-una-vez y durabilidad de muestras durante outage | **Sí** — SAF journal |

### 3.3. ¿Cumplimos trazabilidad?

| Pregunta | Respuesta |
|---|---|
| ¿El fallo de BD queda registrado? | **Sí**, en audit de sistema / Events cuando el store lo permite; alarma BOOL activa |
| ¿El Login muestra trazabilidad? | **Sí a nivel operador**: mensaje i18n + flujo de reconfiguración. **No** muestra el Event ID / correlation ID del fallo |
| ¿Cómo debe funcionar el sistema? | Degraded mode: adquisición→SAF local; alarmas de enlace en memoria; Login bloquea autenticación hasta historiador reachable; reconnect automático; al recuperar → hydrate + flush SAF |

### 3.4. Veredicto y brechas

**Veredicto disponibilidad BD: A−.**  
**Veredicto UX/trazabilidad Login: B.**

Para clase mundial:

1. Banner global “Historiador desconectado” post-login (ya hay overlay de DB en MainLayout — verificar cobertura cold-start).
2. En Login: correlacionar con `ALM.DB.Connection` / último Event (timestamp, host) sin exigir sesión admin.
3. Distinguir “BD no configurada” vs “BD inalcanzable” vs “credenciales BD inválidas” en el payload 503 (parcialmente existe).
4. Modo read-only de emergencia con catálogo embebido/snapshot (opcional, plantas críticas).

---

## 4. Matriz de veredictos

| Dominio | Operativo planta | Nuclear / DCS clase mundial |
|---|---|---|
| Calidad de señal OPC → CVT → alarmas | **D** (invisible StatusCode) | **D** |
| Wavelet `.f` HOLD (diseño) | **A−** (si quality llega) | **B** (depende de P0 CVTEngine + StatusCode) |
| Enlace OPC offline al arranque | **A−** | **B−** (falta Bad/stale en PVs) |
| Historiador offline + SAF | **A** | **A−** |
| Login ante BD caída | **B+** (mensaje + form) | **B** (sin correlation ID / degraded ops) |

**Veredicto global de este documento: B− operativo / D en calidad de señal para grado nuclear.**

---

## 5. Plan mínimo para cerrar gaps P0 (orden sugerido)

| # | Cambio | Archivos | Criterio de aceptación |
|---|---|---|---|
| 1 | Propagar `quality` en `CVTEngine.set_value` | `tags/cvt.py` | Test: `set_value(..., quality=BAD)` deja `tag.quality` BAD/UNCERTAIN |
| 2 | Mapear `StatusCode` en suscripción | `opcua/subscription.py` | Servidor que publica Bad → CVT no queda GOOD |
| 3 | Hold-last raw + no notify engañoso | `tags/tag.py` | Bad no cambia PV de proceso; sí cambia quality |
| 4 | Inhibit alarmas de proceso por Bad | `alarms/__init__.py` | Setpoint no dispara en Bad |
| 5 | Stale al disconnect OPC | `opcua/models.py` + connection path | Disconnect → tags del cliente quality BAD |
| 6 | Tests de integración + soak 24 h | `automation/tests/` | Suite verde + evidencia soak |

---

## 6. Cross-links

| Tema | Documento |
|---|---|
| Wavelet / HOLD / `.f` | [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md) |
| Conexiones Peewee / no freeze hub | [AUDIT_DB.md](./AUDIT_DB.md) |
| Durabilidad sin historiador | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) |
| Events / bitácora | [AUDIT_LOGGING.md](./AUDIT_LOGGING.md) |
| ISA-18.2 estados | [docs/auditoria-modulo-alarmas-isa-18-2.md](../docs/auditoria-modulo-alarmas-isa-18-2.md) |
| Spec wavelet | [specs/08-WAVELET-RPA-RT.md](../specs/08-WAVELET-RPA-RT.md) |

---

## 7. Anclas de código (checklist de re-auditoría)

```
automation/opcua/subscription.py          # StatusCode ausente
automation/tags/tag.py                    # set_value / quality / hold
automation/tags/cvt.py                    # CVTEngine.set_value pierde quality
automation/signal_conditioning/quality.py
automation/signal_conditioning/wavelet_block.py
automation/workers/wavelet_worker.py
automation/alarms/__init__.py             # notify sin quality gate
automation/utils/connection_alarms.py
automation/utils/opcua_audit.py
automation/utils/db_audit.py
automation/opcua/models.py               # connect / reconnect
automation/managers/opcua_client.py
automation/core.py                       # connect_to_db / load_opcua / _fail_db_link
automation/workers/logger.py              # reconnect OPC + DB
automation/modules/users/resources/users.py  # login 503
hmi/src/pages/Login.tsx
hmi/src/components/DatabaseConfigForm.tsx
hmi/src/locales/es.json                   # auth.databaseUnavailable
```
