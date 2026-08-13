# Auditoría de Performance HMI (React) — Operación «Rendimiento Eterno»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomation HMI (`hmi/src`) |
| **Alcance** | Interfaz web 24/7/365: memoria estable, sin fugas, fluidez constante |
| **Clasificación** | Auditoría de rendimiento frontend · Confidencialidad interna |
| **Fecha** | 2026-08-13 (actualizado tras Operación «Rendimiento Eterno») |
| **Metodología** | Revisión estática de hooks, Redux, Socket.IO, listas, ciclos de vida |
| **Principios guía** | SOLID (S/O/L/I/D) aplicados a render, estado y suscripciones |
| **Veredicto** | **A−** — P0 (historial acotado + EventBus) y P1 visibilidad **implementados**. Pendiente P2: Footer 10k alarmas, `AlarmTableRow`, poll Communications |

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
| **HMI-C1** | Hecho | `MAX_HISTORY_POINTS = 720`; historial solo si hay `historySubscribers`; StripChart hace `subscribeTagHistory` / `unsubscribeTagHistory`; logout limpia tags/alarms/machines (`extraReducers` de `logout`). |
| **HMI-C2** | Hecho | EventBus en `socketService`: un `socket.on` nativo por evento, fan-out con `Set`, **sin** `once("connect")`. `disconnect()` hace `removeAllListeners` y vacía Sets. |
| **HMI-H1** | Parcial | Selector por `config.tagNames` con igualdad referencial de arrays; Plotly se congela si `document.hidden`. |
| **HMI-H3** | Hecho | `visibilitychange` / `document.hidden`: flush socket 1 s → 5 s en background; health, machines, communications y Plotly pausan. El socket sigue recibiendo. |
| **Watchdog** | Hecho | `useMemoryWatchdog(512)` en `MainLayout` (Chromium `performance.memory`). |
| **HMI-M8** | Hecho | Clears en la acción `logout`. |

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
| **Severidad** | Alto |
| **Componente** | `components/StripChart.tsx`, `pages/RealTimeTrends.tsx` |
| **Evidencia** | Selector global de historial; sin `React.memo` en StripChart; `onDelete={() => ...}` inline. Buffer visible sí está acotado (120–360). |
| **Impacto** | Un update de un tag no mostrado provoca redraw Plotly de todos los charts abiertos. |

**Recomendación:**

```tsx
const historySlice = useAppSelector(
  (s) => config.tagNames.map((n) => s.tags.tagHistory[n]),
  shallowEqual
);
export default React.memo(StripChart);
```

Throttle de redraw 250–500 ms; pausar si `document.hidden`.

---

#### HMI-H2 — Footer hidrata hasta 10 000 alarmas

| | |
|---|---|
| **Severidad** | Alto |
| **Componente** | `layouts/Footer.tsx`, `store/slices/alarmsSlice.ts` |
| **Evidencia** | `getAlarms(1, 10000)` + selector de todo el mapa; Footer siempre montado en `MainLayout`. Alarmas Redux sin poda. |
| **Impacto** | Re-render del chrome global en cada batch de socket de alarmas. |

**Recomendación:** endpoint o selector `activeAlarmsPreview` (top 3); no hidratar el catálogo completo para el footer.

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
| **Severidad** | Alto |
| **Componente** | `pages/Alarms.tsx` |
| **Evidencia** | `const AlarmTableRow = memo(...)` dentro del cuerpo del padre → nueva identidad de componente cada render → memo no evita remount/reconcile costoso. |
| **Contraste positivo** | `Tags.tsx` define el row fuera con comparador custom. |

**Recomendación:** mover `AlarmTableRow` a módulo o scope de archivo; copiar el patrón de `Tags`.

---

#### HMI-H5 — Communications: poll 1 s + escritura `localStorage`

| | |
|---|---|
| **Severidad** | Alto |
| **Componente** | `pages/Communications.tsx` |
| **Evidencia** | Intervalo 1 s llama persistencia de nodos seleccionados. |
| **Impacto** | I/O síncrono en main thread; amplifica re-suscripciones OPC UA cuando cambia `clients`. |

**Recomendación:** persistir solo en `onChange` de selección con debounce 500 ms; no en el ticker.

---

#### HMI-H6 — Arrays de callbacks «para reconexión» no se re-enlazan

| | |
|---|---|
| **Severidad** | Alto |
| **Componente** | `services/socket.ts` |
| **Evidencia** | `tagCallbacks.push` sin re-registro en `connect` tras `disconnect()` + nuevo `io()`. |
| **Impacto** | Tras reconexión profunda, actualizaciones RT pueden morir en silencio o depender de remount. |

**Recomendación:** fan-out único (§ HMI-C2) o re-bind explícito en handler `connect`.

---

### 3.3 Medio

| ID | Componente | Hallazgo | Recomendación |
|---|---|---|---|
| HMI-M1 | `Header.tsx` + `useDatabaseStatus` | Doble poll health (30 s y 8 s) | Una sola fuente de verdad |
| HMI-M2 | `DatabaseStatusContext` | Value cambia cada poll (`latencyMs`) → re-render Overlay + LED | Separar `connected` estable de métricas |
| HMI-M3 | `Machines` / `MachinesDetailed` | `setState(prev => { sideEffect; return prev })` fuerza reconcile | Usar `ref` para leer estado en handlers |
| HMI-M4 | `MachinesDetailed` | 3× `setInterval(1000)` | Un ticker compartido |
| HMI-M5 | `Trends.tsx` | `setTimeout(200)` en apply sin clear en unmount | Guardar id + clear en cleanup |
| HMI-M6 | Events / AlarmsSummary / DataLogger | Export `limit: 10000` mete pico en state | Stream/chunk; no guardar 10k en React state |
| HMI-M7 | Dropdowns de tags | Sin virtualización | `react-window` / Virtuoso si catálogo > ~200 |
| HMI-M8 | Logout | No limpia slices tags/alarms/machines | Clears en `logout` |

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
| **P1** | Parcial 2026-08-13 | HMI-H3 hecho; HMI-H1 parcial; HMI-H2/H4/H5/H6 abiertos | Pausa en pestaña oculta; selector StripChart granular |
| **P2** | 2–4 semanas | HMI-M1…M7 (M8 hecho) | Un solo health poll; virtualización si catálogo grande |
| **P3** | Continuo | Health check heap + soak 7d | Dashboard interno / alertas |

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

La HMI ya no acumula 10k puntos por tag ni listeners `once("connect")` huérfanos, y deja de renderizar a pleno cuando la pestaña está oculta. El heap debe volver a baseline en logout. Quedan P2 (Footer, filas de alarmas, persistencia 1 s en Communications) y el soak de navegación ×500 en staging.
