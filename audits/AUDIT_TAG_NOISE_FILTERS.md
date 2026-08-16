# Auditoría de filtros de ruido en tags — Gaussiano / proceso / IAD

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/Tags.tsx`) |
| **Alcance** | Estrategia de acondicionamiento de señal en la sección de tags: filtro gaussiano, filtro de proceso, deadband, IAD (outlier / out-of-range / frozen). CPU en el hot path de adquisición, fugas de memoria, idoneidad industrial / nuclear |
| **Fuera de alcance** | Filtros de log (`DedupeFilter`), filtros de consulta API (`filter_by`), HMI Plotly, iDetectFugas LDS/PFM |
| **Fecha** | 2026-08-16 |
| **Clasificación** | Auditoría estática de acondicionamiento de señal · confidencialidad interna |
| **Metodología** | Revisión de código + reproducción puntual del Kalman 1D con NumPy. **No** hay bench de p95 ni soak 24 h de CPU/RSS con filtros ON |
| **Complementa** | `audits/AUDIT_MEMORY.md`, `audits/AUDIT_BACKEND_PERFORMANCE.md`, `audits/PERFORMANCE_RUNBOOK.md` |
| **Veredicto estático** | **D+** respecto a grado nuclear / DCS de clase mundial. Existe **una** estrategia de suavizado (Kalman escalar 1D mal llamado «gaussiano»). El **filtro de proceso es fachada** (flag persistido, cero runtime). IAD está **desconectado**. No hay V&V, ni modelo temporal, ni manejo de calidad OPC. |

---

## 1. Resumen ejecutivo

En Definiciones de tags la HMI ofrece cuatro palancas de «filtros / detección»:

| Palanca HMI | ¿Existe estrategia runtime? | Qué es realmente |
|---|---|---|
| **Filtro gaussiano** (`gaussian_filter`) | **Sí, parcial** | Kalman 1D random-walk + adaptación tosca de `R` por innovación |
| **Filtro de proceso** (`process_filter`) | **No** | Boolean en BD / API / checkbox. Nadie lo lee en `set_value` |
| **Deadband** (`dead_band`) | **Sí** | Puerta de histéresis: no actualiza si `\|Δ\| < dead_band` |
| **Outlier / out-of-range / frozen** | **No en el hot path** | Decoradores IAD **comentados**. Algoritmos outlier/OOR vacíos. Frozen existe pero no se llama |

Cadena real cuando el operador marca Gaussiano:

```
  OPC UA datachange  (hilo de suscripción — «no hacer trabajo caro»)
        │
        ▼
  DAS / SubHandler.update_tag_value
        │  set_value_fast
        ▼
  CVT.set_value
        │  @logging_error_handler
        │  @filter          ← si gaussian_filter: tag.filter(value)  [NumPy linalg]
        ▼
  deadband (CVT)  →  Tag.set_value  →  deadband otra vez
        │
        ▼
  observers / SAF / sio.emit("on.tag")
```

Conclusión de producto: el operador **cree** que hay filtro de ruido de proceso y de medición. En planta solo hay (1) Kalman 1D opcional con parámetros mal documentados y (2) deadband. Eso **no** es una estrategia de acondicionamiento de clase nuclear.

---

## 2. Alcance y preguntas del audit

Este archivo responde, con evidencia de código:

1. ¿Hay estrategia de filtro de ruido gaussiano o de proceso en tags?
2. ¿Cuál es y en qué teoría se basa?
3. ¿Qué cuellos de botella tiene?
4. ¿Es implementación de grado nuclear industrial de clase mundial?
5. ¿Qué tal el performance de CPU y el riesgo de memory leak?

---

## 3. Inventario de código

| Pieza | Archivo | Rol |
|---|---|---|
| Kalman + wrapper | `automation/tags/filter.py` | `KalmanFilter`, `GaussianFilter` |
| Decorador hot path | `automation/filter/__init__.py` | `@filter` sobre `CVT.set_value` |
| Estado por tag | `automation/tags/tag.py` | flags, `self.filter = GaussianFilter()`, deadband |
| Escritura CVT | `automation/tags/cvt.py` | `@filter` activo; IAD comentado; `set_value_fast` → `_cvt.set_value` |
| Persistencia | `automation/dbmodels/tags.py` | columnas boolean/float |
| API / HMI | `modules/tags/resources/tags.py`, `hmi/src/pages/Tags.tsx` | CRUD de flags |
| IAD | `automation/iad/{outliers,out_of_range,frozen_data}.py` | **no enganchado** |
| Alta de alarmas IAD | `automation/state_machine.py` `__define_iad_alarms` | nombre de alarma **inconsistente** con IAD |
| Tests | — | **cero** tests de Kalman / process_filter / IAD |

`process_filter` solo aparece en constructor, `serialize()` y persistencia. Grep de runtime: **ningún** `if tag.process_filter`.

---

## 4. Estrategia gaussiana — qué es y en qué se basa

### 4.1 Nombre vs teoría

La UI dice «filtro gaussiano». El docstring del tag dice «Gaussian (Kalman) filtering». El código es un **filtro de Kalman escalar de primer orden**, no un kernel gaussiano (no hay ventana, σ, FIR/IIR gaussiano, ni Savitzky–Golay).

Modelo implementado (`KalmanFilter`):

| Símbolo | Valor por defecto | Significado |
|---|---|---|
| \(A\) | `[[1]]` | Random walk: \(x_k = x_{k-1}\) (**sin \(\Delta t\)**) |
| \(B\) | `[[0]]` | Sin entrada de control |
| \(H\) | `[[1]]` | Se mide el estado directamente |
| \(P_0\) | `[[1]]` | Covarianza inicial |
| \(Q\) | `[[1e-5]]` | «Process noise» **fijo**, no expuesto al operador |
| \(R\) | `[[0.5]]` luego adaptado | Ruido de medición |

Es el suavizador estándar «posición constante + ruido de medida» (equivalente a un pasa-bajos de ganancia de Kalman). Referencias clásicas: Kalman 1960; en proceso, a menudo un **filtro de 1er orden** \(\tau \dot y + y = u\) con \(\tau\) en segundos de scan.

**No** es:

- Filtro gaussiano espacial/temporal (σ configurable).
- Sage–Husa / Mehra / fading-memory para adaptar \(Q,R\).
- Spike filter / rate-of-change limit típico de DCS.
- Filtro de proceso (modelo de planta, \(Q\) por ingeniería, o 1er orden con constante de tiempo).

### 4.2 Adaptación de \(R\) (el «threshold» y el «R-value»)

En `KalmanFilter.update`:

```python
innov = z - H x
if previous_innov is not None:
    innov_var = np.std([previous_innov, innov])   # N = 2
    self.R = 0.0 if innov_var > threshold else r_value
K = P H^T (H P H^T + R)^{-1}
```

| Parámetro HMI | Default | Uso real |
|---|---|---|
| `gaussian_filter_threshold` | `1.0` | Umbral sobre **std de dos innovaciones** (misma unidad que el tag, no normalizado) |
| `gaussian_filter_r_value` | `0.0` | \(R\) cuando la innovación **no** supera el umbral |

Efectos:

- `np.std` de **dos** muestras no estima varianza; es \(\lvert e_k - e_{k-1}\rvert / 2\).
- Si supera `threshold`, \(R = 0\) → se confía ciegamente en la medida (el filtro **deja de filtrar** precisamente cuando hay un salto, que es cuando un spike filter industrial **rechazaría**).
- El default `r_value = 0.0` hace que, en régimen «tranquilo», \(R\) también sea 0 tras la primera adaptación → el Kalman tiende a **seguidor** (pasa-banda), no a suavizador.
- Dash legado muestra R como 0–100 % y `update_tag` divide por 100. La HMI React escribe el float **sin** esa convención → dos UIs, dos escalas.

### 4.3 Orden respecto al deadband

`@filter` corre **antes** del deadband. El Kalman **siempre** avanza con la muestra cruda, aunque después el deadband descarte el publish. El estado interno y lo que ve el operador pueden divergir. `Tag.set_value` vuelve a aplicar deadband: **doble puerta**.

### 4.4 Calidad y tiempo

- No se lee `StatusCode` OPC. Un BAD/UNCERTAIN entra igual al Kalman y corrompe \(x,P\).
- \(A = 1\), \(Q\) constante: asume periodo de muestreo uniforme. Un tag a 100 ms y otro a 5 s comparten la misma dinámica falsa.
- No hay reset de \(P\) al reconectar el cliente, cambiar unidad, o tras un hueco largo.

---

## 5. «Filtro de proceso» — estrategia ausente

`process_filter` está en:

- modelo Peewee, API Flask, checkbox HMI, `Tag.__init__`, `serialize()`.

No está en:

- `CVT.set_value` / `set_value_fast`
- `GaussianFilter` / `KalmanFilter` (el \(Q\) de proceso **no** se liga a este flag)
- workers, DAS, tests

**Veredicto:** es un **control de configuración huérfano**. Activarlo en planta **no cambia la señal**. El operador no tiene forma de saberlo salvo este audit.

Lo que un DCS llama «process filter» suele ser:

- 1er orden con \(\tau\) en segundos (`PV = PV + (raw-PV)*(dt/τ)`), o
- media móvil de N scans, o
- el \(Q\) del Kalman (incertidumbre de planta).

Ninguno de los tres está implementado ni parametrizable desde la HMI.

El único acondicionamiento de «proceso» que **sí** corre es el **deadband** (no es filtro de ruido de proceso; es un *noise gate* / anti-chatter para historiador y sockets).

---

## 6. IAD (outlier / rango / frozen) — muerto en el hot path

En `CVT.set_value`:

```python
@filter
# @iad_frozen_data
# @iad_out_of_range
# @iad_outlier
def set_value(...)
```

| Detector | Código | Estado |
|---|---|---|
| Frozen | varianza muestral \(< 0.001\) → `abnormal_condition` | Implementado, **no se llama** |
| Outlier | cuerpo **comentado** | Stub |
| Out of range | cuerpo **comentado** | Stub |

Hallazgos si se reactivara:

| ID | Hallazgo |
|---|---|
| **NF-IAD-1** | `data = dict()` **módulo-global** por detector, clave = nombre de tag. `delete_tag` **no** hace `pop`. Fuga de `Buffer` por tag borrado/renombrado |
| **NF-IAD-2** | IAD busca alarma `alarm.iad.{tag}`; `__define_iad_alarms` crea `alarm.{tag}.iad`. **Nunca coinciden** |
| **NF-IAD-3** | Cada muestra instancia `AlarmManager()` y busca por nombre. Caro en el hilo OPC |
| **NF-IAD-4** | Frozen: umbral mágico `0.001` sin ingeniería ni deadband de proceso; media/varianza \(O(n)\) sobre `Buffer` (default 10) |

No es una estrategia de ruido; es un esbozo de diagnóstico ISA-18.2 incompleto y desconectado.

---

## 7. Cuellos de botella

### 7.1 CPU — hot path de adquisición

El comentario de `DAS` / `SubHandler` es explícito: *«Do not do expensive, slow or network operation there»*. Con `gaussian_filter=True`, **cada datachange** hace:

- `cvt.get_tag` extra en el decorador (segunda lookup; `set_value` vuelve a `_tags.get`)
- `np.dot` / `np.linalg.inv` de matrices 1×1 (debería ser aritmética escalar)
- `np.std` sobre lista de 2 innovaciones (posiblemente ndarrays 1×1)
- asignaciones de arrays nuevos en `predict`/`update` (heap en cada scan)

Orden de magnitud (estático, sin bench de planta):

| Escenario | Coste relativo vs `set_value` sin filtro |
|---|---|
| Gaussiano OFF | 1× (deadband + lock + serialize socket) |
| Gaussiano ON, 1 tag @ 1 Hz | despreciable |
| Gaussiano ON, 200 tags @ 100–200 ms | **material**: linalg + alloc en el hilo de notificación OPC, contiende con el resto del worker gevent |

`logging_error_handler` envuelve `@filter`. Si `inv` falla (\(R=0\) y \(P\to 0\): \(S \approx 0\)) o cambia el broadcasting de NumPy, la excepción se **traga**, `set_value` no corre, **se pierde la muestra** y no hay alarma de calidad.

### 7.2 CPU — IAD (dormido)

Si se descomentan los decoradores: tres `Buffer` + tres búsquedas de alarma por tag y por muestra. Frozen recorre el buffer en Python puro (`sum` / generador). Peor que el Kalman 1D y aún sin utilidad (NF-IAD-2).

### 7.3 Memoria — fugas y cotas

| Estructura | ¿Acotada? | ¿Fuga? |
|---|---|---|
| `Tag.filter` → `GaussianFilter.kf` | **Sí**. Un estado \(x,P\) (~pocos arrays 1×1) por tag | No. Vive con el tag; `delete_tag` tira el `Tag` |
| `Tag.values` / `Tag.timestamps` | `Buffer` `deque(maxlen)` default 10 | No (política de producto, no leak) |
| IAD `data` dicts | Buffer 10 por tag **si** se activa | **Sí** si se reactiva IAD sin `pop` en `delete_tag` (NF-IAD-1) |
| `process_filter` | 1 bool | Nulo |

El Kalman **no** es un memory leak en régimen de catálogo fijo. El riesgo de RSS está en **allocar NumPy cada scan** (fragmentación / presión de allocator), no en un `list.append` eterno.

No hay soak con filtros ON; el certificado de RSS 24 h de `AUDIT_MEMORY.md` **no cubre** este camino.

### 7.4 Interacción con historiador y HMI

- Deadband tras Kalman: menos `on.tag` y menos filas SAF. Correcto para chatter; **oculta** el residuo del filtro.
- Valor filtrado es el que entra a alarmas y máquinas. Un Kalman con \(R=0\) en transitorios puede **disparar** alarmas de spike en lugar de atenuarlas (adaptación invertida respecto a un spike filter).

---

## 8. ¿Grado nuclear / DCS de clase mundial?

Criterios habituales (IEC 61508 / IEC 61226 / IEEE 7-4.3.2 / prácticas Honeywell–Siemens–Emerson):

| Criterio | PyAutomation hoy | Nota |
|---|---|---|
| Modelo de ruido documentado (Q proceso vs R medida) | Parcial | \(Q\) oculto; \(R\) mal default; nombre «gaussiano» engaña |
| Filtro de proceso con \(\tau\) / scan-aware | **No** | Flag muerto |
| Spike / ROC / bad-status freeze | **No** | BAD OPC entra al estado |
| Determinismo y CPU acotada en I/O thread | **No** | NumPy + `inv` en datachange |
| Sin pérdida silenciosa de muestra | **No** | `logging_error_handler` traga excepciones |
| Parámetros en unidades de ingeniería + ayuda en HMI | Débil | threshold no normalizado; R 0–1 vs 0–100 |
| Pruebas de paridad / replay / golden traces | **No** | 0 tests |
| Diversidad / SIL / V&V independiente | **No** | No aplica ni se reclama |
| IAD / quality flags alineados a ISA-18.2 | **No** | Desconectado + nombre de alarma roto |
| Reset / bumpless transfer al reconectar | **No** | \(P\) y \(x\) quedan sucios |

**No es** implementación de grado nuclear industrial de clase mundial. Es un prototipo de Kalman 1D útil como suavizado opcional de laboratorio, más una UI que promete un filtro de proceso que no existe.

Calificación estática: **D+** (existe un núcleo teórico reconocible; inseguro para protección, engañoso para operación).

---

## 9. Hallazgos numerados

| ID | Sev. | Hallazgo |
|---|---|---|
| **NF-1** | **Crítica (producto)** | `process_filter` no tiene runtime. Checkbox y columna BD son teatro de configuración |
| **NF-2** | Alta | Adaptación de \(R\): en transitorio \(R=0\) (pasa spike); en calma default \(r=0\) (poco suavizado) |
| **NF-3** | Alta | Kalman en el hilo de notificación OPC (`set_value_fast`) con `np.linalg.inv` y alloc |
| **NF-4** | Alta | Excepción en `@filter` → muestra perdida, sin quality bit |
| **NF-5** | Media | Sin \(\Delta t\): \(Q\) idéntico a 100 ms y a 5 s |
| **NF-6** | Media | Deadband duplicado y posterior al Kalman; estado interno ≠ valor publicado |
| **NF-7** | Media | Escala R-value Dash (0–100) ≠ HMI React (float crudo) |
| **NF-8** | Media | IAD comentado; si se activa: fuga `data[tag]`, alarma con nombre incorrecto, outlier/OOR vacíos |
| **NF-9** | Baja | Forma de `x` depende de broadcasting NumPy (escalar → `(1,1)`). Frágil |
| **NF-10** | Baja | Cero tests automatizados del filtro |

---

## 10. Recomendaciones (prioridad)

1. **Decir la verdad en la HMI**: o se implementa filtro de proceso (1er orden con \(\tau\) en segundos, scan-aware) o se oculta `process_filter` hasta que exista runtime.
2. **Sacar el Kalman del hilo OPC** o reescribirlo en escalar puro (`x, P, Q, R` floats, sin `inv`), con \(Q\) escalado por \(\Delta t\).
3. Invertir la lógica de spike: innovación grande → **aumentar** \(R\) o **hold last good**, no \(R=0\).
4. Default `r_value` ≠ 0; documentar \(R\) en % de span o en unidad de ingeniería.
5. No tragar excepciones en el hot path: marcar calidad BAD y no avanzar \(x\).
6. Congelar filtro si OPC status ≠ Good.
7. Un solo deadband, **después** de decidir si se publica, o aplicar deadband a la medida cruda **antes** del Kalman según política explícita.
8. IAD: no reactivar hasta NF-IAD-1/2/3; o borrar flags de la HMI.
9. Tests: replay de seno + ruido gaussiano; spike; hueco de scan; BAD status; `delete_tag` no deja dicts IAD.
10. Bench: p95 de `set_value_fast` con 0 % / 100 % tags con gaussiano ON; soak RSS 24 h con filtros ON (`/api/health/system`).

---

## 11. Mapa de archivos para una corrección

```
  HMI Tags.tsx  ──CRUD flags──► API tags.py ──► dbmodels/tags.py
                                    │
                                    ▼
                              Tag (estado + GaussianFilter)
                                    │
  DAS datachange ──set_value_fast──► CVT.set_value
                                    │  @filter  (único acondicionamiento activo además de deadband)
                                    ▼
                              observers / journal / socket
```

`automation/iad/*` y `process_filter` **no** están en esa flecha vertical.

---

## 12. Certificación pendiente

| ID | Evidencia que falta | Relación |
|---|---|---|
| **CA-NF-1** | Bench p95 `set_value_fast` gaussiano ON vs OFF (N tags × scan) | NF-3 |
| **CA-NF-2** | Soak 24 h RSS con ≥50 % tags gaussiano ON | NF-3, allocator |
| **CA-NF-3** | Golden trace (ruido N(0,σ) + spike) vs 1er orden / Kalman de referencia | NF-2, NF-5 |
| **CA-NF-4** | Decisión de producto: implementar o retirar `process_filter` | NF-1 |

Hasta CA-NF-4, **no** afirmar en planta que PyAutomation «filtra ruido gaussiano y de proceso» en tags. Lo correcto: *deadband opcional + Kalman 1D experimental, desaconsejado en protección y en hilo de adquisición hasta reescritura escalar y tests*.
