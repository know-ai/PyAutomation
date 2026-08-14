# Auditoría de tendencias en tiempo real — huecos 1 s vs 4 s

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/`) |
| **Pantalla** | `/real-time-trends` (`StripChart` + Redux `tagHistory`) |
| **Síntoma** | La gráfica muestra tramos a ~1000 ms (correcto) y, tras cambiar de pantalla o salir a la terminal **sin cerrar sesión**, tramos a ~4000 ms u otra cadencia. Es **momentáneo** y queda como un segmento más grueso en el eje X. |
| **Campo** | Servidor OPC UA de prueba publicando a **1000 ms**; tags PyAutomation con scan **1000 ms**. |
| **Historiador** | `TagValue` en BD **sí** queda a 1000 ms. |
| **Fecha** | 2026-08-14 |
| **Veredicto** | **Falla de presentación HMI, no de adquisición ni de persistencia.** El socket recibe (o puede recibir) 1 Hz; el buffer de gráfica **descarta muestras intermedias** a propósito por rendimiento. |

---

## 1. Resumen ejecutivo

Hay **tres relojes distintos** en el camino campo → pantalla:

| Reloj | Cadencia observada | Quién lo gobierna |
|---|---|---|
| **A — OPC UA → CVT → journal/BD** | 1000 ms (estable) | `DAS.datachange_notification` → `cvt.set_value_fast` → observadores / SAF |
| **B — Socket.IO `on.tag`** | ~1000 ms por emit (si el valor cambia y no hay deadband) | Mismo `set_value` que A; `sio.emit("on.tag", …)` |
| **C — Buffer HMI de StripChart** | 1000 ms en primer plano; **2–5 s (típico ~4 s)** con pestaña oculta, cambio de ruta o hilo principal ocupado | `useSocket`: `Map` last-wins + flush 1 s / 5 s |

A y B explican que la **base de datos esté bien**. C explica el **diente de sierra visual**.

El patrón “una *parte* de la curva no está a 1 s” es exactamente lo que produce un buffer que **a veces coalescea** (navegación / `document.hidden`) y **a veces no** (pestaña enfocada, hilo libre). Los puntos dispersos **permanecen** en `tagHistory` (hasta 720 por tag), así que al volver a la pantalla se ve el tramo feo mezclado con el tramo denso.

Esto no es un bug de Plotly “inventando” 4 s, ni de PostgreSQL, ni del simulador OPC.

---

## 2. Cadena de datos (campo → píxel)

```
  OPC UA SourceTimestamp ~1 Hz
           │
           ▼
  DAS.update_tag_value                    [automation/opcua/subscription.py]
    · ensure_utc(SourceTimestamp)
    · cvt.set_value_fast(...)             → emit on.tag  (reloj B)
    · das.buffer[tag].timestamp/values    → (buffer in-proc, no es la HMI)
           │
           ▼
  TagObserver / CycleSampleCache / journal
           │
           ▼
  TagValue (UTC epoch ms)                 [reloj A — 1 Hz, verificado en planta]
           │
           ▼
  Socket.IO  event "on.tag"  {name, value, timestamp ISO}
           │
           ▼
  HMI socketService.onTagUpdate
           │
           ▼
  useSocket pendingTagUpdatesRef: Map<name, Tag>   ⚠️ last-wins
           │  flush cada 1000 ms si visible
           │  flush cada 5 ticks (~5 s) si document.hidden
           ▼
  Redux tagHistory[name][]  (máx. 720)
           │
           ▼
  StripChart: copia throttled cada 300 ms → Plotly
              (si hidden: congela lastPlotRef, no borra historial)
```

---

## 3. Hallazgos

### RT-H1 — Coalescing last-wins en `useSocket` (causa raíz)

| | |
|---|---|
| **Severidad** | **Alta** — distorsiona la forma de onda RT; no afecta disco |
| **Archivo** | `hmi/src/hooks/useSocket.ts` |
| **IDs previos** | Introducido como mitigación **HMI-H3** (`AUDIT_HMI_PERFORMANCE.md`): “flush 1 s → 5 s en background” |

Cada `on.tag` hace:

```ts
pendingTagUpdatesRef.current.set(tag.name, tag);
```

`Map.set` **sobrescribe** el valor anterior del mismo tag. En una ventana de flush, N muestras OPC (N×1000 ms) se convierten en **1 punto** en Redux: el último.

Flush:

```ts
const BUFFER_INTERVAL_MS = 1000;
const HIDDEN_FLUSH_EVERY = 5;

setInterval(() => {
  if (isPageHidden()) {
    hiddenTicksRef.current += 1;
    if (hiddenTicksRef.current % HIDDEN_FLUSH_EVERY !== 0) {
      return; // no se vuelca nada
    }
  } else {
    hiddenTicksRef.current = 0;
  }
  flushUpdates();
}, BUFFER_INTERVAL_MS);
```

**Pestaña visible, hilo holgado:** 1 emit/s y 1 flush/s → gráfica a 1000 ms. Coherente con “la mayoría de los casos”.

**Pestaña oculta (Alt+Tab a la terminal, otra ventana encima):**  
- Los ticks 1–4 **no flushean**. El `Map` se queda con un solo valor.  
- Si el operador vuelve **antes del 5.º tick** (~4 s), `hiddenTicksRef` se **resetea a 0 sin haber volcado** esos segundos. El siguiente intervalo visible emite **un único punto** que cubre ~4 s.  
- Eso casa con el “~4000 ms” mejor que un 5 s exacto.

**Pestaña oculta > 5 s:** un punto cada ~5 s mientras sigue hidden; al volver, otro last-wins del resto. “Otra dinámica”.

**Cambio de pantalla HMI (ruta visible, `document.hidden === false`):**  
`useSocket` vive en `MainLayout` y **no se desconecta**. Pero el hilo principal se bloquea (desmontaje Plotly + `react-grid-layout` + hidratación de la nueva página). `setInterval` de 1 s se **retrasa** (timers clamped / long tasks). Mientras tanto el websocket sigue entregando `on.tag` y el `Map` coalescea 2–4 muestras → huecos de 2–4 s **ya escritos** en `tagHistory`. Al regresar a tendencias RT, ese tramo está en el buffer.

Chrome, con pestaña en segundo plano, además **limita timers a ≥ 1 s** y puede alargarlos. Eso multiplica `HIDDEN_FLUSH_EVERY`.

| Condición | Muestras OPC en la ventana | Puntos en `tagHistory` | ΔX aparente |
|---|---|---|---|
| Foreground, 1 Hz, flush a tiempo | 1 | 1 | ~1000 ms |
| Foreground, flush tardío 3–4 s (navegación / Plotly) | 3–4 | **1** | ~3000–4000 ms |
| Hidden 4 s y vuelta antes del tick 5 | 4 | **1** | ~4000 ms |
| Hidden 10 s | ~10 | ~2 | ~5000 ms |

---

### RT-H2 — El historiador no usa ese `Map` (por eso la BD está bien)

`DAS.update_tag_value` llama `set_value_fast` **en cada datachange** (no filtra `get_value()!=val`; ese filtro solo está en `SubHandler`, que no es el handler de planta).

`set_value` emite socket **y** notifica observadores que alimentan el journal / `TagValue`. Caminos **independientes** después del CVT.

Conclusión: un hueco en StripChart **no** implica pérdida en disco. Inverso: disco a 1 Hz **no** prueba que la HMI haya guardado 1 Hz.

---

### RT-H3 — Congelar Plotly en `document.hidden` no crea el hueco; lo *revela*

`StripChart.tsx`:

- Copia `tagHistory` a `throttledHistories` cada **300 ms** (solo retrasa el pintado; no descarta puntos).
- Si `pageHidden`, `plotData` reutiliza `lastPlotRef` (no redibuja).

Al volver, Plotly pinta el historial Redux **ya coalescido**. El throttle 300 ms no explica 4000 ms.

`BUFFER_SIZE_MIN/MAX` = 120–360 puntos (~2–6 min a 1 Hz). Un gap de 4 s es un segmento más largo, no un reset del chart.

---

### RT-H4 — `tagHistory` sobrevive a la navegación (el tramo feo se queda)

`unsubscribeTagHistory` **no borra** el array. `pushHistoryPoint` sigue empujando si `tagHistory[name]` ya existe, aunque el StripChart esté desmontado.

Eso es correcto para no “olvidar” la curva; el efecto colateral es que **los huecos generados fuera de la pantalla siguen ahí** al volver.

Tope: `MAX_HISTORY_POINTS = 720` (~12 min a 1 Hz). Persistencia `localStorage` cada 2 s / al ocultar pestaña: serializa lo que hay, **no re-muestrea**.

---

### RT-H5 — Backend: omisiones posibles, no el patrón del reporte

| Mecanismo | ¿Puede espaciar emits? | ¿Encaja con “tras salir a la terminal”? |
|---|---|---|
| Deadband en `CVT.set_value` / `Tag.set_value` | Sí, si \|Δ\| < deadband: no emit y **tampoco** journal | No: la BD está a 1 Hz |
| `SubHandler` `if tag.get_value()!=val` | Sí, valor idéntico | Planta usa **DAS**, no este handler |
| Gevent/gunicorn ocupado | Retrasa emit; no coalescea 4 s de forma selectiva en la UI | No correlaciona con Alt+Tab |
| Socket.IO fallback `polling` | Cadencia peor si cae websocket | Sería global y sostenido, no un *tramo* |
| Scan OPC 1000 ms | Fuente | OK; BD lo confirma |

No hay evidencia de que el servidor deje de emitir a 1 Hz cuando el operador mira la terminal. El socket **sigue abierto**; HMI-H3 documenta: “El socket sigue recibiendo.”

---

## 4. Reproducción sugerida (sin dudar del OPC)

1. Abrir `/real-time-trends` con 1–2 tags a 1 Hz. Confirmar Δt ≈ 1 s (hover Plotly o `JSON.parse(localStorage.pyautomation.tagHistory)`).
2. Alt+Tab a una terminal **3.5–4.5 s** y volver. Inspeccionar timestamps ISO del mismo tag: debe aparecer **un salto ~4 s** y luego otra vez 1 s.
3. Alt+Tab **12 s**. Esperar saltos ~5 s (flush hidden) más un last-wins al volver.
4. Con la gráfica visible, navegar Tags → Trends RT varias veces (desmonta Plotly). Buscar clusters de Δt 2–4 s coincidiendo con la navegación.
5. En paralelo, consultar `TagValue` del mismo intervalo: Δt ≈ 1000 ms.

DevTools:

- `window.__pyaSocketListeners()` — nativos `on.tag` = 1.
- Consola `[HMI] longtask … ms (real-time-trends)` al cambiar de pantalla.
- Performance: `document.hidden` true mientras la terminal tiene el foco.

---

## 5. Criterio de diseño (conflicto rendimiento vs fidelidad)

HMI-H3 fue deliberado: no despachar Redux/Plotly a 1 Hz×N tags con la pestaña oculta.

Para **valores actuales** (tabla de tags, alarmas, footer) last-wins cada 1–5 s es correcto.

Para **StripChart** last-wins es incorrecto: la gráfica **es** la serie temporal. Descartar el 75 % de las muestras convierte 1 Hz en 0.25 Hz y se ve como “otra dinámica”.

---

## 6. Remediación recomendada (no implementada en esta auditoría)

Prioridad: **RT-H1**. El resto es contexto.

| ID | Cambio | Efecto |
|---|---|---|
| **FIX-1** | Cola/ring **por tag** (no `Map` last-wins) para tags con `historySubscribers` o `tagHistory[name]`. El flush vuelca **todas** las muestras de la ventana, acotadas (p. ej. 20/tag/flush). | Huecos de navegación/hidden desaparecen; Redux sigue acotado a 720. |
| **FIX-2** | En `visibilitychange` → visible: flush inmediato de la cola completa; no resetear `hiddenTicks` sin volcar. | Elimina el caso “4 s y volví antes del tick 5”. |
| **FIX-3** | Separar canales: `updateTagValue` (último valor, coalescible) vs `appendTagHistory` (todas las muestras). Footer/tablas siguen baratas. | SOLID: S — un buffer para UI, otro para forma de onda. |
| **FIX-4** | Opcional: no aplicar `HIDDEN_FLUSH_EVERY` al canal de historial; sí al de “último valor”. | Fidelidad RT sin re-renderizar tablas en background. |

No hace falta tocar OPC, `set_value_fast`, ni el historiador para este síntoma.

---

## 7. Checklist

```text
[x] Historiador TagValue a 1 Hz — camino independiente del Map HMI
[x] Socket on.tag emitido desde el mismo set_value que persiste
[x] useSocket Map last-wins — causa de Δt 2–5 s
[x] HIDDEN_FLUSH_EVERY = 5 — caso Alt+Tab ~4 s
[x] Flush 1 s retrasado por long task / navegación — caso cambio de pantalla
[x] Plotly throttle 300 ms y freeze hidden — no descartan puntos
[x] tagHistory persistente — el tramo feo se ve al volver
[ ] FIX-1..4 (pendiente de implementación)
```

---

## 8. Archivos clave

| Área | Archivo |
|---|---|
| Coalescing / flush hidden | `hmi/src/hooks/useSocket.ts` |
| Historial Redux | `hmi/src/store/slices/tagsSlice.ts` |
| Pintado / freeze | `hmi/src/components/StripChart.tsx` |
| Página | `hmi/src/pages/RealTimeTrends.tsx` |
| `document.hidden` | `hmi/src/hooks/usePageHidden.ts` |
| Socket nativo | `hmi/src/services/socket.ts` |
| OPC → CVT → emit | `automation/opcua/subscription.py`, `automation/tags/cvt.py` |
| Contexto rendimiento HMI | `audits/AUDIT_HMI_PERFORMANCE.md` § HMI-H3 |
