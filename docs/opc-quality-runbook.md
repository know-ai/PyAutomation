# Runbook: calidad de señal OPC UA y modo degradado

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO |
| **Specs** | [09](../specs/09-OPC-QUALITY-AND-DEGRADED-STARTUP.md), [10](../specs/10-OPC-QUALITY-A-PLUS.md) |
| **Audiencia** | Operador · ingeniero de procesos · soporte |

---

## 1. Guía de operación — badges G / U / B

| Badge | Significado | Qué hace el sistema | Qué hace el operador |
|---|---|---|---|
| **G** | GOOD — medición viva | Setpoints de proceso se evalúan | Operar con normalidad |
| **U** | UNCERTAIN — valor usable con duda | Setpoints se evalúan **salvo** que Settings tenga «inhibir UNCERTAIN» | Verificar sensor / rango; no tratarlo como fallo duro |
| **B** o **B\*** | BAD o stale (hold-last) | PV congelado en último bueno; **no** dispara alarmas de proceso; activa `ALM.QUALITY.<tag>` | Tratar como pérdida de medición, no como alarma de proceso |

El asterisco (`*`) indica **stale**: el número en pantalla es el último valor bueno, no una muestra viva. El tooltip muestra la edad (`stale age`).

`ALM.QUALITY.<tag>` es una alarma **de sistema** (BOOL). No sustituye a `ALM.OPCUA.<cliente>` (enlace) ni a las alarmas de umbral de proceso.

---

## 2. Incidentes

### 2.1 Sensor Bad / calidad BAD

1. Localizar el tag en Tags: badge **B**, tooltip con substatus si existe (`SensorFailure`, `Overrange`, `LastUsable`, …).
2. Confirmar `ALM.QUALITY.<tag>` activa en Alarmas (no una alarma de presión/temperatura falsa).
3. Corregir el instrumento o el StatusCode en el servidor OPC.
4. Al volver GOOD el PV se actualiza, stale se limpia y `ALM.QUALITY.*` retorna a normal.

### 2.2 Pérdida de enlace OPC UA

1. Alarma de comunicación `ALM.OPCUA.<cliente>`.
2. Todos los PVs de ese cliente pasan a BAD/stale (hold-last).
3. Cada PV de proceso genera `ALM.QUALITY.<tag>`.
4. Al reconectar, muestras GOOD limpian stale y desactivan calidad.

### 2.3 Historiador / BD caído

1. Banner: «Modo degradado: sin conexión al historiador».
2. Adquisición **no** se detiene; SAF journal local.
3. Login 503 incluye **Event ID** (hex). Copiarlo y buscar `event_id=<hex>` en Events / descripción del evento «Database disconnected».
4. Reconectar desde el banner o DatabaseConfigForm. Tras recuperar, el journal se replica (cola SAF → 0).

---

## 3. Configuración — inhibir UNCERTAIN

Ruta HMI: **Settings → Alarmas → Inhibir setpoints con calidad UNCERTAIN**.

- Predeterminado: **desactivado** (UNCERTAIN permite evaluar umbrales).
- Activado: BAD y UNCERTAIN inhiben alarmas de proceso.
- El cambio se aplica en caliente (caché en proceso; no requiere reinicio).

---

## 4. Soak 24 h (CA-OQ-13…15)

Entorno: planta o laboratorio con servidor OPC real/simulado y historiador.

| ID | Procedimiento | Pasa si |
|---|---|---|
| **CA-OQ-13** | Cada 10 min forzar StatusCode Bad 2 min en un PV con alarma de proceso | `ALM.QUALITY.*` ON/OFF; alarma de proceso **no** dispara en Bad; Events «Quality changed» |
| **CA-OQ-14** | Cortar y restaurar el cliente OPC **2 veces** | Tags stale/BAD; `ALM.OPCUA.*` + `ALM.QUALITY.*`; al reconectar GOOD limpia |
| **CA-OQ-15** | Tirar el historiador 30 min; intentar Login; restaurar | Banner degradado; Login muestra Event ID; SAF_QUEUE_DEPTH vuelve a 0; sin excepciones críticas en logs |

Registrar hora, `event_id`, nombres de alarmas y captura del banner. Sin soak formal el veredicto de calidad permanece **A−** (código listo, V&V de planta pendiente).
