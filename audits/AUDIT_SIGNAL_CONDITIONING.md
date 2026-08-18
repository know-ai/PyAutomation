# Auditoría compacta: acondicionamiento de señal en tags (Gaussiano / proceso / IAD)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/Tags.tsx`) |
| **Alcance** | Filtro gaussiano, filtro de proceso, deadband, IAD (outlier / out-of-range / frozen). CPU en hot path, fugas, idoneidad industrial |
| **Fuera de alcance** | `DedupeFilter` de logs, `filter_by` de API, Plotly, algoritmos LDS/PFM de iDetectFugas |
| **Fecha original** | 2026-08-16 |
| **Compactación** | 2026-08-18 — contraste de código: IAD sigue comentado; `process_filter` sigue sin runtime |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_HMI.md](./AUDIT_HMI.md) |
| **Veredicto estático** | **D+** respecto a grado nuclear / DCS. Hay **una** estrategia de suavizado (Kalman escalar 1D mal llamado «gaussiano»). El **filtro de proceso es fachada**. IAD está **desconectado**. Sin V&V ni manejo de calidad OPC |
| **Clasificación** | Auditoría de acondicionamiento de señal |

---

## 0. Respuesta directa

| Palanca HMI | ¿Runtime? | Qué es |
|---|---|---|
| **Filtro gaussiano** | **Sí, parcial** | Kalman 1D random-walk + adaptación tosca de `R` por innovación |
| **Filtro de proceso** | **No** | Boolean en BD / API / checkbox. Nadie lo lee en `set_value` |
| **Deadband** | **Sí** | Puerta de histéresis: no actualiza si `\|Δ\| < dead_band` |
| **Outlier / OOR / frozen** | **No en el hot path** | Decoradores IAD **comentados**. Outlier/OOR vacíos. Frozen existe y no se llama |

El operador **cree** que hay filtro de ruido de proceso y de medición. En planta solo hay Kalman 1D opcional + deadband. **No** afirmar en planta que PyAutomation «filtra ruido gaussiano y de proceso».

Cadena si Gaussiano ON:

```
OPC datachange (hilo de suscripción — no hacer trabajo caro)
  → set_value_fast → CVT.set_value
  → @filter  (tag.filter → NumPy linalg)  → deadband CVT → Tag.set_value (deadband otra vez)
  → observers / SAF / on.tag
```

---

## 1. Inventario de código

| Pieza | Archivo | Rol |
|---|---|---|
| Kalman + wrapper | `automation/tags/filter.py` | `KalmanFilter`, `GaussianFilter` |
| Decorador | `automation/filter/__init__.py` | `@filter` sobre `CVT.set_value` |
| Estado por tag | `automation/tags/tag.py` | flags, `self.filter = GaussianFilter()`, deadband |
| Escritura | `automation/tags/cvt.py` | `@filter` activo; IAD comentado; `set_value_fast` → `_cvt.set_value` |
| Persistencia / API / HMI | `dbmodels/tags.py`, `modules/tags/resources/tags.py`, `Tags.tsx` | CRUD de flags |
| IAD | `automation/iad/{outliers,out_of_range,frozen_data}.py` | **no enganchado** |
| Alarmas IAD | `state_machine.py` `__define_iad_alarms` | nombre **inconsistente** con IAD |
| Tests | — | **cero** tests de Kalman / process_filter / IAD |

`process_filter` solo constructor / `serialize()` / persistencia. Grep runtime: **ningún** `if tag.process_filter`.

---

## 2. «Gaussiano» — teoría vs código

No es kernel gaussiano (no hay ventana, σ, FIR/IIR). Es Kalman escalar 1er orden:

| Símbolo | Default | Significado |
|---|---|---|
| \(A\) | `[[1]]` | Random walk **sin \(\Delta t\)** |
| \(Q\) | `[[1e-5]]` | Process noise **fijo**, no expuesto |
| \(R\) | `[[0.5]]` luego adaptado | Ruido de medida |
| threshold | `1.0` | Umbral sobre std de **dos** innovaciones |
| r_value | `0.0` | \(R\) cuando la innovación **no** supera el umbral |

Adaptación: si `std([e_{k-1}, e_k]) > threshold` → \(R=0\) (el filtro **deja de filtrar** en el salto, al revés de un spike filter industrial). Default `r_value=0` en calma → seguidor, no suavizador. `np.std` de N=2 no estima varianza.

Dash legado: R 0–100 % y `update_tag` divide por 100. HMI React escribe el float **sin** esa convención → dos escalas.

`@filter` corre **antes** del deadband: el Kalman siempre avanza aunque no se publique. `Tag.set_value` aplica deadband otra vez (**doble puerta**). Estado interno ≠ valor publicado.

No se lee `StatusCode` OPC: BAD entra al Kalman. \(A=1\), \(Q\) constante: asume scan uniforme. No hay reset de \(P\) al reconectar.

---

## 3. Filtro de proceso — ausente

Control de configuración **huérfano**. Activarlo no cambia la señal.

Un DCS suele implementar 1er orden con \(\tau\) en segundos, media móvil de N scans, o el \(Q\) del Kalman. Ninguno está parametrizable. El único «proceso» que corre es el **deadband** (noise gate, no filtro de proceso).

---

## 4. IAD — muerto en el hot path

```python
@filter
# @iad_frozen_data
# @iad_out_of_range
# @iad_outlier
def set_value(...)
```

| Detector | Estado |
|---|---|
| Frozen | varianza < 0.001 → `abnormal_condition`; **no se llama** |
| Outlier / OOR | cuerpo comentado / stub |

Si se reactivara:

| ID | Hallazgo |
|---|---|
| **NF-IAD-1** | `data = dict()` módulo-global; `delete_tag` no hace `pop` → fuga de Buffer |
| **NF-IAD-2** | IAD busca `alarm.iad.{tag}`; `__define_iad_alarms` crea `alarm.{tag}.iad`. **Nunca coinciden** |
| **NF-IAD-3** | Cada muestra instancia `AlarmManager()` y busca por nombre en hilo OPC |
| **NF-IAD-4** | Frozen umbral mágico 0.001; O(n) sobre Buffer default 10 |

---

## 5. CPU / memoria

Con gaussiano ON, cada datachange: lookup extra, `np.linalg.inv` 1×1, `np.std` de 2, alloc de arrays. A 200 tags @ 100–200 ms es **material** en el hilo de notificación OPC (contiende con gevent).

`@logging_error_handler` envuelve `@filter`: si `inv` falla (\(R=0\), \(P\to0\)), la excepción se **traga**, `set_value` no corre, **se pierde la muestra**, sin quality bit.

Kalman **no** es leak de catálogo fijo (estado \(x,P\) vive con el Tag). Riesgo RSS = alloc NumPy cada scan (fragmentación). El soak RSS de [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) **no cubre** filtros ON.

Deadband tras Kalman: menos `on.tag` y menos SAF. Un Kalman con \(R=0\) en transitorios puede **disparar** alarmas de spike.

---

## 6. ¿Grado nuclear / DCS?

| Criterio | Hoy |
|---|---|
| Modelo Q/R documentado | Parcial; Q oculto; nombre «gaussiano» engaña |
| Filtro de proceso scan-aware | **No** |
| Spike / ROC / freeze BAD | **No** |
| CPU acotada en I/O thread | **No** |
| Sin pérdida silenciosa | **No** |
| Parámetros en u.i. + ayuda HMI | Débil |
| Tests / golden traces | **No** |
| IAD alineado ISA-18.2 | **No** |
| Reset bumpless al reconectar | **No** |

Calificación: **D+** — prototipo de laboratorio, inseguro para protección, engañoso para operación.

---

## 7. Hallazgos numerados

| ID | Sev. | Hallazgo |
|---|---|---|
| **NF-1** | Crítica (producto) | `process_filter` teatro de configuración |
| **NF-2** | Alta | Adaptación \(R\): transitorio \(R=0\); calma default 0 |
| **NF-3** | Alta | Kalman + `inv` en hilo OPC |
| **NF-4** | Alta | Excepción en `@filter` → muestra perdida |
| **NF-5** | Media | Sin \(\Delta t\) |
| **NF-6** | Media | Deadband duplicado, posterior al Kalman |
| **NF-7** | Media | Escala R Dash 0–100 ≠ React float |
| **NF-8** | Media | IAD comentado; si se activa: fuga + nombre de alarma roto |
| **NF-9** | Baja | Forma de \(x\) frágil (broadcasting NumPy) |
| **NF-10** | Baja | Cero tests |

---

## 8. Recomendaciones

1. Decir la verdad en la HMI: implementar 1er orden con \(\tau\) **o** ocultar `process_filter`.
2. Sacar Kalman del hilo OPC o reescribir escalar puro; \(Q\) por \(\Delta t\).
3. Innovación grande → **aumentar** \(R\) o hold last good, no \(R=0\).
4. Default `r_value` ≠ 0; documentar \(R\) en % span o u.i.
5. No tragar excepciones: calidad BAD, no avanzar \(x\).
6. Congelar filtro si OPC ≠ Good.
7. Un solo deadband con política explícita.
8. No reactivar IAD hasta NF-IAD-1/2/3; o quitar flags de la HMI.
9. Tests: seno+ruido; spike; hueco de scan; BAD; `delete_tag` limpia dicts IAD.
10. Bench p95 `set_value_fast` 0 % / 100 % gaussiano ON; soak RSS 24 h con filtros ON.

---

## 9. Certificación pendiente

| ID | Evidencia que falta |
|---|---|
| **CA-NF-1** | Bench p95 gaussiano ON vs OFF |
| **CA-NF-2** | Soak 24 h RSS con ≥50 % tags gaussiano ON |
| **CA-NF-3** | Golden trace vs 1er orden / Kalman de referencia |
| **CA-NF-4** | Decisión de producto: implementar o retirar `process_filter` |

Hasta CA-NF-4: *deadband opcional + Kalman 1D experimental, desaconsejado en protección y en hilo de adquisición*.
