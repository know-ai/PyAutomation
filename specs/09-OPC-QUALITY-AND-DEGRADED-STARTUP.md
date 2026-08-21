# Documento 09: Calidad OPC UA y arranque degradado

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 2026-08-20 |
| **Producto** | PyAutomationIO (`automation/` + HMI React) |
| **Estado** | **Implementado** — P0/P1 cerrados (calidad OPC → CVT → alarmas → HMI; stale disconnect; Login `event_id`; banner degradado) |
| **Auditoría** | [AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md](../audits/AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md) (verificación post-impl 2026-08-21) |
| **Complementa** | [08-WAVELET-RPA-RT.md](./08-WAVELET-RPA-RT.md), [AUDIT_SIGNAL_CONDITIONING.md](../audits/AUDIT_SIGNAL_CONDITIONING.md), [AUDIT_DB.md](../audits/AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](../audits/AUDIT_STORE_AND_FORWARD.md) |
| **Normas de referencia** | OPC UA Part 4 (StatusCodes), ISA-18.2, prácticas DCS (hold-last, inhibit, stale PV, degraded mode) |
| **Veredicto baseline** | **B−** operativo / **D** en calidad de señal (pre-impl) |
| **Veredicto post-impl** | **A−** disponibilidad · **B+** calidad · **A−** Login/UX degradada |

---

## Índice

| § | Sección |
|---|---|
| 1 | [Objetivo](#objetivo) |
| 2 | [Alcance](#alcance) |
| 3 | [Calidad de señal OPC UA](#calidad-opc) |
| 4 | [Arranque con servidor OPC UA inactivo](#arranque-opc) |
| 5 | [Arranque sin historiador](#arranque-bd) |
| 6 | [Priorización P0 / P1](#priorizacion) |
| 7 | [Plan de implementación](#plan) |
| 8 | [Criterios de aceptación](#criterios) |
| 9 | [Componentes](#componentes) |
| 10 | [Veredicto objetivo](#veredicto) |

---

## 1. Objetivo

<a id="objetivo"></a>

Cerrar las brechas de **semántica de calidad de señal** (OPC UA StatusCode → CVT → alarmas → HMI) y de **trazabilidad en modo degradado** (OPC offline, BD inalcanzable), sin perder la resiliencia actual de arranque no bloqueante y reconexión.

---

## 2. Alcance

<a id="alcance"></a>

| Escenario | Hoy | Meta |
|---|---|---|
| Servidor OPC publica BAD / UNCERTAIN / NaN | StatusCode ignorado; quality default GOOD; alarmas de proceso evalúan valor | Mapear StatusCode → quality; hold-last; inhibir setpoints; badge HMI |
| Arranque con OPC configurado y servidor caído | App no bloquea; alarma `ALM.OPCUA.*`; tags siguen GOOD aparente | Marcar PVs del cliente como BAD/stale |
| Arranque sin alcanzar BD/historiador | App no bloquea; SAF local; Login 503 + `DatabaseConfigForm` | `event_id` en 503; banner «modo degradado» en HMI |

**Fuera de alcance:** certificación SIL/IEC 61508 formal; rediseno del SAF; cambios en el pipeline wavelet `.f` (ya hace HOLD+UNCERTAIN cuando la quality llega al ingest — ver [08](./08-WAVELET-RPA-RT.md)).

---

## 3. Calidad de señal OPC UA

<a id="calidad-opc"></a>

### 3.1. Estado actual

| Pieza | Comportamiento |
|---|---|
| `opcua/subscription.py` | Extrae `SourceTimestamp` y valor; **ignora StatusCode** |
| `CVTEngine.set_value` | No propaga `quality` a `set_value_fast` → default **GOOD** |
| `Alarm.notify` | Evalúa setpoint sin gate de calidad |
| Hold-last | Solo en bloque wavelet (`.f`); el tag **raw** sí se sobrescribe |

Cadena actual:

```
OPC UA datachange (subscription.py)
  → SourceTimestamp
  → (NO StatusCode)
  → cvt.set_value_fast(id, val, timestamp)   # quality = GOOD
  → Tag.set_value(..., quality=GOOD)
  → deadband → Alarm.notify(value)           # sin gate
  → (si filter ON) ingest wavelet
```

### 3.2. Consecuencias

- Sensor Bad puede disparar falsas alarmas de proceso (p. ej. presión baja).
- Operador no ve indicador de calidad en HMI.
- Alarmas de comunicación OPC no inhiben alarmas de proceso.

### 3.3. Estándar esperado (DCS)

1. Mapear StatusCode → `GOOD` / `UNCERTAIN` / `BAD` en el CVT (`quality.py`: `1.0` / `0.5` / `0.0`).
2. Bad/NaN/Inf: **hold last good** en PV raw; actualizar `quality` y `stale_timestamp`.
3. Inhibir alarmas de proceso mientras quality ≠ GOOD (configurable).
4. Alarma de calidad opcional (`ALM.QUALITY.<tag>`).
5. HMI: badge **G / U / B** junto al valor.

---

## 4. Arranque con servidor OPC UA inactivo

<a id="arranque-opc"></a>

### 4.1. Estado actual (robusto en disponibilidad)

- No bloquea el arranque; alarma `ALM.OPCUA.*`; `LoggerWorker` reintenta.
- Tags de proceso **no** se marcan Bad; quedan con último valor (o vacío) y quality GOOD aparente.

### 4.2. Mejora requerida

| Acción | Detalle |
|---|---|
| Disconnect path | Recorrer tags del cliente → `quality=BAD` / `stale=True` **sin** pisar last-good |
| HMI | Mostrar stale / edad de stale en Tags, Trends y Alarmas |

---

## 5. Arranque sin historiador

<a id="arranque-bd"></a>

### 5.1. Estado actual (muy bueno en disponibilidad)

- App no bloquea; SAF journal local; alarma `ALM.DB.Connection`.
- Login **503** con mensaje claro; `DatabaseConfigForm` permite reconfigurar en caliente.
- Reconexión automática; hidratación de catálogo y replay del journal al recuperar.

### 5.2. Brechas UX / trazabilidad

| Gap | Mejora |
|---|---|
| Login 503 sin correlation ID | Incluir `event_id` del evento de desconexión BD reciente |
| Modo degradado poco visible post-login | Banner fijo en header: «Modo degradado: sin conexión al historiador» si `is_db_connected=false` |

---

## 6. Priorización P0 / P1

<a id="priorizacion"></a>

| Prioridad | Acción | Archivos | Criterio de aceptación |
|---|---|---|---|
| **P0** | Propagar `quality` en `CVTEngine.set_value` | `tags/cvt.py` | `set_value(..., quality=BAD)` deja `tag.quality` BAD |
| **P0** | Mapear StatusCode en suscripción OPC UA | `opcua/subscription.py` | Servidor Bad → CVT no queda GOOD |
| **P0** | Hold-last raw; no notify engañoso en Bad | `tags/tag.py` | Bad no cambia PV; sí cambia quality |
| **P0** | Inhibir alarmas de proceso por Bad | `alarms/__init__.py` | Setpoint no dispara en Bad |
| **P1** | Stale al disconnect OPC | `opcua/models.py` + connection path | Disconnect → tags del cliente quality BAD |
| **P1** | HMI badge G/U/B y stale age | HMI Tags / Trends / Alarms | Operador ve calidad y edad stale |
| **P1** | `event_id` en Login 503 | `modules/users/resources/users.py` | 503 incluye correlation ID |
| **P1** | Banner modo degradado | `MainLayout.tsx` | Banner si `is_db_connected=false` |

---

## 7. Plan de implementación

<a id="plan"></a>

### Fase 1 — P0 (calidad y alarmas)

1. Corregir `CVTEngine.set_value` para propagar `quality` a `set_value_fast`.
2. Extraer StatusCode en `subscription.py` y mapear a quality.
3. En `Tag.set_value`: si Bad o valor no finito → no sobrescribir PV; actualizar quality / stale.
4. En `Alarm.notify`: gate por quality; opcionalmente disparar `ALM.QUALITY.<tag>`.

### Fase 2 — P1 (stale OPC y UX)

1. Al desconectar un cliente OPC, marcar sus tags como BAD/stale.
2. Badge G/U/B y `stale_age_ms` en tooltip (Tags, Trends, Alarmas).

### Fase 3 — P1 (Login y banner)

1. Payload 503 de login con `event_id` del evento BD reciente.
2. Banner persistente en header cuando el historiador esté offline.

---

## 8. Criterios de aceptación

<a id="criterios"></a>

| ID | Criterio |
|---|---|
| CA-OQ-01 | `CVTEngine.set_value(..., quality=BAD)` persiste quality BAD/UNCERTAIN en el tag |
| CA-OQ-02 | Suscripción OPC con StatusCode Bad → CVT quality ≠ GOOD |
| CA-OQ-03 | Ingest Bad/NaN/Inf no modifica PV raw (hold last good); sí actualiza quality |
| CA-OQ-04 | `Alarm.notify` no evalúa setpoint cuando quality es BAD (política configurable) |
| CA-OQ-05 | Disconnect de cliente OPC marca tags suscritos como BAD/stale sin pisar last-good |
| CA-OQ-06 | HMI muestra badge G/U/B y stale age en valores de proceso |
| CA-OQ-07 | Login 503 incluye `event_id` correlacionable con Events de BD |
| CA-OQ-08 | Banner «modo degradado» visible si `is_db_connected=false` |

Tests previstos: `automation/tests/test_opc_quality.py` (nuevo), extensión de tests de alarmas y CVT.

---

## 9. Componentes

<a id="componentes"></a>

| Pieza | Ruta |
|---|---|
| Calidad (constantes) | `automation/signal_conditioning/quality.py` |
| Suscripción OPC | `automation/opcua/subscription.py` |
| CVT | `automation/tags/cvt.py` |
| Tag (hold-last) | `automation/tags/tag.py` |
| Alarmas | `automation/alarms/__init__.py` |
| Cliente OPC / disconnect | `automation/opcua/models.py` |
| Login 503 | `automation/modules/users/resources/users.py` |
| HMI badge / banner | `hmi/src/pages/Tags.tsx`, `MainLayout.tsx` |
| Wavelet (referencia HOLD) | [08-WAVELET-RPA-RT.md](./08-WAVELET-RPA-RT.md) |

---

## 10. Veredicto objetivo

<a id="veredicto"></a>

| Dimensión | Baseline | Meta post-Fase 1–3 | Veredicto auditoría 2026-08-21 |
|---|---|---|---|
| Disponibilidad (arranque / reconnect / SAF) | **A−** | Mantener | **A−** |
| Calidad de señal (StatusCode → CVT → alarmas → HMI) | **D** | **B+ / A−** | **B+** |
| Trazabilidad Login / modo degradado UX | **B** | **A−** | **A−** |

**Estado:** Fases 1–3 implementadas. Detalle y evidencia: [AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md](../audits/AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md).
