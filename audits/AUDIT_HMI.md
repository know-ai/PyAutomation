# Auditoría compacta: HMI (rendimiento 24/7 y tendencias en tiempo real)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomation HMI (`hmi/src`) + emisión Socket.IO del backend |
| **Alcance** | Heap/listeners/re-renders eternos; fidelidad de StripChart vs historiador |
| **Fecha original** | 2026-08-13 (Engranaje Perfecto) / 2026-08-14 (Forma de Onda Perfecta) |
| **Compactación** | 2026-08-18 |
| **Fuentes absorbidas** | `AUDIT_HMI_PERFORMANCE`, `AUDIT_RT_TRENDS` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) (runbook heap), [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) |
| **Veredicto** | Rendimiento HMI **A** (P0/P1/P2 hechos; soak 24 h planta pendiente). Huecos 1 s vs 4 s: **falla de presentación**, no de adquisición. Canal historial = cola por tag (no last-wins) |
| **Clasificación** | Auditoría de frontend · tiempo real |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿La HMI puede vivir 365 días en la misma pestaña? | Diseño acotado: historial 720×64, EventBus (1 listener nativo/evento), pestaña oculta pausa Plotly/polls, Footer no hidrata 10k alarmas. Falta soak 24 h en planta |
| ¿Por qué StripChart mostraba tramos a ~4 s si TagValue está a 1 Hz? | El socket recibía 1 Hz. Un `Map` last-wins + flush 5 s en `document.hidden` **descartaba** muestras. La BD no usa ese Map |
| ¿Eso se corrigió? | **Sí (2026-08-14).** Valor actual sigue last-wins (barato). Historial: cola por tag (máx. 20/flush), flush 1 s aunque hidden, vaciado inmediato al volver a primer plano |

Objetivo: día 365, heap y frame time de Trends RT dentro de ±20 % del día 1.

---

## 1. SOLID aplicados a la HMI (diagnóstico original → estado)

| Letra | Violación original | Estado |
|---|---|---|
| **S** | Footer hidrataba 10k alarmas + preview de 3 | Preview top 3 (`selectActiveAlarmsPreview`) |
| **O** | `tagHistory` hasta 10k/tag sin política de suscripción | 720 pts × 64 tags LRU |
| **L** | Selector de historial global: coste crece con N | Selector por `config.tagNames` |
| **I** | StripChart pedía todo el historial; `useAuth` todo `auth` | Selectores estrechos |
| **D** | Cada página `once("connect")` sobre el socket concreto | EventBus en `socketService` |

---

## 2. Hallazgos de rendimiento (IDs conservados)

### 2.1 Crítico — remediados 2026-08-13

#### HMI-C1 — Historial Redux hasta 10k puntos/tag

`MAX_HISTORY_POINTS = 10000`; spread + `slice` en cada update; `clearTagValues` no se invocaba en logout.

**Hecho:** `MAX_HISTORY_POINTS = 720`; `MAX_HISTORY_TAGS = 64` (LRU). Unsubscribe **no** borra el buffer. Logout **persiste** `localStorage` (`pyautomation.tagHistory`) y **no** vacía el historial (política CA-MEM-8). Sigue recibiendo puntos si el tag ya está rastreado.

#### HMI-C2 — Race `once("connect")` → listeners huérfanos

Si el componente se desmontaba antes del `connect`, el `once` no se cancelaba → N handlers por evento tras meses de navegación.

**Hecho:** EventBus: un `socket.on` nativo por evento, fan-out con `Set`, **sin** `once("connect")`. `disconnect()` hace `removeAllListeners` y vacía Sets. DEV: `socketService.listenerCount()` / `window.__pyaSocketListeners()`.

### 2.2 Alto — remediados

| ID | Hallazgo | Hecho |
|---|---|---|
| **HMI-H1** | StripChart selector global; sin memo; Plotly en cada tag ajeno | Selector por `tagNames`; `React.memo(StripChart)`; throttle 300 ms; freeze si `document.hidden`; `useLongTaskObserver(50)` en RealTimeTrends |
| **HMI-H2** | Footer `getAlarms(1, 10000)` | Preview top 3 |
| **HMI-H3** | Cero `document.hidden` | Flush valor 1 s → 5 s en background; health/machines/communications/Plotly pausan; **el socket sigue recibiendo** |
| **HMI-H4** | `AlarmTableRow` definido *dentro* de `Alarms()` → memo inútil | Módulo propio + `React.memo` |
| **HMI-H5** | Communications poll 1 s escribía `localStorage` | Persistencia debounce 500 ms en onChange; ticker solo UI |
| **HMI-H6** | Callbacks no se re-enlazaban tras `disconnect()` + nuevo `io()` | Cubierto por EventBus |

HMI-H3 es la mitigación que **introdujo** el síntoma de ~4 s en StripChart (ver §3). El canal de historial se separó después.

### 2.3 Medio / bajo — hechos

| ID | Hallazgo | Estado |
|---|---|---|
| HMI-M1/M2 | Doble poll health; context `latencyMs` re-renderizaba Overlay | Un poll en `DatabaseStatusProvider`; contextos `connected` vs `latencyMs` |
| HMI-M3/M4 | `setState` con side effects; 3× interval 1 s en MachinesDetailed | Refs; un ticker |
| HMI-M5 | `setTimeout(200)` Trends sin clear | `relayoutTimeoutRef` + cleanup |
| HMI-M6 | Export CSV `limit: 10000` en React state | Variable local |
| HMI-M7 | Dropdowns sin virtualizar | `VirtualList` si >200 |
| HMI-M8 | Logout no limpiaba slices | Limpia `tagValues`/alarms/machines; **conserva** `tagHistory` |
| Watchdog | — | `useMemoryWatchdog(512)` + `POST /logs/add` una vez por cruce |
| HMI-L1 | Login/Signup timeout sin cleanup | Páginas efímeras |
| HMI-L2 | SCADA rAF | Ruta comentada en router |
| HMI-L3 | `workspaceStore` | Acotado 24 charts |

### 2.4 Lo que ya estaba bien

Buffer 1 s + `batch` Redux. Cleanup de la mayoría de listeners. Strip chart visible 120–360. Workspace máx. 24 charts. Trends: abort fetch, debounce zoom, cache ≤ 8. Paginación Events/AlarmsSummary/DataLogger. `Tags` con memo + comparación por valor RT.

---

## 3. Tendencias RT — huecos 1 s vs 4 s

### 3.1 Tres relojes

| Reloj | Cadencia | Quién |
|---|---|---|
| **A — OPC → CVT → journal/BD** | 1000 ms estable | DAS → `set_value_fast` → SAF |
| **B — Socket `on.tag`** | ~1000 ms por emit | Mismo `set_value`; no depende de PG |
| **C — Buffer HMI** | 1 s en foco; **2–5 s** hidden/navegación (antes del fix de historial) | `useSocket` |

A y B explican que **TagValue esté bien**. C explicaba el diente de sierra visual. No es Plotly inventando 4 s, ni PostgreSQL, ni el simulador OPC.

### 3.2 Cadena campo → píxel

```
OPC UA SourceTimestamp ~1 Hz
    → DAS.update_tag_value → cvt.set_value_fast → emit on.tag
    → TagObserver / journal → TagValue UTC ms          [reloj A]
    → HMI socketService.onTagUpdate
    → useSocket:
         valor actual: Map last-wins, flush 1 s / 5 s hidden
         historial:    cola por tag (máx. 20/flush)     [post Forma de Onda]
    → Redux tagHistory[name][] (máx. 720)
    → StripChart copia throttled 300 ms → Plotly
       (hidden: congela lastPlotRef, no borra historial)
```

### 3.3 Hallazgos RT

#### RT-H1 — Coalescing last-wins (causa raíz original)

`pendingTagUpdatesRef.set(tag.name, tag)` sobrescribe. Con pestaña oculta, ticks 1–4 no flusheaban; si el operador volvía **antes del 5.º tick** (~4 s), `hiddenTicksRef` se reseteaba **sin volcar** → un solo punto cubría ~4 s. Navegación HMI (Plotly unmount + grid) retrasaba el `setInterval` de 1 s → coalescing 2–4 muestras **ya escritas** en `tagHistory`.

| Condición | Muestras OPC | Puntos historial (pre-fix) | ΔX aparente |
|---|---|---|---|
| Foreground, flush a tiempo | 1 | 1 | ~1000 ms |
| Foreground, flush tardío 3–4 s | 3–4 | **1** | ~3000–4000 ms |
| Hidden 4 s y vuelta antes del tick 5 | 4 | **1** | ~4000 ms |
| Hidden 10 s | ~10 | ~2 | ~5000 ms |

#### RT-H2 — El historiador no usa ese Map

`DAS.update_tag_value` llama `set_value_fast` en cada datachange. Journal y socket son caminos **independientes** después del CVT. Hueco en StripChart **≠** pérdida en disco.

#### RT-H3 — Congelar Plotly en hidden no crea el hueco; lo revela

Throttle 300 ms no descarta puntos. `BUFFER_SIZE` 120–360. Un gap de 4 s es un segmento más largo.

#### RT-H4 — `tagHistory` sobrevive a la navegación

`unsubscribeTagHistory` no borra el array. Los huecos generados fuera de la pantalla **siguen ahí** al volver. Tope 720 (~12 min @ 1 Hz). Persistencia `localStorage` cada 2 s / al ocultar: serializa lo que hay, no re-muestrea.

#### RT-H5 — Backend: omisiones posibles, no el patrón del reporte

Deadband sí puede espaciar emits **y** journal (entonces la BD también perdería 1 Hz — no era el caso). Planta usa DAS, no `SubHandler` `if get_value()!=val`. Gevent ocupado retrasa emit de forma global, no un *tramo* al Alt+Tab.

### 3.4 Conflicto rendimiento vs fidelidad

Para **valores actuales** (tabla, alarmas, footer) last-wins cada 1–5 s es correcto.

Para **StripChart** last-wins es incorrecto: la gráfica **es** la serie. Descartar el 75 % convierte 1 Hz en 0.25 Hz.

### 3.5 Remediación — Operación «Forma de Onda Perfecta» (aplicada 2026-08-14)

| ID | Cambio | Efecto |
|---|---|---|
| **FIX-1** | Cola/ring por tag (`pendingHistoryUpdatesRef`) para tags con historial. Flush vuelca **todas** las muestras de la ventana, máx. 20/tag | Huecos de navegación/hidden desaparecen; Redux sigue acotado a 720 |
| **FIX-2** | `visibilitychange` → visible: flush inmediato; no resetear `hiddenTicks` sin volcar | Elimina «4 s y volví antes del tick 5» |
| **FIX-3** | `updateTagValuesBatch` (último valor) vs `appendTagHistoryPoints` (serie) | SRP |
| **FIX-4** | `HIDDEN_FLUSH_EVERY` solo en valor actual / alarmas / máquinas | Fidelidad RT sin re-renderizar tablas en background |

Evidencia de código: `hmi/src/hooks/useSocket.ts` (`pendingHistoryUpdatesRef`, `appendTagHistoryPoints`, flush historial aunque hidden).

### 3.6 Reproducción (regresión)

1. `/real-time-trends` 1–2 tags @ 1 Hz. Δt ≈ 1 s (hover o `localStorage pyautomation.tagHistory`).
2. Alt+Tab 3.5–4.5 s. **Tras el fix** no debe aparecer un salto sistemático de ~4 s en el canal de historial.
3. En paralelo, `TagValue` del mismo intervalo: Δt ≈ 1000 ms siempre.
4. DEV: `window.__pyaSocketListeners()` — nativos `on.tag` = 1. Consola longtask al cambiar de pantalla.

---

## 4. Checklist HMI

```text
[x] MAX_HISTORY 720×64 LRU; persistido; no se vacía en logout
[x] EventBus; sin once("connect"); disconnect limpia
[x] StripChart selector estrecho + memo + throttle 300 ms + freeze hidden
[x] Footer preview 3; AlarmTableRow módulo propio
[x] visibilitychange: polls/Plotly pausan; socket vive
[x] Communications no escribe localStorage en el ticker
[x] VirtualList >200; export CSV fuera de state
[x] Watchdog 512 MB + long task observer Trends RT
[x] Canal historial ≠ last-wins (cola por tag, flush hidden, flush al visible)
[x] Historiador independiente del Map HMI
[ ] Soak 24 h / navegación ×500 en staging (P3 planta)
```

---

## 5. Archivos clave

| Área | Archivo |
|---|---|
| Historial Redux | `hmi/src/store/slices/tagsSlice.ts` |
| Coalescing / colas / hidden | `hmi/src/hooks/useSocket.ts` |
| EventBus | `hmi/src/services/socket.ts` |
| StripChart / freeze | `hmi/src/components/StripChart.tsx` |
| RealTimeTrends | `hmi/src/pages/RealTimeTrends.tsx` |
| `document.hidden` | `hmi/src/hooks/usePageHidden.ts` |
| Footer / alarmas | `hmi/src/layouts/Footer.tsx`, `hmi/src/store/slices/alarmsSlice.ts` |
| AlarmTableRow | `hmi/src/components/AlarmTableRow.tsx` |
| Watchdog | `hmi/src/hooks/useMemoryWatchdog.ts` |
| OPC → CVT → emit | `automation/opcua/subscription.py`, `automation/tags/cvt.py` |
