# Auditoría de Performance HMI (React) — Operación «Rendimiento Eterno»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomation HMI (`hmi/src`) |
| **Alcance** | Interfaz web 24/7/365: memoria estable, sin fugas, fluidez constante |
| **Clasificación** | Auditoría de rendimiento frontend · Confidencialidad interna |
| **Fecha** | 2026-08-13 (actualizado tras Operación «Engranaje Perfecto») |
| **Metodología** | Revisión estática de hooks, Redux, Socket.IO, listas, ciclos de vida |
| **Principios guía** | SOLID (S/O/L/I/D) aplicados a render, estado y suscripciones |
| **Veredicto** | **A** — P0/P1/P2 **implementados**. P3: watchdog envía logs, `listenerCount` en DEV, long tasks en Trends RT; soak 24 h en planta. |

---

## 1. Resumen ejecutivo

La HMI ya evita varios anti-patrones graves: `useSocket` agrupa actualizaciones cada 1 s con `batch`, Events/AlarmsSummary/DataLogger paginan, StripChart limita el buffer visible (120–360) y el workspace de tendencias RT limita a 24 charts. Eso no basta para «rendimiento eterno».

Los riesgos dominantes a 3–12 meses de sesión abierta son:

1. **`tagHistory` en Redux hasta 10 000 puntos por tag** — heap que crece con el catálogo activo y provoca GC + re-renders globales.
2. **Race `socket.once("connect")`** — listeners huérfanos si el componente se desmonta antes del `connect`.
3. **Selectores Redux demasiado anchos** — cualquier tag re-renderiza todos los StripCharts y el Footer.
4. **Sin `document.hidden`** — intervalos, Plotly y flush RT siguen a plena carga en pestaña oculta.
5. **`AlarmTableRow` memoizado *dentro* del padre** — `React.memo` inútil; re-renders masivos en Alarms.

**Objetivo de aceptación:** el día 365, con la misma sesión (o tras sleep/wake del navegador), el heap de la pestaña y el frame time de Trends RT deben estar dentro del ±20 % del día 1.

---

## 1.1 Estado de implementación (2026-08-13)

| ID | Estado | Qué se hizo |
|---|---|---|
| **HMI-C1** | Hecho | `MAX_HISTORY_POINTS = 720`; `MAX_HISTORY_TAGS = 64` (LRU). Unsubscribe **no** borra el buffer; logout **persiste** historial en `localStorage` (`pyautomation.tagHistory`) y no lo vacía. Sigue recibiendo puntos si el tag ya está rastreado. |
| **HMI-C2** | Hecho | EventBus en `socketService`: un `socket.on` nativo por evento, fan-out con `Set`, **sin** `once("connect")`. `disconnect()` hace `removeAllListeners` y vacía Sets. |
| **HMI-H1** | Hecho | Selector por `config.tagNames`; `React.memo(StripChart)`; throttle Plotly 300 ms; se congela si `document.hidden`. |
| **HMI-H2** | Hecho | Footer usa `selectActiveAlarmsPreview` (top 3); no hidrata 10k. |
| **HMI-H3** | Hecho | `visibilitychange` / `document.hidden`: flush socket 1 s → 5 s en background; health, machines, communications y Plotly pausan. El socket sigue recibiendo. |
| **HMI-H4** | Hecho | `AlarmTableRow` en módulo propio con `React.memo` + comparador. |
| **HMI-H5** | Hecho | Communications persiste selección con debounce 500 ms en onChange; el ticker 1 s solo actualiza UI. |
| **HMI-H6** | Hecho | Cubierto por EventBus (HMI-C2): re-bind nativo en `connect`. |
| **HMI-M1/M2** | Hecho | Un solo poll en `DatabaseStatusProvider`; contextos `connected` vs `latencyMs`. |
| **HMI-M3/M4** | Hecho | Machines: ref de nombres (sin setState en handler); MachinesDetailed: un ticker 1 s. |
| **HMI-M5** | Hecho | `relayoutTimeoutRef` + clear en cleanup de Trends. |
| **HMI-M6** | Hecho | Export CSV usa `limit: 10000` en variable local, no en React state. |
| **HMI-M7** | Hecho | `VirtualList` en `MultiSelectSearch` y dropdown StripChart si >200 opciones. |
| **HMI-M8** | Hecho | Logout limpia `tagValues`/alarms/machines; **conserva** `tagHistory` persistido (tope 720×64). |
| **Watchdog** | Hecho | `useMemoryWatchdog(512)` + `POST /logs/add` al cruzar umbral. |
| **P3 UI** | Hecho | `socketService.listenerCount()` en DEV (`window.__pyaSocketListeners`); `useLongTaskObserver(50)` en RealTimeTrends. |

---

## 2. Principios SOLID aplicados a la HMI

| Letra | Aplicación | Violación detectada |
|---|---|---|
| **S** | Un componente = una responsabilidad de UI | Footer mezcla hidratación de 10k alarmas + preview de 3 activas |
| **O** | Estado abierto a extensión, cerrado a crecimiento sin política | `tagHistory` crece hasta tope alto; alarmas Redux solo crecen |
| **L** | Sustitutos (caché, cola) deben comportarse igual a cualquier tamaño | Selector de `tagHistory` completo: coste crece con N×historial |
| **I** | Hooks/selectores no piden más de lo necesario | StripChart selecciona todo el historial; `useAuth` selecciona todo `auth` |
| **D** | Depender de abstracciones (bus de eventos), no de listeners ad-hoc | Cada página registra su propio `once("connect")` sobre el socket concreto |

---

## 3. Hallazgos (por severidad)

### 3.1 Crítico

#### HMI-C1 — Historial Redux de tags hasta 10k puntos/tag

| | |
|---|---|
| **Severidad** | Crítico — **remediado 2026-08-13** |
| **Componente** | `store/slices/tagsSlice.ts` |
| **Evidencia** | `MAX_HISTORY_POINTS = 10000`; cada update hace spread + `slice(-10000)`. Persistente mientras la sesión autenticada viva. `clearTagValues` existe pero **no se invoca en logout**. |
| **Impacto 24/7** | Con T tags activos: hasta T×10k objetos en heap. GC constante. Cualquier `useAppSelector(s => s.tags.tagHistory)` re-renderiza al actualizar *cualquier* tag. |
| **SOLID** | Viola O (crecimiento sin política de suscripción) e I (consumidores reciben historial global). |

```4:40:hmi/src/store/slices/tagsSlice.ts
const MAX_HISTORY_POINTS = 10000;
// ...
  const newHistory: TagHistoryPoint[] = [
    ...history,
    { timestamp, value: numericValue },
  ].slice(-MAX_HISTORY_POINTS);
```

**Recomendación:**

```ts
// Solo tags suscritos a StripChart / RealTimeTrends
const MAX_HISTORY_POINTS = 720; // ~12 min @ 1 Hz
const pushHistoryPoint = (state, tag, subscribed: Set<string>) => {
  if (!subscribed.has(tag.name)) return;
  const history = state.tagHistory[tag.name] ?? [];
  // Preferir mutación Immer (ya en RTK) sin nuevo array completo si es posible
  history.push({ timestamp, value: numericValue });
  if (history.length > MAX_HISTORY_POINTS) history.splice(0, history.length - MAX_HISTORY_POINTS);
  state.tagHistory[tag.name] = history;
};
```

En logout: `dispatch(clearTagValues()); dispatch(clearAlarms()); dispatch(clearMachines());`.

---

#### HMI-C2 — Race `once("connect")` deja listeners huérfanos

| | |
|---|---|
| **Severidad** | Crítico — **remediado 2026-08-13** |
| **Componente** | `services/socket.ts` (`onTagUpdate`, `onAlarmUpdate`, `onMachineUpdate`, OPC UA) |
| **Evidencia** | Si el socket no está conectado, se registra `socket.once("connect", () => socket.on(event, handler))`. El cleanup hace `off(event, handler)` pero **no cancela** el `once("connect")`. Si `connect` llega tras unmount → listener permanente. |
| **Impacto 24/7** | Tras meses de navegación/reconexiones: N handlers por evento, CPU y fugas de closures. |
| **SOLID** | Viola D (acoplamiento a ciclo de vida del socket concreto) y S (cada suscriptor reimplementa connect). |

```117:150:hmi/src/services/socket.ts
    if (!this.socket || !this.socket.connected) {
      this.connect();
      if (this.socket) {
        this.socket.once("connect", () => {
          this.socket?.on("on.tag", handler);
        });
      }
    } else {
      this.socket.on("on.tag", handler);
    }
    return () => {
      // ... off(handler) — but once("connect") is not cancelled
    };
```

**Recomendación (fan-out centralizado):**

```ts
// Un solo listener por evento; Set de callbacks
private tagListeners = new Set<(t: Tag) => void>();

onTagUpdate(cb: (t: Tag) => void): () => void {
  this.ensureConnected();
  this.tagListeners.add(cb);
  if (!this._tagFanoutBound) {
    this._tagFanoutBound = true;
    this.socket!.on("on.tag", (data) => {
      for (const fn of this.tagListeners) fn(data);
    });
  }
  return () => { this.tagListeners.delete(cb); };
}
```

En `disconnect()`: `removeAllListeners()`, vaciar Sets, reset flags.

---

### 3.2 Alto

#### HMI-H1 — StripChart selecciona todo `tagHistory`

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Componente** | `components/StripChart.tsx`, `pages/RealTimeTrends.tsx` |
| **Evidencia** | Selector global de historial; sin `React.memo` en StripChart; `onDelete={() => ...}` inline. Buffer visible sí está acotado (120–360). |
| **Impacto** | Un update de un tag no mostrado provoca redraw Plotly de todos los charts abiertos. |

**Hecho:** selector por `config.tagNames` + igualdad referencial; `memo(StripChartInner)`; throttle 300 ms; `useLongTaskObserver` en RealTimeTrends.

---

#### HMI-H2 — Footer hidrata hasta 10 000 alarmas

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Componente** | `layouts/Footer.tsx`, `store/slices/alarmsSlice.ts` |
| **Evidencia** | `getAlarms(1, 10000)` + selector de todo el mapa; Footer siempre montado en `MainLayout`. Alarmas Redux sin poda. |
| **Impacto** | Re-render del chrome global en cada batch de socket de alarmas. |

**Hecho:** `selectActiveAlarmsPreview` (top 3 por timestamp); Footer no hidrata el catálogo.

---

#### HMI-H3 — Sin pausa en pestaña oculta

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Componente** | Toda la HMI (`document.hidden` / `visibilitychange`: **0 usos**) |
| **Evidencia** | `useSocket` flush 1 s; Machines / MachinesDetailed intervalos 1 s; Communications poll + `localStorage` 1 s; health polls. |
| **Impacto** | CPU/batería y presión de GC durante turnos con pestaña en background. |

**Recomendación:**

```ts
useEffect(() => {
  const onVis = () => {
    pausedRef.current = document.hidden;
  };
  document.addEventListener("visibilitychange", onVis);
  return () => document.removeEventListener("visibilitychange", onVis);
}, []);
// En el ticker: if (pausedRef.current) return;
```

---

#### HMI-H4 — `AlarmTableRow` definido dentro de `Alarms()`

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Componente** | `pages/Alarms.tsx` |
| **Evidencia** | `const AlarmTableRow = memo(...)` dentro del cuerpo del padre → nueva identidad de componente cada render → memo no evita remount/reconcile costoso. |
| **Contraste positivo** | `Tags.tsx` define el row fuera con comparador custom. |

**Hecho:** `hmi/src/components/AlarmTableRow.tsx` con `React.memo`.

---

#### HMI-H5 — Communications: poll 1 s + escritura `localStorage`

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** |
| **Componente** | `pages/Communications.tsx` |
| **Evidencia** | Intervalo 1 s llama persistencia de nodos seleccionados. |
| **Impacto** | I/O síncrono en main thread; amplifica re-suscripciones OPC UA cuando cambia `clients`. |

**Hecho:** persistencia con debounce 500 ms en onChange; el ticker no escribe `localStorage`.

---

#### HMI-H6 — Arrays de callbacks «para reconexión» no se re-enlazan

| | |
|---|---|
| **Severidad** | Alto — **remediado 2026-08-13** (EventBus HMI-C2) |
| **Componente** | `services/socket.ts` |
| **Evidencia** | `tagCallbacks.push` sin re-registro en `connect` tras `disconnect()` + nuevo `io()`. |
| **Impacto** | Tras reconexión profunda, actualizaciones RT pueden morir en silencio o depender de remount. |

**Recomendación:** fan-out único (§ HMI-C2) o re-bind explícito en handler `connect`.

---

### 3.3 Medio

| ID | Componente | Hallazgo | Recomendación | Estado |
|---|---|---|---|---|
| HMI-M1 | `Header.tsx` + `useDatabaseStatus` | Doble poll health (30 s y 8 s) | Una sola fuente de verdad | **Hecho** |
| HMI-M2 | `DatabaseStatusContext` | Value cambia cada poll (`latencyMs`) → re-render Overlay + LED | Separar `connected` estable de métricas | **Hecho** |
| HMI-M3 | `Machines` / `MachinesDetailed` | `setState(prev => { sideEffect; return prev })` fuerza reconcile | Usar `ref` para leer estado en handlers | **Hecho** |
| HMI-M4 | `MachinesDetailed` | 3× `setInterval(1000)` | Un ticker compartido | **Hecho** |
| HMI-M5 | `Trends.tsx` | `setTimeout(200)` en apply sin clear en unmount | Guardar id + clear en cleanup | **Hecho** |
| HMI-M6 | Events / AlarmsSummary / DataLogger | Export `limit: 10000` mete pico en state | Stream/chunk; no guardar 10k en React state | **Hecho** (local, no state) |
| HMI-M7 | Dropdowns de tags | Sin virtualización | `react-window` / Virtuoso si catálogo > ~200 | **Hecho** (`VirtualList`) |
| HMI-M8 | Logout | No limpia slices tags/alarms/machines | Clears en `logout` | **Hecho** |

### 3.4 Bajo

| ID | Hallazgo | Nota |
|---|---|---|
| HMI-L1 | Login/Signup `setTimeout` sin cleanup | Páginas efímeras |
| HMI-L2 | SCADA con rAF | Ruta comentada en router |
| HMI-L3 | `workspaceStore` | Acotado (24 charts); OK |

---

## 4. Lo que ya está bien

- Buffer 1 s + `react-redux` `batch` en `useSocket`.
- Cleanup de la mayoría de `addEventListener` / intervals en páginas principales.
- Strip chart buffer UI 120–360; workspace máx. 24 charts.
- Trends: abort de fetch, debounce de zoom, cache zoom ≤ 8.
- Paginación en Events / AlarmsSummary / DataLogger.
- `Tags` con `memo` + comparación por valor RT.

---

## 5. Recomendaciones con ejemplo de código

### 5.1 Health check de memoria frontend (monitoreo continuo)

```ts
// hooks/useMemoryWatchdog.ts
export function useMemoryWatchdog(thresholdMb = 512) {
  useEffect(() => {
    const id = setInterval(() => {
      const mem = (performance as any).memory;
      if (!mem) return;
      const usedMb = mem.usedJSHeapSize / (1024 * 1024);
      if (usedMb > thresholdMb) {
        console.warn("[HMI] heap high", usedMb.toFixed(1), "MB");
        // opcional: toast + métrica a /api/logs
      }
    }, 60_000);
    return () => clearInterval(id);
  }, [thresholdMb]);
}
```

Disponible solo en Chromium (`performance.memory`). Complementar con React DevTools Profiler en staging.

### 5.2 Selector granular (patrón I)

```ts
import { createSelector } from "@reduxjs/toolkit";

const selectHistory = (s: RootState) => s.tags.tagHistory;
export const makeSelectTagHistories = (names: string[]) =>
  createSelector([selectHistory], (hist) =>
    Object.fromEntries(names.map((n) => [n, hist[n] ?? []]))
  );
```

---

## 6. Plan de acción priorizado

| Prioridad | Plazo sugerido | Ítems | Criterio de hecho |
|---|---|---|---|
| **P0** | Hecho 2026-08-13 | HMI-C1, HMI-C2 | Historial 720 + suscripción visual; un listener nativo por evento |
| **P1** | Hecho 2026-08-13 | HMI-H1, HMI-H3 | Selector StripChart + pausa pestaña oculta |
| **P2** | Hecho 2026-08-13 | HMI-H2/H4/H5, HMI-M1…M7 | Footer preview; row memo; localStorage onChange; un health poll; virtualización |
| **P3** | Continuo (planta) | Heap + soak 7d | Watchdog → `/logs/add`; `PERFORMANCE_RUNBOOK.md` |

### Pruebas de envejecimiento sugeridas

1. **Soak UI 24 h:** RealTimeTrends con 8 charts, pestaña visible; muestrear heap cada 5 min.
2. **Background 8 h:** misma sesión con `document.hidden`; CPU < 5 % del visible.
3. **Navigate storm:** 500 cambios de ruta + reconnect socket; `socket.listeners("on.tag").length` constante.
4. **Logout/login ×50:** heap vuelve a baseline (±10 %).

---

## 7. Monitoreo continuo

| Señal | Cómo | Umbral sugerido |
|---|---|---|
| JS heap used | `performance.memory` / watchdog | > 512 MB sostenido → aviso |
| Listeners socket | contador interno en `socketService` | crecimiento entre mounts |
| FPS / long tasks | PerformanceObserver `longtask` | > 50 ms en Trends RT |
| Redux size | DevTools / serialización de `tagHistory` lengths | > 720 pts/tag o tags no suscritos |

---

## 8. Conclusión

La HMI ya no acumula 10k puntos por tag ni listeners `once("connect")` huérfanos, y deja de renderizar a pleno cuando la pestaña está oculta. El Footer no hidrata el catálogo, las filas de alarmas tienen memo efectivo y Communications no escribe `localStorage` en el ticker. El heap debe volver a baseline en logout. La certificación (P3) es el soak 24 h / navegación ×500 en staging (`audits/PERFORMANCE_RUNBOOK.md`).
