# Auditoría: HMI (rendimiento, tendencias RT, socket, machines/domain)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Documento canónico** | 03 / 10 |
| **Fecha de agrupación** | 2026-09-16 |
| **Fuentes absorbidas** | `AUDIT_HMI`, `AUDIT_HMI_PERFORMANCE`, `AUDIT_RT_TRENDS`, `AUDIT_REALTIME_TRENDS_UIUX`, `AUDIT_HMI_SOCKET_TRACEABILITY`, `AUDIT_HMI_MACHINE_DOMAIN_EXTENSION` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_TIME.md](./AUDIT_TIME.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_ALARMS.md](./AUDIT_ALARMS.md), [AUDIT_AUTH_AUTHORIZATION.md](./AUDIT_AUTH_AUTHORIZATION.md) |
| **Veredicto vigente** | Heap **A** · forma de onda RT cola por tag · layout RT **B+ código** / datos **A−** · socket **A+** código · machines/domain **A** Schema-Driven |
| **Clasificación** | Auditoría de contraste código vs diseño. IDs de hallazgos conservados. |


Este archivo agrupa **todas** las auditorías del dominio. Cada parte conserva el texto original.

## Índice de partes

- [Parte A — Rendimiento 24/7 y tendencias en tiempo real](#parte-a-rendimiento-247-y-tendencias-en-tiempo-real)
- [Parte B — UI/UX de Tendencias en Tiempo Real](#parte-b-uiux-de-tendencias-en-tiempo-real)
- [Parte C — Trazabilidad Socket HMI](#parte-c-trazabilidad-socket-hmi)
- [Parte D — Extensión HMI machines/domain](#parte-d-extensión-hmi-machinesdomain)

---

## Parte A — Rendimiento 24/7 y tendencias en tiempo real

> Fuente original: `AUDIT_HMI.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomation HMI (`hmi/src`) + emisión Socket.IO del backend |
| **Alcance** | Heap/listeners/re-renders eternos; fidelidad de StripChart vs historiador |
| **Fecha original** | 2026-08-13 (Engranaje Perfecto) / 2026-08-14 (Forma de Onda Perfecta) |
| **Compactación** | 2026-08-18 |
| **Fuentes absorbidas** | `AUDIT_HMI_PERFORMANCE`, `AUDIT_RT_TRENDS` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) (runbook heap), [AUDIT_TIME.md](./AUDIT_TIME.md), [AUDIT_DB.md](./AUDIT_DB.md) |
| **Veredicto** | Rendimiento HMI **A** (P0/P1/P2 hechos; soak 24 h planta pendiente). Huecos 1 s vs 4 s: **falla de presentación**, no de adquisición. Canal historial = cola por tag (no last-wins) |
| **Clasificación** | Auditoría de frontend · tiempo real |

---

### 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿La HMI puede vivir 365 días en la misma pestaña? | Diseño acotado: historial 720×64, EventBus (1 listener nativo/evento), pestaña oculta pausa Plotly/polls, Footer hidrata `GET /alarms/footer` (top 3). Falta soak 24 h en planta |
| ¿Por qué StripChart mostraba tramos a ~4 s si TagValue está a 1 Hz? | El socket recibía 1 Hz. Un `Map` last-wins + flush 5 s en `document.hidden` **descartaba** muestras. La BD no usa ese Map |
| ¿Eso se corrigió? | **Sí (2026-08-14).** Valor actual sigue last-wins (barato). Historial: cola por tag (máx. 20/flush), flush 1 s aunque hidden, vaciado inmediato al volver a primer plano |

Objetivo: día 365, heap y frame time de Trends RT dentro de ±20 % del día 1.

---

### 1. SOLID aplicados a la HMI (diagnóstico original → estado)

| Letra | Violación original | Estado |
|---|---|---|
| **S** | Footer hidrataba 10k alarmas + preview de 3 | Preview `top3Active` (`selectActiveAlarmsPreview`) + `GET /alarms/footer` |
| **O** | `tagHistory` hasta 10k/tag sin política de suscripción | 720 pts × 64 tags LRU |
| **L** | Selector de historial global: coste crece con N | Selector por `config.tagNames` |
| **I** | StripChart pedía todo el historial; `useAuth` todo `auth` | Selectores estrechos |
| **D** | Cada página `once("connect")` sobre el socket concreto | EventBus en `socketService` |

---

### 2. Hallazgos de rendimiento (IDs conservados)

#### 2.1 Crítico — remediados 2026-08-13

##### HMI-C1 — Historial Redux hasta 10k puntos/tag

`MAX_HISTORY_POINTS = 10000`; spread + `slice` en cada update; `clearTagValues` no se invocaba en logout.

**Hecho:** `MAX_HISTORY_POINTS = 720`; `MAX_HISTORY_TAGS = 64` (LRU). Unsubscribe **no** borra el buffer. Logout **persiste** `localStorage` (`pyautomation.tagHistory`) y **no** vacía el historial (política CA-MEM-8). Sigue recibiendo puntos si el tag ya está rastreado.

##### HMI-C2 — Race `once("connect")` → listeners huérfanos

Si el componente se desmontaba antes del `connect`, el `once` no se cancelaba → N handlers por evento tras meses de navegación.

**Hecho:** EventBus: un `socket.on` nativo por evento, fan-out con `Set`, **sin** `once("connect")`. `disconnect()` hace `removeAllListeners` y vacía Sets. DEV: `socketService.listenerCount()` / `window.__pyaSocketListeners()`.

#### 2.2 Alto — remediados

| ID | Hallazgo | Hecho |
|---|---|---|
| **HMI-H1** | StripChart selector global; sin memo; Plotly en cada tag ajeno | Selector por `tagNames`; `React.memo(StripChart)`; throttle 300 ms; freeze si `document.hidden`; `useLongTaskObserver(50)` en RealTimeTrends |
| **HMI-H2** | Footer `getAlarms(1, 10000)` | **Cerrado v3:** `getAlarmsFooter()` + store `top3Active` ≤ 3. `/alarms` pagina ≤ 50. |
| **HMI-H3** | Cero `document.hidden` | Flush valor 1 s → 5 s en background; health/machines/communications/Plotly pausan; **el socket sigue recibiendo** |
| **HMI-H4** | `AlarmTableRow` definido *dentro* de `Alarms()` → memo inútil | Módulo propio + `React.memo` |
| **HMI-H5** | Communications poll 1 s escribía `localStorage` | Persistencia debounce 500 ms en onChange; ticker solo UI |
| **HMI-H6** | Callbacks no se re-enlazaban tras `disconnect()` + nuevo `io()` | Cubierto por EventBus |

HMI-H3 es la mitigación que **introdujo** el síntoma de ~4 s en StripChart (ver §3). El canal de historial se separó después.

#### 2.3 Medio / bajo — hechos

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

#### 2.4 Lo que ya estaba bien

Buffer 1 s + `batch` Redux. Cleanup de la mayoría de listeners. Strip chart visible 120–360. Workspace máx. 24 charts. Trends: abort fetch, debounce zoom, cache ≤ 8. Paginación Events/AlarmsSummary/DataLogger. `Tags` con memo + comparación por valor RT.

---

### 3. Tendencias RT — huecos 1 s vs 4 s

#### 3.1 Tres relojes

| Reloj | Cadencia | Quién |
|---|---|---|
| **A — OPC → CVT → journal/BD** | 1000 ms estable | DAS → `set_value_fast` → SAF |
| **B — Socket `on.tag`** | ~1000 ms por emit | Mismo `set_value`; no depende de PG |
| **C — Buffer HMI** | 1 s en foco; **2–5 s** hidden/navegación (antes del fix de historial) | `useSocket` |

A y B explican que **TagValue esté bien**. C explicaba el diente de sierra visual. No es Plotly inventando 4 s, ni PostgreSQL, ni el simulador OPC.

#### 3.2 Cadena campo → píxel

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

#### 3.3 Hallazgos RT

##### RT-H1 — Coalescing last-wins (causa raíz original)

`pendingTagUpdatesRef.set(tag.name, tag)` sobrescribe. Con pestaña oculta, ticks 1–4 no flusheaban; si el operador volvía **antes del 5.º tick** (~4 s), `hiddenTicksRef` se reseteaba **sin volcar** → un solo punto cubría ~4 s. Navegación HMI (Plotly unmount + grid) retrasaba el `setInterval` de 1 s → coalescing 2–4 muestras **ya escritas** en `tagHistory`.

| Condición | Muestras OPC | Puntos historial (pre-fix) | ΔX aparente |
|---|---|---|---|
| Foreground, flush a tiempo | 1 | 1 | ~1000 ms |
| Foreground, flush tardío 3–4 s | 3–4 | **1** | ~3000–4000 ms |
| Hidden 4 s y vuelta antes del tick 5 | 4 | **1** | ~4000 ms |
| Hidden 10 s | ~10 | ~2 | ~5000 ms |

##### RT-H2 — El historiador no usa ese Map

`DAS.update_tag_value` llama `set_value_fast` en cada datachange. Journal y socket son caminos **independientes** después del CVT. Hueco en StripChart **≠** pérdida en disco.

##### RT-H3 — Congelar Plotly en hidden no crea el hueco; lo revela

Throttle 300 ms no descarta puntos. `BUFFER_SIZE` 120–360. Un gap de 4 s es un segmento más largo.

##### RT-H4 — `tagHistory` sobrevive a la navegación

`unsubscribeTagHistory` no borra el array. Los huecos generados fuera de la pantalla **siguen ahí** al volver. Tope 720 (~12 min @ 1 Hz). Persistencia `localStorage` cada 2 s / al ocultar: serializa lo que hay, no re-muestrea.

##### RT-H5 — Backend: omisiones posibles, no el patrón del reporte

Deadband sí puede espaciar emits **y** journal (entonces la BD también perdería 1 Hz — no era el caso). Planta usa DAS, no `SubHandler` `if get_value()!=val`. Gevent ocupado retrasa emit de forma global, no un *tramo* al Alt+Tab.

#### 3.4 Conflicto rendimiento vs fidelidad

Para **valores actuales** (tabla, alarmas, footer) last-wins cada 1–5 s es correcto.

Para **StripChart** last-wins es incorrecto: la gráfica **es** la serie. Descartar el 75 % convierte 1 Hz en 0.25 Hz.

#### 3.5 Remediación — Operación «Forma de Onda Perfecta» (aplicada 2026-08-14)

| ID | Cambio | Efecto |
|---|---|---|
| **FIX-1** | Cola/ring por tag (`pendingHistoryUpdatesRef`) para tags con historial. Flush vuelca **todas** las muestras de la ventana, máx. 20/tag | Huecos de navegación/hidden desaparecen; Redux sigue acotado a 720 |
| **FIX-2** | `visibilitychange` → visible: flush inmediato; no resetear `hiddenTicks` sin volcar | Elimina «4 s y volví antes del tick 5» |
| **FIX-3** | `updateTagValuesBatch` (último valor) vs `appendTagHistoryPoints` (serie) | SRP |
| **FIX-4** | `HIDDEN_FLUSH_EVERY` solo en valor actual / alarmas / máquinas | Fidelidad RT sin re-renderizar tablas en background |

Evidencia de código: `hmi/src/hooks/useSocket.ts` (`pendingHistoryUpdatesRef`, `appendTagHistoryPoints`, flush historial aunque hidden).

#### 3.6 Reproducción (regresión)

1. `/real-time-trends` 1–2 tags @ 1 Hz. Δt ≈ 1 s (hover o `localStorage pyautomation.tagHistory`).
2. Alt+Tab 3.5–4.5 s. **Tras el fix** no debe aparecer un salto sistemático de ~4 s en el canal de historial.
3. En paralelo, `TagValue` del mismo intervalo: Δt ≈ 1000 ms siempre.
4. DEV: `window.__pyaSocketListeners()` — nativos `on.tag` = 1. Consola longtask al cambiar de pantalla.

---

### 4. Checklist HMI

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

### 5. Archivos clave

| Área | Archivo |
|---|---|
| Historial Redux | `hmi/src/store/slices/tagsSlice.ts` |
| Coalescing / colas / hidden | `hmi/src/hooks/useSocket.ts` |
| EventBus | `hmi/src/services/socket.ts` |
| StripChart / freeze | `hmi/src/components/StripChart.tsx` |
| RealTimeTrends | `hmi/src/pages/RealTimeTrends.tsx` |
| `document.hidden` | `hmi/src/hooks/usePageHidden.ts` |
| Footer / alarmas | `hmi/src/layouts/Footer.tsx`, `hmi/src/store/slices/alarmsSlice.ts` |
| AlarmTableRow | `hmi/src/components/AlarmTableRow.tsx` — **2026-09-15:** badge “condición activa” (`condition_met`) distinto de ack ISA-18.2. Contrato: [AUDIT_DB.md](./AUDIT_DB.md) §3.5 |
| Footer «últimas 3» | `hmi/src/layouts/Footer.tsx` — RTN Unack en Redux; orden **priority luego** `last_transition_ts`; B/C/D con color distinto. Cotas store `top3Active`≤3 / page≤50 / history≤100. P2: `priority` en payload. Ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |
| Watchdog | `hmi/src/hooks/useMemoryWatchdog.ts` |
| OPC → CVT → emit | `automation/opcua/subscription.py`, `automation/tags/cvt.py` |


## Parte B — UI/UX de Tendencias en Tiempo Real

> Fuente original: `AUDIT_REALTIME_TRENDS_UIUX.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomation HMI (`hmi/src`) |
| **Alcance** | Estética, usabilidad, layout/canvas, edición de cards, picker de tags y granularidad de movimiento de la vista de tendencias en tiempo real. **No** cubre fidelidad de serie ni heap (eso vive en [AUDIT_HMI.md](./AUDIT_HMI.md)) |
| **Fecha** | 2026-09-09 · **implementación spec HMI 2.10** misma fecha |
| **Evidencia** | Código `hmi/src/pages/RealTimeTrends.tsx`, `StripChart.tsx`, `workspaceStore.ts`, `realtimeTrendsGrid.ts`, `usePlotlyResize.ts`, `global.css`; backend `automation/modules/settings/workspace.py`; tests `test_realtime_trends_workspace.py` |
| **Complementa** | [AUDIT_HMI.md](./AUDIT_HMI.md) (rendimiento RT / forma de onda), [AUDIT_TIME.md](./AUDIT_TIME.md), [AUDIT_HMI.md](./AUDIT_HMI.md) |
| **Veredicto vigente** | Layout **B+ (en implementación, código)** — módulos A–E de la spec UI/UX cerrados en esta entrega. Datos RT **A−** (vía AUDIT_HMI). Fuera de alcance: RT-LAY-02 (Ctrl+drag libre) y RT-EDIT-03 (guías). Verificación planta CA-RT-01…08 pendiente de corrida en HMI vivo |
| **Clasificación** | Auditoría de frontend · UI/UX · layout · Confidencialidad interna |
| **Estado** | **En implementación** — schema v3 + canvas 48×10 + Plotly desacoplado + MultiSelectSearch + persistencia con circuit breaker |

---

### 0. Respuesta directa

| Pregunta | Respuesta (código 2026-09-09) |
|---|---|
| ¿Qué es la pantalla? | Un canvas de **strip charts Plotly** sobre `react-grid-layout`, con workspace por estación (local + servidor) |
| ¿Cómo se edita? | **Doble clic** en la página → modo edición. Toolbar (Agregar Gráfico, umbrales) **solo** aparece ahí |
| ¿El card nuevo “latea” (crece/decrece) hasta hacer click? | **Sí, reproducible en código.** Cadena Plotly `useResizeHandler` + `autosize` + transición CSS 200 ms del grid item + leyenda externa. Hallazgo **UX-RT-1** (crítico) |
| ¿El botón Tags muestra mal la lista? | **Sí.** Dropdown absoluto dentro de un panel con `overflow-y: auto` → la lista de ~280 px se **recorte** y a menudo se ve ~1 fila. Hallazgo **UX-RT-2** (alto) |
| ¿Se puede mover un card píxel a píxel? | **No.** Snap a celda: 12 columnas × `rowHeight=40` px + margen 10. Paso mínimo ≈ **~1/12 del ancho** y **50 px** en vertical (40+10). Hallazgo **UX-RT-3** (medio–alto, requisito de producto) |
| ¿Es estética “industrial / sala de control”? | Parcial. Chrome Bootstrap genérico, mode bar Plotly siempre visible, densidad no alineada con Trends históricos. Funcional en planta; no es una composición de diseño deliberada |

---

### 1. Mapa del código (evidencia)

| Pieza | Ruta |
|---|---|
| Página / canvas | `hmi/src/pages/RealTimeTrends.tsx` |
| Card + Plotly + picker Tags | `hmi/src/components/StripChart.tsx` |
| Chrome Bootstrap del card | `hmi/src/components/Card.tsx` |
| Persistencia workspace | `hmi/src/services/workspaceStore.ts` |
| Estilos grid + picker | `hmi/src/styles/global.css` (`.react-grid-item`, `.stripchart-tag-config`) |
| Backend workspace estación | API `/settings/workspace/realtime-trends` → `./db/hmi_workspace_realtime_trends.json` |
| Tests de contrato workspace | `automation/tests/test_realtime_trends_workspace.py` |
| Rendimiento / fidelidad RT (otro dominio) | [AUDIT_HMI.md](./AUDIT_HMI.md) |

**No participan en esta vista** (aunque el nombre sugiera lo contrario):

- `TrendChart.tsx` — SVG de `/performance`
- `MultiSelectSearch.tsx` — sí en Trends históricos / DataLogger; **aquí hay un picker ad-hoc**

---

### 2. Cómo funciona la vista (scope completo)

#### 2.1 Modelo mental

```
Página RealTimeTrends
  └─ ResponsiveGridLayout (react-grid-layout ^2)
       └─ item[i]  →  posición x,y,w,h en celdas
            └─ StripChart
                 ├─ Card header (título, ventana, Tags, borrar)  ← drag-handle
                 └─ cuerpo: empty | “sin datos” | <Plot/>
```

Un **card** = un `StripChartConfig` persistido:

| Campo | Rol |
|---|---|
| `id` | Clave del item RGL |
| `title` | Título editable (≤ 80 chars en sanitize) |
| `tagNames[]` | Hasta 16 tags; máx. 2 unidades de ingeniería |
| `timeSpanMinutes` | Ventana visible: 1 \| 2 \| 3 \| 5 |
| `x, y, w, h` | Layout en celdas del grid |

Límites de estación: **24** charts máximo (`MAX_STATION_CHARTS`).

#### 2.2 Modos

| Aspecto | Visualización | Edición |
|---|---|---|
| Entrada | Doble clic en el `row` de la página | Mismo toggle |
| Toolbar | Ausente | Título, switch umbrales, badge “Modo Edición”, “Agregar Gráfico” |
| Drag / resize | `static`, deshabilitados | Activos; handle `.drag-handle` = **todo el header** |
| Título | Texto + `QualityBadge` por tag | `<input>` |
| Tags / ventana / borrar | Ocultos | Visibles |
| Umbrales Plotly | **Nunca** (`showThresholds={isEditMode && showThresholds}`) | Solo si el switch está ON |

Implicación UX: en **producción** el operador no ve umbrales aunque los haya configurado, y no hay affordance visible de “puedo editar” salvo el empty state o conocimiento tribal del doble clic.

#### 2.3 Grid / canvas — números

| Parámetro | Valor | Efecto |
|---|---|---|
| Librería | `react-grid-layout` `ResponsiveGridLayout` | Posicionamiento absoluto + `transform` |
| `cols` | **12** (`lg`) | Ancho = N/12 del contenedor |
| `rowHeight` | **40** px | Alto base de una fila |
| `margin` | **[10, 10]** | Separación entre items |
| `containerPadding` | **[0, 0]** | |
| `minW` / `maxW` | **4 / 12** | Card no más estrecho que 1/3 |
| `minH` | **6** | Alto mínimo ≈ `40·6 + 10·5 = **290 px**` |
| Default nuevo | `w=6`, `h=6`, `y=maxY` | Mitad de ancho, apilado abajo |
| `compactType` | **`null`** | No reordena vecinos al soltar |
| `preventCollision` | **`false`** | **Permite solapes** |
| `resizeHandles` | `e`, `s`, `se`, `sw` | Sin norte |
| Ancho contenedor | `offsetWidth` + `window.resize` | Sin `ResizeObserver` (sidebar puede desincronizar) |
| Persistencia | Debounce **300 ms**; flush `beforeunload` | localStorage + PUT remoto |

#### 2.4 Flujo “Agregar Gráfico”

1. Modo edición → botón success “Agregar Gráfico”.
2. Se inserta un card **vacío** (`tagNames: []`) con empty state (“configura tags…”).
3. El operador abre **Tags (0)** en el header del card.
4. Panel flotante + búsqueda → al elegir el **primer tag**, se monta `<Plot/>`.
5. Ahí es donde aparece el lateo de tamaño (**UX-RT-1**).

#### 2.5 Flujo “Tags” (botón `bi-tags`)

No es `MultiSelectSearch`. Es un panel propio:

1. Toggle abre `.stripchart-tag-config` (absoluto, `z-index: 10000`).
2. Si ya hay tags, la lista de búsqueda arranca **cerrada** (chips primero).
3. Focus / tipeo en el input abre `.stripchart-tag-search-list` con `VirtualList` (`height={280}`, `itemHeight={52}` → ~5 filas teóricas).
4. Escape / click fuera cierra lista o panel.
5. Límite de 2 unidades → toast; `loadingTags` se setea pero **nunca se pinta** en UI.

#### 2.6 Persistencia

- Cache: `localStorage` `pyautomation.workspace.realtime-trends.v1` (+ migración legacy).
- Fuente de verdad de estación: `GET/PUT /settings/workspace/realtime-trends`.
- Hidratación: remoto con charts gana; si vacío, migra local.
- Sanitize: clamps de `w/h`, tope 24 charts, títulos y tags.

---

### 3. Hallazgos del operador (prioridad)

#### UX-RT-1 — Card de plot nuevo latea de tamaño hasta el click (crítico)

**Síntoma (planta):** en modo edición, al crear un gráfico nuevo y poblarlo, el card **aumenta y disminuye de tamaño de forma constante**. Solo se estabiliza al hacer click dentro. Fallo garrafal de UI/UX: impide diseñar el layout y transmite inestabilidad del producto.

**Cadena causal en código (sin bug report interno previo; evidencia estructural):**

1. Card vacío → empty state sin Plot → geometría estable.
2. Primer tag → monta `<Plot useResizeHandler={true} responsive style 100%×100% />` con `layout.autosize: true`.
3. Leyenda Plotly en `x: 1.02` (fuera del área de plot) + mode bar cambian el tamaño medido del contenedor.
4. CSS global:

```css
.react-grid-item {
  transition: all 200ms ease;
  transition-property: left, top, width, height;
}
```

5. Plotly relayout ↔ transición CSS del item ↔ nuevo tamaño medido → **bucle cresce/decrece**.
6. Un click / interacción fuerza reflow y corta el ciclo percibido.

**Agravantes:**

- Throttle de datos ~200 ms re-renderiza Plot mientras latea.
- `overflow: visible` en grid item y card (necesario para handles/picker) no aísla el layout.
- StripChart **no** tiene el patrón de debounce `relayoutTimeoutRef` que sí tiene Trends históricos (HMI-M5 en AUDIT_HMI).

**Severidad:** crítica para el flujo de configuración. Un card que “respira” solo no es un detalle cosmético: rompe la confianza en el canvas.

**Dirección de remediación (scope, no implementación):** desacoplar resize de Plotly del tamaño del grid item (fijar altura del plot al contenedor sin feedback loop); desactivar transición CSS en items de esta vista al montar/relayout; o `useResizeHandler={false}` + resize explícito al terminar el drag/resize de RGL; leyenda interna o margen derecho reservado estable.

---

#### UX-RT-2 — Lista de tags casi ilegible al pulsar Tags (alto)

**Síntoma (planta):** al abrir Tags → buscar, aparece un “card interno” con la lista. El contenedor externo **no tiene altura útil**; a menudo se ve **casi un solo tag**.

**Evidencia:**

```css
.stripchart-tag-config {
  max-height: min(70vh, 32rem);
  overflow-y: auto;          /* ← recorta hijos absolute */
}
.stripchart-tag-search-list {
  /* position-absolute (clase + markup) */
  max-height: 18rem;
  overflow-y: auto;
}
```

`VirtualList` pide `height={280}` (~5.4 filas de 52 px). Pero el dropdown es **`position: absolute`** dentro del panel con **`overflow-y: auto`**. Un hijo absolute **no expande** el scrollHeight del padre: el panel se dimensiona por el contenido en flujo (input + chips) y **recorta** la lista. Resultado visual: viewport diminuto sobre una lista de 280 px → sensación de “solo 1 tag”.

**Agravantes:**

- Panel anclado al header de un card de ~290 px de alto mínimo; en cards bajos cerca del borde inferior del viewport, el espacio percibido empeora.
- Picker inconsistente con `MultiSelectSearch` (portal, teclado, select-all) usado en Trends/DataLogger.
- `loadingTags` no tiene feedback visual → lista vacía momentánea se confunde con “no hay tags”.

**Severidad:** alta. Configurar tendencias es el trabajo principal de la pantalla en edición; si la lista no se puede explorar, el resto del canvas sobra.

**Dirección de remediación (scope):** portal/popover fuera del overflow del panel (como MultiSelectSearch); o lista en flujo (no absolute) con altura mínima garantizada (p. ej. 12–16 filas); unificar con el patrón de selección del resto del HMI.

---

#### UX-RT-3 — Movimiento de cards solo por celdas, no px a px (medio–alto)

**Síntoma / requisito (planta):** al desplazar un card completo sobre el canvas, se desea movimiento **lo más granular posible (px a px)** para componer layouts diversos con flexibilidad.

**Comportamiento actual:** `react-grid-layout` **siempre hace snap a la grilla**. Con `cols=12`, `rowHeight=40`, `margin=[10,10]`:

| Eje | Paso efectivo aproximado |
|---|---|
| Horizontal | `containerWidth / 12` (p. ej. ~100 px a 1200 px de ancho) |
| Vertical | `rowHeight + marginY` = **50 px** entre orígenes de fila |

No existe API de “free drag en píxeles” en esta configuración. `compactType={null}` y `preventCollision={false}` dan libertad de **solape**, no de granularidad.

**Severidad:** medio–alto como requisito de producto. Hoy el canvas es un **dashboard de celdas**, no un lienzo de diseño fino. Eso choca con la expectativa de “diseñar diversos layouts”.

**Dirección de remediación (scope) — trade-offs a decidir:**

| Opción | Pros | Contras |
|---|---|---|
| A. Subir resolución (`cols=48…96`, `rowHeight=5…10`) | Sigue siendo RGL; persistencia compatible con escala | Más “temblor” al alinear; minW/minH hay que reescalar |
| B. Modo “fine” temporal (más cols / menor rowHeight solo en edición) | Operación gruesa vs fina | Complejidad de UX y de migrate |
| C. Posicionamiento libre (left/top px) fuera de RGL | Verdadero px a px | Reescribir canvas; colisiones/snap opcionales a mano |
| D. Snap magnético a 1–2 px con guía | Sensación de precisión sin abandonar grid | Sigue sin ser continuo puro |

Cualquier camino exige **decisión de producto**: ¿dashboard alineado o lienzo libre?

---

### 4. Pros (lo que está bien)

| # | Fortaleza | Evidencia |
|---|---|---|
| P1 | Workspace de estación dual (local + servidor) con sanitize fuerte | `workspaceStore.ts`, endpoint settings, tests |
| P2 | Memo + selector Redux estrecho + freeze con pestaña oculta | `StripChart` / [AUDIT_HMI.md](./AUDIT_HMI.md) — buen cuidado del hot path de datos |
| P3 | Empty states claros (página vacía, card sin tags, sin puntos en ventana) | `RealTimeTrends.tsx`, `StripChart.tsx` |
| P4 | Ventana temporal explícita (1–5 min) y tope de 2 unidades | Controles en header + toast |
| P5 | Límite 24 charts / 16 tags evita explosión de layout | `MAX_STATION_CHARTS`, sanitize |
| P6 | Dark/light en Plotly coherente con tema | `paper_bgcolor` / `plot_bgcolor` según `mode` |
| P7 | Placeholder de drag visible (azul dashed) | `global.css` `.react-grid-placeholder` |
| P8 | QualityBadge en modo planta | Feedback de calidad OPC en header (solo fuera de edición) |

---

### 5. Contras estéticos y de UX (además de UX-RT-1…3)

| ID | Contras | Impacto |
|---|---|---|
| **UX-RT-4** | Edición solo por **doble clic**; toolbar invisible en planta | Affordances opacas; descubribilidad baja |
| **UX-RT-5** | Umbrales **apagados en producción** aunque el switch exista en edición | El operador de sala no ve la referencia que el ingeniero configuró |
| **UX-RT-6** | `preventCollision={false}` + `compactType={null}` | Layouts “sucios”: cards apilados/solapados sin ayuda |
| **UX-RT-7** | Header entero = `drag-handle` (incluye input, Tags, trash, select) | Arrastres accidentales al editar título o abrir Tags |
| **UX-RT-8** | Mode bar Plotly siempre visible | Ruido visual en modo planta; zoom/pan compiten con la lectura |
| **UX-RT-9** | Sin `trends-fit-viewport` (sí en Trends históricos) | Scroll largo con muchos charts; densidad inconsistente |
| **UX-RT-10** | Ancho del grid solo por `window.resize`, no `ResizeObserver` | Al colapsar sidebar el layout puede quedar desfasado |
| **UX-RT-11** | API RGL estilo v1 en paquete v2; Performance/LDS ya usan `dragConfig`/`resizeConfig` | Inconsistencia interna del HMI |
| **UX-RT-12** | Picker Tags ≠ `MultiSelectSearch` | Dos metáforas de selección de tags en el mismo producto |
| **UX-RT-13** | Borrar chart **sin confirmación** | Error irreversible con un click en el trash |
| **UX-RT-14** | Cada `StripChart` hace `getTagsList()` al montar | N requests con N cards; lentitud percibida al entrar en edición |
| **UX-RT-15** | QualityBadge desaparece en edición | Se pierde estado de calidad justo cuando se configura |
| **UX-RT-16** | Tipografía / chrome Bootstrap genérico; sin jerarquía visual de “lienzo de operación” | Aspecto de formulario admin más que de sala de control |
| **UX-RT-17** | Un solo breakpoint (`lg: 0`); touch targets no dedicados | Móvil/tablet poco usable para editar layout |
| **UX-RT-18** | `aria-label="Remove"` en inglés; doble clic no anunciado | Accesibilidad parcial |

---

### 6. Estética — lectura de diseño

#### 6.1 Primera impresión (modo planta)

- Sin toolbar: el canvas es solo cards + empty state.
- Cards Bootstrap `shadow-sm`, header compacto, Plotly con mode bar.
- No hay hero ni branding de la vista; depende del layout global (sidebar + MainLayout).
- Sensación: **tablero técnico funcional**, no composición deliberada.

#### 6.2 Primera impresión (modo edición)

- Aparece toolbar con badge warning “Modo Edición” — buena señal de estado.
- Handles de resize y grip vertical ayudan, pero el lateo del plot (**UX-RT-1**) domina la percepción de calidad.
- El picker Tags (**UX-RT-2**) rompe el flujo en el momento más crítico (añadir señal).

#### 6.3 Comparación con hermanas del HMI

| Vista | Layout | Selección tags | Densidad |
|---|---|---|---|
| Real-time trends | RGL celdas 12×40 | Panel ad-hoc | Sin fit viewport |
| Trends históricos | Charts fijos / fit | `MultiSelectSearch` | `trends-fit-viewport` |
| Performance | RGL (API v2) | N/A (métricas fijas) | Tiles densos |
| LDS dashboard | RGL + tabs | N/A | Paneles densos |

La vista RT es la que **más necesita** un canvas de diseño y, a la vez, la que tiene la **metáfora de edición menos madura**.

---

### 7. Matriz de severidad y criterios de aceptación (futuros)

| ID | Severidad | Criterio de aceptación sugerido |
|---|---|---|
| **CA-UX-RT-1** | Crítica | Tras añadir el 1.er tag a un card nuevo, el tamaño del item RGL **no oscila** más de ±1 px durante 3 s sin interacción |
| **CA-UX-RT-2** | Alta | Con el panel Tags abierto y búsqueda activa, ≥ **8 tags** visibles sin scroll del card padre; lista no recortada por overflow del panel |
| **CA-UX-RT-3** | Media–alta (producto) | Decisión documentada: o bien paso de grid ≤ **5–10 px** efectivos en edición, o bien modo libre px a px; operador puede alinear dos cards con error visual ≤ 2 px |
| **CA-UX-RT-4** | Media | Entrada a edición descubrible (botón/icono persistente o hint), no solo doble clic |
| **CA-UX-RT-5** | Media | Umbrales visibles en modo planta si el ingeniero los activó (o política explícita “umbrales solo en edición”) |
| **CA-UX-RT-6** | Media | Drag handle acotado al grip; controles del header no inician drag |
| **CA-UX-RT-7** | Baja–media | Confirmación al borrar card; loading state en catálogo de tags |

---

### 8. Runbook de verificación manual (planta / lab)

1. Abrir `/real-time-trends` → doble clic → modo edición.
2. **Agregar Gráfico** → card vacío estable.
3. Tags → buscar → confirmar cuántas filas se ven sin scroll raro (**UX-RT-2**).
4. Añadir 1 tag → observar 3–5 s **sin click**: ¿latea el borde del card? (**UX-RT-1**).
5. Click dentro → ¿se detiene?
6. Arrastrar el card: medir el salto mínimo en px (DevTools / regla) (**UX-RT-3**).
7. Solapar dos cards a propósito: ¿se permite? (hoy sí).
8. Colapsar sidebar: ¿el ancho del grid se corrige sin resize de ventana? (**UX-RT-10**).
9. Salir de edición (doble clic) → umbrales: ¿siguen visibles? (**UX-RT-5**).
10. Recargar: ¿el layout persistió en la estación?

---

### 9. Residual / fuera de alcance de este documento

| ID | Nota |
|---|---|
| UX-R1 | Fidelidad 1 Hz / huecos de serie → [AUDIT_HMI.md](./AUDIT_HMI.md), no UI |
| UX-R2 | Coste de Plotly con muchos tags @ throttle 200 ms → performance, no estética |
| UX-R3 | i18n de strings de banner socket vs copy del picker → menor |
| UX-R4 | RT-LAY-02 (lienzo libre px) y RT-EDIT-03 (guías) quedan **fuera** de HMI 2.10; granularidad = grid 48×10 (§11) |

---

### 10. Cierre

La pantalla de tiempo real **cumple** como visor de series con workspace de estación durable y buen cuidado del canal de datos. Como **herramienta de diseño de layouts** —que es lo que el modo edición promete— hoy **no** está a nivel industrial:

1. El card nuevo que latea (**UX-RT-1**) rompe la sesión de edición.
2. El picker Tags ilegible (**UX-RT-2**) bloquea el flujo de añadir señales.
3. El snap grueso (**UX-RT-3**) impide la flexibilidad de composición que el operador pide.

Pros reales (workspace, empty states, límites, tema Plotly) no compensan esos tres puntos en la percepción del producto. El siguiente paso no es “pulir CSS”: es **cerrar el bucle de resize**, **sacar la lista de tags del overflow**, y **decidir el contrato de granularidad del canvas** antes de tocar código.

**Veredicto (auditoría original):** UI/UX de layout **C+ / B−**; datos RT y persistencia **A−** (vía AUDIT_HMI + workspace). Prioridad de remedio: UX-RT-1 → UX-RT-2 → decisión UX-RT-3 → affordances de edición (UX-RT-4/6/5).

La entrega posterior está en la **§11**.

---

### 11. Implementación 2026-09-09 — spec UI/UX HMI 2.10 (módulos A–E)

**Decisión de producto:** grid canónico **48 columnas / `rowHeight=10`** en edición y visualización. Migración **una vez** al hidratar (schema 2 → 3). **No** se incluye RT-LAY-02 (Ctrl+drag libre en px) ni RT-EDIT-03 (guías de alineación). Flag Vite `VITE_RT_TRENDS_LAYOUT_V3` (default `true`).

#### 11.1 Contrato schema v3

| Campo | Valor |
|---|---|
| `schemaVersion` | 3 |
| `grid` | `{ cols: 48, rowHeight: 10 }` |
| `panelTitle` | string opcional |
| por card `showThresholds` | boolean, default `true` |
| `minW` / `maxW` | 16 / 48 (1/3 visual del `minW=4` legado) |
| `minH` / default | 15 / `w=24, h=15` (equivalencia en px del `h=6` legado ≈ 290 px) |
| Migración | `x,w *= 4`; `y,h` por fórmula de píxeles (`rowHeight` 40→10, margin 10) |

Backend `sanitize_workspace` y HMI `workspaceStore` + `realtimeTrendsGrid.ts` espejo. `MAX_GRID_W=48` — un PUT v3 **ya no** se recorta a 12.

#### 11.2 Remediación vs hallazgos

| Hallazgo | Estado en código | Pieza |
|---|---|---|
| **UX-RT-1** lateo Plotly | Cerrado | `useResizeHandler={false}`, `autosize:false`, `usePlotlyResize` (ResizeObserver + debounce 200 ms, Δ>5 px, pausa en drag/resize), leyenda `orientation:'h'` `y:-0.18`, `transition: none` en `.rt-trends-layout--editing` |
| **UX-RT-2** picker recortado | Cerrado | `MultiSelectSearch` en portal; `PANEL_MAX_HEIGHT=580` / `60vh` (≥10 filas de 48 px a 1080p) |
| **UX-RT-3** snap grueso | Mitigado (opción A) | 48 cols ≈ **25 px** a 1200 px; vertical `rowHeight+margin=20` px. Libre px a px **fuera de alcance** |
| **UX-RT-4** doble clic | Cerrado | Botón permanente «Editar panel»; Escape sale y hace flush |
| **UX-RT-5** umbrales en planta | Cerrado | `showThresholds` persiste; toggle global escribe todos los cards; visibles fuera de edición |
| **UX-RT-6** solapes | Mitigado | `getCompactor(null, allowOverlap, preventCollision)`; sin Alt, `preventCollision`; Alt+drag permite solape |
| **UX-RT-7** header=drag | Cerrado | Franja `.rt-card-drag-handle` 20 px; input/Tags/trash con `stopPropagation` y `dragConfig.cancel` |
| **UX-RT-8** mode bar planta | Cerrado | `displayModeBar: isEditMode` |
| **UX-RT-10** sidebar | Cerrado | `ResizeObserver` en el canvas |
| **UX-RT-11** API RGL v1 | Cerrado | `dragConfig` / `resizeConfig` / `compactor` como Performance/LDS |
| **UX-RT-12** picker ad-hoc | Cerrado | `MultiSelectSearch` |
| **UX-RT-13** borrar sin confirm | Cerrado | `OpsConfirmModal` |
| **UX-RT-14** N× GET tags | Cerrado | `loadStationTagCatalog()` una vez al entrar en edición |
| **UX-RT-18** aria | Parcial | `aria-label` en Agregar gráfico y drag handle |

#### 11.3 Criterios CA-RT (spec)

| ID | Criterio | Código | Planta / lab |
|---|---|---|---|
| **CA-RT-01** | Tras el 1.er tag, el item RGL no oscila >1 px / 3 s | Implementado (desacople Plotly) | Lab Vite: card vacío estable (`h` px = 290). 1.er tag con serie viva pendiente de HMI con API |
| **CA-RT-02** | Picker ≥10 filas, portal, no recortado | Implementado (`PANEL_MAX_HEIGHT=580` / 60vh, portal) | Lab: listbox portal fuera del card; lista vacía sin catálogo. Filas ≥10 pendiente de planta |
| **CA-RT-03** | Paso ≤25 px a 1200 px de ancho | 48 cols | Lab: canvas ~630 px → paso ≈ 13 px; a 1200 px ≈ 25 px |
| **CA-RT-04** | Botón Editar permanente | Implementado | **PASS** lab («Editar panel» / «Edit panel») |
| **CA-RT-05** | Umbrales visibles en planta | Implementado (`showThresholds` persistido, switch global) | Toggle visible en edición; traza punteada pendiente de tags vivos |
| **CA-RT-06** | Modal al borrar | Implementado | **PASS** lab (`¿Eliminar el gráfico «Chart 1»?`) |
| **CA-RT-07** | Offline: localStorage + banner; 3 PUT fallidos → 5 min; timeout 10 s | Implementado | **PASS** lab (badge «Sin conexión al servidor» + banner local) |
| **CA-RT-08** | 1 GET `/tags/list` al editar | Implementado (`loadStationTagCatalog`) | Lab sin API: un intento de catálogo al entrar en edición (fallido, toast) |

#### 11.4 Persistencia

- Debounce 300 ms; localStorage primero; PUT con timeout 10 s.
- Circuit breaker: 3 fallos → `offline` 5 min; `setInterval` 60 s para reintentar; banner «Cambios guardados localmente».
- Export/import JSON v3 pasa por `sanitize` + `migrateLayout`.

#### 11.5 Fuera de esta entrega

Fuse.js, `@floating-ui`, DOMPurify, pixel-perfect libre, snap guides, cifrado de localStorage, CSP nonce nuevo, `REACT_APP_GRID_V2`.


## Parte C — Trazabilidad Socket HMI

> Fuente original: `AUDIT_HMI_SOCKET_TRACEABILITY.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) + HMI React (`hmi/src/`) + Gunicorn/gevent |
| **Alcance** | Ciclo de vida Socket.IO (connect / disconnect / reconnect); telemetría TLS; conteo multi-worker; **LED RT del header**; correlación freeze de tendencias vs estado de transporte |
| **Fecha** | 2026-08-24 (v2.3 — timeouts ≤45s + watchdog frescura) · v2.2 gap documentado · base v2.1 2026-08-19 |
| **Spec** | [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md) v2.1 + especificación timeouts/watchdog 2026-08-24 |
| **Runbook** | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |
| **Complementa** | [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) §2 Events, [AUDIT_HMI.md](./AUDIT_HMI.md) §2 socket/EventBus, [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_DB.md](./AUDIT_DB.md) |
| **Veredicto vigente** | **A** transporte (detección ≤45s) · **A−** plano de datos (watchdog `on.tag` 5 s → LED amarillo) — soak planta pendiente |
| **Clasificación** | Auditoría operativa · conectividad HMI · trazabilidad multi-equipo · UX indicadores |

---

### 0. Respuesta directa (actualizada 2026-08-24)

| Pregunta | Respuesta |
|---|---|
| ¿Connect/disconnect Socket se registran en **Events**? | **Sí** — `HMI client connected` / `disconnected` / `reconnected` / `connection rejected` |
| ¿Se identifica el cliente? | **Sí** — `username=`, `origin=`, `sid=`, `edge=` |
| ¿El LED **RT** del header refleja desconexión Socket.IO? | **Sí (transporte)** + **watchdog de frescura**: sin `on.tag` ≥5 s con socket up → LED amarillo (`data-stale`). |
| ¿Por qué la tendencia RT puede congelarse con LED RT verde? | Mitigado por **SKT-H7 cerrado (código)**: watchdog `useDataFreshness`. Validar en planta (tags lentos pueden generar warn legítimo). |
| ¿Hay watchdog de “último `on.tag`”? | **Sí** — `socketService.onTagActivity` + `useDataFreshness` (umbral 5 s). |
| ¿Toasts de pérdida/recuperación? | **Sí**, con debounce **2 s** (`useSocketConnectionNotifications`). |
| ¿Token inválido? | Fail-closed + evento `connection rejected` + logout HMI. |

#### 0.1 Tres capas de conectividad HMI

| Capa | Qué ocurre | Trazabilidad L3 Events | Indicador HMI |
|---|---|---|---|
| **A — TLS / WSGI** | Cert, HTTP vs TLS, EOF | `"HMI TLS handshake failure"` — 1/IP/5 min | Ninguno dedicado |
| **B — Transporte Socket.IO** | connect / disconnect / reconnect / reject | 1 evento por sesión (`HMI`) | LED **RT** (header) |
| **C — Plano de datos RT** | Emisión `on.tag` / `on.alarm` / CVT | Sin evento L3 de stall (aún) | LED **RT** amarillo si silence ≥5 s; banner tendencias |
| **D — HTTP sesión / BD** | login, health probe | `User logged in\|out`; health HTTP | LED **BD** (independiente) |

#### 0.2 Flujo operativo (transporte)

```
Login HTTP     → Event: User logged in
Connect socket → UPSERT hmi_sessions + Event: connected + LED RT verde
Heartbeat 30s  → HMI emit "ping" → UPDATE last_heartbeat (sin evento, sin LED)
Disconnect     → DELETE hmi_sessions + Event: disconnected
                 → LED RT amarillo (reconnecting) hasta 30 s
                 → LED RT rojo (disconnected) si outage ≥ 30 s
Reconnect      → Event: reconnected + GET /history/backfill (ventana 2–5 min, ISO UTC) + LED verde
Token inválido → Event: rejected + logout HMI
```

#### 0.3 Flujo de datos RT (independiente del LED)

```
Adquisición / OPC / workers → CVT.set_value → sio.emit("on.tag")
  → HMI socketService.onTagUpdate → buffer 250 ms → Redux tagHistory
  → StripChart lee tagHistory

Si este pipeline se detiene y Engine.IO sigue vivo → curva plana + LED RT verde.
```

---

### 1. Por qué importa el síntoma «curva congelada / LED verde»

| Riesgo | Con solo v2.1 (transporte) | Con gap SKT-H7 |
|---|---|---|
| Operador asume “RT OK” porque LED verde | Correcto solo si el socket está up | **Falso positivo** si CVT/OPC/fanout fallan |
| Correlacionar freeze con Events | Busca `disconnected` | Puede **no** haber disconnect |
| Distinguir BD down vs socket down | LED BD vs LED RT separados | Correcto para capas B/D; **no** cubre capa C |
| Diagnóstico en planta | “¿Se cayó el socket?” | Preguntar también: ¿siguen llegando `on.tag`? ¿OPC/adquisición? |

---

### 2. Inventario de código (evidencia 2026-08-24)

#### 2.1 Backend — sesiones + auditoría + fanout

| Artefacto | Rol | Estado |
|---|---|---|
| `automation/dbmodels/hmi_sessions.py` | Tabla sesiones HMI | ✅ |
| `automation/utils/hmi_session_store.py` | upsert / remove / count / heartbeat / cleanup | ✅ |
| `automation/utils/hmi_socket_audit.py` | Events + connect fail-closed | ✅ |
| `automation/workers/hmi_session_cleanup.py` | Huérfanas > 2 min sin heartbeat | ✅ |
| `automation/core.py` `define_socketio` | `ping_interval=15`, `ping_timeout=30` (s) → detección ≤45 s; handlers connect/disconnect/ping | ✅ v2.3 |
| `automation/tags/cvt.py` | `sio.emit("on.tag", …)` en hot path de valor | ✅ (capa C) |
| `automation/utils/hmi_tls_telemetry.py` | TLS por IP | ✅ |

#### 2.2 HMI — LED RT y fases

| Artefacto | Rol | Estado |
|---|---|---|
| `hmi/src/services/socket.ts` | Fases transporte; `DISCONNECTED_PHASE_MS=15_000`; reconnect 500–5000 ms; `timeout=15_000`; `onTagActivity` / `DATA_STALE_MS=5_000`; heartbeat app 15 s | ✅ v2.3 |
| `hmi/src/hooks/useSocketConnection.ts` | Suscribe `onConnectionChange` → fase | ✅ |
| `hmi/src/hooks/useDataFreshness.ts` | Watchdog: sin `on.tag` ≥5 s → `dataStale` | ✅ v2.3 |
| `hmi/src/hooks/useSystemHealth.ts` | `socketHealth` = transporte ∪ frescura; `transportHealth` separado; `rtReason` | ✅ v2.3 |
| `hmi/src/components/SocketBadge.tsx` | LED header **RT** (ok/warn/alarm) + tooltip data-stale | ✅ v2.3 |
| `hmi/src/hooks/useSocketConnectionNotifications.ts` | Toasts pérdida/recuperación, debounce **2 s** | ✅ |
| `hmi/src/hooks/useSocket.ts` | Suscribe `on.tag` → Redux; backfill al reconnect vía `/history/backfill` | ✅ v2.4 |
| `hmi/src/utils/tagHistoryBackfill.ts` | `from=max(último punto, now−ventana)`; ventana = time span charts | ✅ v2.4 |
| `hmi/src/services/history.ts` | Cliente `GET /history/backfill` | ✅ v2.4 |
| `automation/modules/history/` | Endpoint backfill TagValue → ISO UTC | ✅ v2.4 |
| `hmi/src/pages/RealTimeTrends.tsx` | Banner transporte + banner `dataStalled` | ✅ v2.3 |
| `hmi/src/components/StripChart.tsx` | Serie desde `tagHistory` Redux | ✅ sin watchdog propio |
| Locales `socket.*` | Tooltips LED / toasts | ✅ |
| CSS `.socket-badge--ok\|warn\|alarm` | Verde / amarillo / rojo | ✅ |

#### 2.3 Evolución

| Capacidad | v2.1 | v2.2 (esta auditoría) |
|---|---|---|
| Events connect/disconnect | ✅ | Sin cambio |
| LED RT por fase de transporte | ✅ | **Documentado** mapeo + umbrales |
| Separación LED RT vs LED BD | ✅ | Confirmado |
| Watchdog frescura `on.tag` → LED | ❌ | **✅ v2.3** (`useDataFreshness`, umbral 5 s) |
| Evento L3 “RT data stalled” | ❌ | **Gap abierto** (solo UX LED/banner) |

---

### 3. Configuración del LED RT (header)

#### 3.1 Cadena de estado

```
Engine.IO events (connect / disconnect / connect_error / reconnect_attempt)
  → SocketService.computePhase()
  → emitConnection → useSocketConnection()
  → useSystemHealth().socketStatus / socketHealth
  → SocketBadge (clase CSS + tooltip i18n)
```

`HeaderClock` monta `SocketBadge` junto al LED BD (`DatabaseStatus`). Son **independientes**.

#### 3.2 Mapa fase → LED

| `SocketConnectionPhase` | `socketHealth` | CSS | Color | Tooltip (ES) |
|---|---|---|---|---|
| `connected` | `connected` | `socket-badge--ok` | Verde | «Socket HMI conectado — datos en tiempo real activos» |
| `connecting` | `reconnecting` | `socket-badge--warn` | Amarillo | «Socket HMI conectando…» |
| `reconnecting` | `reconnecting` | `socket-badge--warn` | Amarillo | «Socket HMI reconectando…» |
| `disconnected` | `disconnected` | `socket-badge--alarm` | Rojo | «Socket HMI desconectado — reintentando…» |

**Nota UX:** el tooltip de “datos en tiempo real activos” es **aspiracional**: el código solo garantiza socket transport connected, no llegada de muestras.

#### 3.3 Umbrales y temporizadores (código actual)

| Constante / config | Valor | Efecto en LED / UX |
|---|---|---|
| `SocketService.DISCONNECTED_PHASE_MS` | **15 000 ms** | Tras `disconnect`, amarillo hasta 15 s; luego rojo |
| Toast debounce | **2 000 ms** | Blips < 2 s no muestran toast de pérdida |
| Heartbeat HMI → backend `ping` | **15 s** | Actualiza `hmi_sessions.last_heartbeat`; no cambia el LED |
| Backend `ping_interval` | **15 s** | Engine.IO ping servidor→cliente |
| Backend `ping_timeout` | **30 s** | Detección peer muerto ≤ **45 s** (15+30) |
| Cliente `timeout` | **15 000 ms** | Timeout de conexión inicial |
| Reconnect delay | **500–5000 ms** + jitter | Reintentos más agresivos (≤2 s típico) |
| `DATA_STALE_MS` / watchdog | **5 000 ms** | Socket up + silencio `on.tag` → LED amarillo + banner |
| Buffer Redux tags | **250 ms** | Agrupa `on.tag` |

#### 3.4 Banner en RealTimeTrends

Solo se muestra si `socketStatus !== "connected"`:

- `disconnected` → alerta danger (`realTimeTrends.waitingSocket`)
- `reconnecting` / `connecting` → alerta warning

Si el socket sigue `connected` y no hay `on.tag`, **no hay banner** y la curva se queda en el último valor histórico.

---

### 4. Tabla `hmi_sessions` (estado global sin Redis)

Sin cambios respecto a v2.1. Ver §3 del audit histórico: connect requiere PG; heartbeat 30 s; cleanup 60 s / stale 2 min.

```sql
SELECT sid, username, origin, connected_at, last_heartbeat
FROM hmi_sessions WHERE node_id = '<AUTOMATION_NODE_ID>'
ORDER BY last_heartbeat DESC;
```

---

### 5. Modelo de eventos L3 (transporte)

Clasificación: **`HMI`**.

| `message` | Cuándo | priority | criticity |
|---|---|---|---|
| `HMI client connected` | Primera conexión válida | 2 | 2 |
| `HMI client disconnected` | disconnect limpio | 3 | 3 |
| `HMI client reconnected` | `auth.reconnect=true` | 2 | 2 |
| `HMI client connection rejected` | Token inválido / store no disponible | 3 | 4 |
| `HMI TLS handshake failure` | Fallo TLS por IP (rate 5 min) | 2 | 2 |

**No existen** mensajes L3 del tipo:

- `HMI RT data stalled`
- `HMI on.tag silence`
- `HMI CVT fanout stopped`

---

### 6. Diagnóstico: tendencia congelada vs LED RT

#### 6.1 Matriz de síntomas

| Síntoma HMI | LED RT | Events esperados | Causa más probable |
|---|---|---|---|
| Curva plana, LED **verde** | `connected` | Ningún `disconnected` reciente | **SKT-H7** — capa C: OPC/adquisición/CVT sin emitir; o half-open aún no detectado por Engine.IO |
| Curva plana, LED **amarillo** ≤30 s | `reconnecting` | Posible `disconnected` | Outage corto o en curso; operador puede no notar “alarma” |
| Curva plana, LED **rojo** ≥30 s | `disconnected` | `HMI client disconnected` | Transporte caído — esperado |
| Hueco + reanudación, LED verde de nuevo | connected tras reconnect | `reconnected` | Normal; `GET /history/backfill` si PG up |
| Logout inesperado | — | `connection rejected` | Token / sesión |

#### 6.2 Cómo validar en planta (checklist)

1. **DevTools → Network → WS**: ¿el frame Socket.IO sigue abierto? ¿llegan paquetes `2`/`3` (ping/pong Engine.IO)?
2. **Consola / Redux**: ¿entran payloads `on.tag` mientras la curva está plana?
3. **Events** (mismo edge, ventana del freeze): ¿hay `HMI client disconnected`?
4. **`hmi_sessions`**: ¿`last_heartbeat` se actualiza cada ~30 s?
5. **Adquisición / OPC**: ¿el tag cambia en CVT/backend aunque la HMI no pinte?
6. **LED BD**: independiente; puede estar rojo (BD down) con LED RT verde y curvas vivas (valores desde memoria CVT).

#### 6.3 Por qué el LED “no se activa” en el caso reportado

Hallazgo operativo confirmado por código:

1. El LED **solo** escucha fase de transporte (`socket.ts` → `useSystemHealth` → `SocketBadge`).
2. Las tendencias leen **historial Redux** alimentado por `on.tag`, no por el LED.
3. Si Engine.IO no dispara `disconnect` (conexión half-open, servidor aún hace ping, proceso gevent vivo pero sin emitir tags), la fase permanece `connected` → LED verde.
4. Incluso con `disconnect` real, los primeros **30 s** el LED es **amarillo** (`reconnecting`), no rojo; toasts solo tras **2 s**.
5. El copy del tooltip («datos en tiempo real activos») **sobrepromete** respecto a lo instrumentado.

---

### 7. Hallazgos y residuales

| ID | Hallazgo | Estado |
|---|---|---|
| **SKT-H1…H6** | Disconnect, Events, TLS, conteo, fail-closed, TLS/IP | ✅ Cerrados (v2.1) |
| **SKT-H7** | LED RT no reflejaba silencio de `on.tag` | **✅ Cerrado (código v2.3)** — watchdog 5 s; soak tags lentos pendiente |
| **SKT-H8** | Tooltip i18n “datos RT activos” engañoso | **Mitigado** — `badgeDataStale` cuando aplica; copy connected sigue siendo aspiracional si tags fluyen |
| **SKT-R1** | Connect requiere PG para sesión | Aceptado |
| **SKT-R2** | Cierre pestaña sin HTTP logout | Por diseño |
| **SKT-R3** | Soak multi-worker 2-edge | Pendiente planta |
| **SKT-R4** | Detección Engine.IO peer muerto | **Mejorado** — ≤45 s (antes ~85 s) |

#### 7.1 Criterios de aceptación (transporte — sin cambio)

| ID | Criterio | Evidencia |
|---|---|---|
| CA-SKT-11…17 | Reject, PG, heartbeat, TLS, logout, runbook | Ver v2.1 |
| CA-SKT-01…10 | Soak operativo | Pendiente planta |

#### 7.2 Criterios propuestos (plano de datos — pendientes de implementación)

| ID | Criterio | Estado |
|---|---|---|
| **CA-SKT-18** | Sin `on.tag` ≥5 s con socket connected → LED warn + banner | ✅ código `useDataFreshness` / RealTimeTrends |
| **CA-SKT-19** | Evento L3 / métrica `last_on_tag_age_ms` | **Pendiente** |
| **CA-SKT-20** | Tooltip distingue socket up vs datos fluyendo | ✅ `badgeDataStale` |
| **CA-SKT-21** | Detección transporte ≤45 s (`ping_interval=15` + `ping_timeout=30`) | ✅ `core.py` |
| **CA-SKT-22** | Reconnect delay 500–5000 ms | ✅ `socket.ts` |

Tests actuales (transporte):

```bash
./venv/bin/python3 -m unittest automation.tests.test_hmi_session_store automation.tests.test_hmi_tls_telemetry -v
```

No hay tests HMI automatizados que fallen si `on.tag` deja de llegar con fase `connected`.

---

### 8. Veredicto

| Dimensión | Nota | Comentario |
|---|---|---|
| Trazabilidad L3 Socket.IO (transporte) | **A+** | connect/disconnect/reconnect/reject + IP/usuario/sid |
| Conteo global multi-worker | **A+** | `hmi_sessions` |
| LED RT vs LED BD | **A** | Separados correctamente |
| Fidelidad LED RT ↔ “hay datos RT” | **A−** | Watchdog 5 s (SKT-H7); tags muy lentos pueden warn |
| Resiliencia UX (fases 15 s, toasts 2 s, detect ≤45 s) | **A** | Timeouts v2.3 |
| Cobertura tests plano datos | **C** | Sin e2e stall automatizado |

**Veredicto global v2.3: A (transporte) / A− (RT completo en código)** — Timeouts Engine.IO 15/30 s y watchdog de frescura implementados. Cierre formal tras soak planta (falsos positivos por tags lentos + CA-SKT-10/13).

---

### 9. Referencias

| Tema | Ruta |
|---|---|
| Spec v2.1 | [specs/04-HMI-SOCKET-TRACEABILITY.md](../specs/04-HMI-SOCKET-TRACEABILITY.md) |
| Runbook | [docs/hmi-connectivity-runbook.md](../docs/hmi-connectivity-runbook.md) |
| Handlers Socket.IO | `automation/core.py` — `define_socketio` |
| Fanout tags | `automation/tags/cvt.py` — `emit("on.tag")` |
| Fases + umbrales | `hmi/src/services/socket.ts` |
| Watchdog frescura | `hmi/src/hooks/useDataFreshness.ts` |
| LED header | `hmi/src/components/SocketBadge.tsx` |
| Salud agregada | `hmi/src/hooks/useSystemHealth.ts` |
| Pipeline RT → Redux | `hmi/src/hooks/useSocket.ts` |
| Tendencias | `hmi/src/pages/RealTimeTrends.tsx`, `StripChart.tsx` |
| Sesiones / Events | `hmi_session_store.py`, `hmi_socket_audit.py` |

---

### 10. Changelog

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-08-19 AM | v1 | Badge, backfill RT, Events connect/disconnect in-memory, TLS agregado |
| 2026-08-19 PM | v2.1 | PG `hmi_sessions`, fail-closed, heartbeat/cleanup, TLS/IP; veredicto A+ código transporte |
| 2026-08-24 | v2.2 | Documenta gap LED vs frescura (SKT-H7); umbrales legacy 25/60 ≈85 s |
| 2026-08-24 | **v2.3** | `ping_interval=15`/`ping_timeout=30`; reconnect 500–5s; `DISCONNECTED_PHASE_MS=15s`; watchdog `useDataFreshness` 5 s; cierra SKT-H7 en código |
| 2026-08-24 | **v2.4** | `GET /api/history/backfill` (ISO UTC); ventana = time span tendencia (2–5 min); merge dedupe por epoch ms; corrige huecos por formato MM/DD vs ISO |

---

### 11. Notas operativas

- **python-socketio** usa `ping_interval` / `ping_timeout` en **segundos** (15 y 30), no milisegundos.
- El cliente mantiene `autoConnect: false` (token antes de conectar); no se adoptó `autoConnect: true` de la spec de ejemplo.
- Tags con periodo de actualización >5 s dispararán LED amarillo de forma esperada; si molesta en planta, subir `DATA_STALE_MS` o armar el watchdog solo para tags suscritos a stripcharts.


## Parte D — Extensión HMI machines/domain

> Fuente original: `AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`github/PyAutomation`, paquete `automation` + HMI `hmi/src/`) |
| **Versión auditada** | 2.8.1 → contrato DomainConfigurable implementado en árbol 2026-08-26 |
| **Pregunta fundamental** | ¿Puede un proyecto externo (p. ej. iDetectFugas) añadir formularios de configuración complejos a `/hmi/machines/detailed` **sin modificar una sola línea** de PyAutomationIO? |
| **Respuesta (pre Fase A)** | **NO** (inventario §3) |
| **Respuesta (post Fase A)** | **SÍ** — Schema-Driven UI + duck-typing; ver [§13 evidencia](#13-evidencia-de-implementación-2026-08-26) |
| **Principios (pre)** | DIP / OCP violados |
| **Principios (post)** | Host de schemas; el producto implementa `get_ui_schema` / `get_config` / `put_config` |
| **Fecha** | 2026-08-26 (auditoría) · Fase A 2026-08-26 · Fase B iDetectFugas 2026-08-26 · suscripción filtrada **2026-09-01** |
| **Complementa** | [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md), [AUDIT_HMI.md](./AUDIT_HMI.md); producto: `idetectfugas/audits/10-AUDIT_HMI_MACHINE_CONFIG_EXTENSION.md` |
| **Misión** | Evolucionar PyAutomationIO de un framework que **conoce** iDetectFugas a uno que **ignora** el dominio, pero es extraordinariamente extensible |

---

### Índice

1. [Veredicto y pregunta fundamental](#1-veredicto-y-pregunta-fundamental)
2. [Arquitectura genérica esperada vs filtraciones](#2-arquitectura-genérica-esperada-vs-filtraciones)
3. [Inventario exhaustivo de acoplamientos](#3-inventario-exhaustivo-de-acoplamientos)
4. [Anti-patrones de diseño](#4-anti-patrones-de-diseño)
5. [Flujo actual (cómo pide y guarda config la UI)](#5-flujo-actual-cómo-pide-y-guarda-config-la-ui)
6. [Por qué la respuesta es NO](#6-por-qué-la-respuesta-es-no)
7. [Contrato objetivo: Schema-Driven UI](#7-contrato-objetivo-schema-driven-ui)
8. [Neutralidad de `serialize()`](#8-neutralidad-de-serialize)
9. [Test de regresión negativa](#9-test-de-regresión-negativa)
10. [Plan de migración Fase A (PyAutomationIO)](#10-plan-de-migración-fase-a-pyautomationio)
11. [Criterios de aceptación (Definition of Done)](#11-criterios-de-aceptación-definition-of-done)
12. [Fuera de alcance / Fase B](#12-fuera-de-alcance--fase-b)
13. [Evidencia de implementación (2026-08-26)](#13-evidencia-de-implementación-2026-08-26)
14. [Actualización 2026-09-01 — suscripción filtrada](#14-actualización-2026-09-01--suscripción-filtrada)

---

### 1. Veredicto y pregunta fundamental

> ¿Puede un proyecto externo añadir formularios de configuración complejos a la pantalla de detalle de máquinas **sin modificar** el código base de PyAutomationIO?

| Pre Fase A | Post Fase A (este árbol) |
|---|---|
| **NO** | **SÍ** |

**Por qué era NO:** la HMI y `PUT .../attributes` ramificaban por nombres de motores de producto. Inventario histórico en §3.

**Por qué es SÍ ahora:** un engine externo implementa `get_ui_schema` / `get_config` / `put_config`. El framework los detecta por duck-typing, publica `has_domain_config` en `serialize()`, sirve `GET|PUT /api/machines/<name>/domain-config` y renderiza `DomainConfigSlot`. Cero nombres de producto en la API/HMI de machines (guardia en `test_machine_domain_config.py`).

**Fase B (producto):** iDetectFugas implementó el Protocol en LDS/NPW/PPA/PFM/Observer (**2026-08-26**). El slot aparece para esos motores; el toggle probabilidad/estadístico vive en el schema de NPW/PPA, no en `/attributes`.

---

### 2. Arquitectura genérica esperada vs filtraciones

#### 2.1 Lo que el framework debería hacer (capa genérica)

| Capa | Responsabilidad universal |
|---|---|
| `AutomationStateMachine` / workers | Ciclo SM, timings (`execution_interval`, `sample_interval`), buffers, subscribe |
| `PUT /api/machines/<name>/attributes` | `threshold`, `on_delay`, `buffer_size`, intervals, overrides — **solo genéricos** |
| `GET /api/machines/<name>` | Metadatos universales + process vars tipadas |
| HMI `/hmi/machines/detailed` | Inputs genéricos + transitions (reset/restart/…) |
| Transiciones | Independientes del dominio de fuga |

#### 2.2 Lo que filtra dominio de producto (contaminación)

| Síntoma | Dónde |
|---|---|
| Campos API documentados como “Solo PPA/NPW” | `machines.py` model + docstring PUT |
| Clamp 0–100 + `wavelet.threshold_iqr` si `name == "npw"` | `machines.py`, `state_machine.py` (carga BD), Dash legado |
| UI que adivina unidades / locks / pares de tags por substring del nombre | `MachinesDetailed.tsx` |
| Card de atributos gated por `classification.includes("leak detection")` | `MachinesDetailed.tsx` |
| Cliente TS tipa `detection_threshold_mode` en el mismo PUT genérico | `machines.ts` |

`workers/state_machine.py`: **sin** hardcodes de nombres de motores de fuga (limpio en este eje).

---

### 3. Inventario exhaustivo de acoplamientos

Convención de severidad:

| Severidad | Significado |
|---|---|
| **P0** | Bloquea DIP/OCP; debe salir en Fase A |
| **P1** | Contaminación en legado Dash / comentarios / tipado TS; limpiar en el mismo sprint o inmediatamente después |
| **P2** | Duck-typing genérico aceptable *si* se mueve a `/domain-config` y se retira el nombre de producto de mensajes/docs |

#### 3.1 Backend — `automation/modules/machines/resources/machines.py`

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-01 | `machines.py:99-102` | **P0** | Modelo Flask-RESTx `detection_threshold_mode` documentado como *“PPA/NPW only”* — el contrato público del framework nombra productos. |
| BE-DC-02 | `machines.py:575,587-592` | **P0** | Docstring PUT: “Solo PPA/NPW”, persistencia YAML, “otras máquinas NPW legacy”. |
| BE-DC-03 | `machines.py:613,624-630` | **P0** | `detection_threshold_mode` forma parte del contrato de `/attributes` (validación “al menos un atributo”). |
| BE-DC-04 | `machines.py:648-670` | **P0**/P2 | Rama de modo umbral. El `hasattr(set_detection_threshold_mode_from_ui)` es duck-typing usable, pero el **mensaje 400** dice *“only supported for PPA/NPW engines”* — fuga de dominio en la API. |
| BE-DC-05 | `machines.py:677-691` | **P2→mover** | `set_active_detection_threshold_from_ui` — duck-typing OK como puente, pero vive en `/attributes` sobrecargado; debe migrar a `/domain-config`. |
| BE-DC-06 | `machines.py:693-702` | **P0** | Hardcode explícito: `"leak detection" in classification` **y** `machine_name.lower() == "npw"` → clamp 0–100 + `machine.wavelet.threshold_iqr = threshold_value`. El framework **parsea JSON sabiendo que existe NPW**. |
| BE-DC-07 | `machines.py:873-880` | **P1** | Tras persistir, llama `_load_bayesian_motor_thresholds` / `_sync_bayesian_detection_threshold` por nombre de método bayesiano — acoplamiento semántico a iDetectFugas (aunque sea duck-typing). Debe vivir solo tras `put_config` del producto. |

#### 3.2 Backend — `automation/state_machine.py` (carga de config BD)

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-08 | `state_machine.py:279-280` | P1 | Comentario: “módulos (p.ej. NPW/Observer)”. |
| BE-DC-09 | `state_machine.py:294-298` | **P0** | Al hidratar threshold desde BD: si classification contiene `"leak detection"` y `name == "npw"` → escribe `machine.wavelet.threshold_iqr`. Contaminación en el core SM, no solo en la API. |
| BE-DC-10 | `state_machine.py:870-872` | P1 | Comentario `_legacy_sample_and_execute`: “iDetectFugas (LDS/NPW)”. Sin rama ejecutable por nombre; limpiar wording. |
| BE-DC-11 | `state_machine.py:1636-1638` | P1 | Comentario `on_enter_waiting`: “Leak engines…”. |

**Nota:** `serialize()` base (`state_machine.py:1547-1566`) es **genérico** (state, actions, intervals, models). Los flags de dominio (`supports_detection_threshold_mode`, `active_detection_threshold`, etc.) los **añade el producto** al sobrescribir `serialize()` / `get_serialized_models()` — eso es aceptable. El problema es que la **HMI del framework interpreta** esos flags *y además* hardcodea nombres.

#### 3.3 Backend — legado Dash (aún en árbol)

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-12 | `pages/components/machines.py:46-49` | **P0** (legado) | `if "pfm" in machine_name` / `observer` → `disable = True` en formulario de atributos. |
| BE-DC-13 | `pages/callbacks/machines_detailed.py:145-148` | **P0** (legado) | Misma lógica pfm/observer. |
| BE-DC-14 | `pages/callbacks/machines_detailed.py:534-549` | **P0** (legado) | `leak detection` + `npw` → clamp + `wavelet.threshold_iqr`. |

Aunque Dash no sea el path de producto actual, **sigue siendo código base** que viola DIP. Fase A debe neutralizarlo o marcarlo deprecated y eliminar ramas.

#### 3.4 Backend — otros

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-15 | `tags/tag.py:938-949` | P2 | `_machine_threshold_value` usa `get_active_detection_threshold` (duck-typing). Comentario menciona PPA/NPW. Aceptable si el getter es contrato opcional genérico; retirar nombres de producto del docstring. |
| BE-DC-16 | `workers/state_machine.py` | — | **Sin** hardcodes npw/ppa/lds. OK. |

#### 3.5 Frontend — `hmi/src/pages/MachinesDetailed.tsx`

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| FE-DC-01 | `MachinesDetailed.tsx:86-90` | **P0** | `name.includes("lds")` → pares exclusivos flow+density; `pfm`/`observer` → solo density. UI adivina por id. |
| FE-DC-02 | `MachinesDetailed.tsx:118-126` | **P0** | `name === "ppa" \|\| name === "npw"` (o flag) → unidades de modo probabilidad/estadístico. |
| FE-DC-03 | `MachinesDetailed.tsx:128-148` | **P0** | `observer` → unidad leak_flow; `pfm` → %. |
| FE-DC-04 | `MachinesDetailed.tsx:196` | **P0** | Tipo de atributo incluye `detection_threshold_mode` en el flujo genérico de confirmación. |
| FE-DC-05 | `MachinesDetailed.tsx:204-206` | **P0** | `supportsDetectionThresholdMode`: hardcode `ppa`/`npw` **además** del flag serialize. |
| FE-DC-06 | `MachinesDetailed.tsx:211,421,456-476,484,503,777,823` | **P0** | Lectura/escritura de `detection_threshold_mode` / `active_detection_threshold` vía `/attributes`. |
| FE-DC-07 | `MachinesDetailed.tsx:377,626,697,1543-1547` | **P0** | Locks de threshold/buffer/on_delay si nombre ∈ `{pfm, observer}`. |
| FE-DC-08 | `MachinesDetailed.tsx:1914-1918` | **P0** | Card “Machine Attributes” solo si `classification.includes("leak detection")`. El framework decide qué es “leak detection”. |
| FE-DC-09 | `MachinesDetailed.tsx:1968-1982` | **P0** | Select de modo umbral en JSX condicionado al dominio. |

#### 3.6 Frontend — servicios / utils

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| FE-DC-10 | `services/machines.ts:104-116` | **P0** | `updateMachineAttributes` tipa `detection_threshold_mode` en el cliente genérico. No hay `fetchNpwConfig` (bien), pero el campo de dominio está en el API client universal. |
| FE-DC-11 | `utils/tagThreshold.ts:29` | P2 | Prefiere `active_detection_threshold` en serialize de lista — OK si el producto lo publica; no hardcodea nombres. |

#### 3.7 Resumen cuantitativo

| Zona | Hallazgos P0 | P1 | P2 |
|---|---|---|---|
| API machines | 6 | 1 | 1 |
| state_machine core | 1 | 3 | 0 |
| Dash legado | 3 | 0 | 0 |
| HMI React | 9 | 0 | 0 |
| services/utils | 1 | 0 | 1 |
| **Total** | **~20 P0** | **4** | **2** |

---

### 4. Anti-patrones de diseño

#### 4.1 Violación DIP

La capa de alto nivel (HMI + API machines) **depende de detalles de un producto concreto** (nombres de motores iDetectFugas). Debería depender de una **abstracción** (`DomainConfigurable` / schema).

```
Hoy:     HMI ──conoce──► "npw" | "lds" | "pfm" | "leak detection"
Objetivo: HMI ──consume──► ui_schema()  ◄──implementa──  iDetectFugas engines
```

#### 4.2 Violación OCP

- **Abierto a modificación:** cada motor nuevo (o rename `NPW` → `Linea1.NPW`) obliga a tocar `MachinesDetailed.tsx` / `machines.py`.
- **Cerrado a extensión:** no hay registry, slot ni endpoint de dominio. No se puede “enchufar” un form sin PR al framework.

#### 4.3 Responsabilidad conjunta en `/attributes`

El mismo PUT mezcla:

1. Config **universal** (interval, buffer, on_delay, threshold plano).
2. Config **de dominio** (`detection_threshold_mode`, side-effects wavelet/Bayes).

Eso impide evolucionar el producto sin riesgo de romper la UI genérica, y viceversa.

#### 4.4 Falta de tipado declarativo

La UI **adivina** (slider vs select vs unidad) por substring del nombre. El backend no publica un schema de inputs. Resultado: hardcodes FE-DC-01…03.

---

### 5. Flujo actual (cómo pide y guarda config la UI)

```
┌─ Navegador /hmi/machines/detailed ──────────────────────────────┐
│  MachinesDetailed.tsx                                            │
│   • if name includes lds|pfm|observer → pares / locks / units    │
│   • if classification includes "leak detection" → card atributos │
│   • if ppa|npw → select detection_threshold_mode                 │
└───────────────┬───────────────────────────────┬─────────────────┘
                │ GET /api/machines/<name>      │ PUT /api/machines/<name>/attributes
                │                               │  { threshold, on_delay, buffer_size,
                │                               │    detection_threshold_mode, … }
                ▼                               ▼
┌─ machines.py ───────────────────────────────────────────────────┐
│  serialize() genérico + campos que el engine aporte              │
│  PUT:                                                            │
│   • duck-typing set_*_from_ui                                    │
│   • if classification leak + name==npw → wavelet.threshold_iqr   │
│   • persist_ui_config_attributes + sync bayesiano                │
└───────────────┬─────────────────────────────────────────────────┘
                ▼
┌─ Engines iDetectFugas (fuera del repo, pero implícitos) ────────┐
│  YAML planta · Bayes · classic engines                           │
└──────────────────────────────────────────────────────────────────┘
```

**Problema:** el flujo “genérico” ya contiene ramas que solo tienen sentido si el proceso carga motores LDS. Un `GenericMotor` sin esos métodos aún puede ser discriminado por nombre vacío, pero la **card** y los **pares** dependen de classification/nombre de producto.

---

### 6. Por qué la respuesta es NO

Para que un producto externo añada un formulario complejo **sin tocar PyAutomationIO** haría falta al menos uno de:

1. Un **slot** en la HMI que renderice un schema remoto, o  
2. Un **endpoint** de dominio + componente dinámico ya existente en el wheel.

**Ninguno existe hoy.** Las únicas vías reales son:

| Vía | ¿Modifica PyAutomationIO? |
|---|---|
| Nuevo hardcode en `MachinesDetailed.tsx` | **Sí** |
| Nueva rama en `PUT .../attributes` | **Sí** |
| Fork del wheel / patch site-packages | **Sí** (y prohibido en operación) |
| Solo YAML + REST propio fuera de `/hmi/machines/detailed` | No modifica framework, pero **no embebe** en la vista pedida |

Por tanto: **embeber forms de dominio en machines/detailed sin tocar el framework = imposible con el código actual.**

---

### 7. Contrato objetivo: Schema-Driven UI

PyAutomationIO se convierte en **host**. El producto implementa el contrato. Cero nombres de motores en el framework.

#### 7.A Interfaz duck-typing (opcional en engines)

Vivir como protocolo documentado (ABC opcional o solo duck-typing). **No** importar iDetectFugas.

```python
# Conceptual — documentación / typing Protocol en PyAutomationIO
class DomainConfigurable:
    def get_ui_schema(self) -> dict:
        """JSON Schema simplificado: number | select | boolean | string | object | array."""
        ...

    def get_config(self) -> dict:
        """Valores actuales alineados a keys del schema."""
        ...

    def put_config(self, payload: dict) -> dict:
        """Valida, aplica en caliente, persiste. Retorna config efectiva (+ warnings)."""
        ...
```

Helper sugerido en el resource:

```python
def _domain_configurable(machine):
    return all(
        callable(getattr(machine, name, None))
        for name in ("get_ui_schema", "get_config", "put_config")
    )
```

#### 7.B Endpoints desacoplados (no tocar el contrato estable de `/attributes` más que para **eliminar** campos de dominio)

| Método | Ruta | Comportamiento |
|---|---|---|
| `GET` | `/api/machines/<name>/domain-config` | Si `_domain_configurable` → `{ "schema": get_ui_schema(), "config": get_config() }`. Si no → **404** o `{ "supported": false }` (elegir uno y documentarlo; preferencia: **404** limpio para GenericMotor). |
| `PUT` | `/api/machines/<name>/domain-config` | Body → `put_config`; 400 validación; 200 config efectiva. |
| `PUT` | `/api/machines/<name>/attributes` | **Solo** genéricos. Rechazar `detection_threshold_mode` (y cualquier key no whitelist) con **400**. |

Whitelist sugerida de `/attributes` post-Fase A:

`threshold`, `interval`, `execution_interval`, `sample_interval`, `sample_overrides`, `buffer_size`, `on_delay`.

#### 7.C Ejemplo JSON de schema (producto; el framework solo lo renderiza)

```json
{
  "version": 1,
  "title": "NPW",
  "sections": [
    {
      "id": "detection",
      "label": "Detection",
      "fields": [
        {
          "key": "detection_threshold_mode",
          "type": "select",
          "label": "Threshold mode",
          "options": [
            { "value": "probability", "label": "Probability (%)" },
            { "value": "statistic", "label": "Statistic (adim)" }
          ]
        },
        {
          "key": "active_detection_threshold",
          "type": "number",
          "label": "Active threshold",
          "min": 0,
          "depends_on": { "field": "detection_threshold_mode", "equals": "probability" },
          "unit": "%"
        },
        {
          "key": "wavelet.threshold_iqr",
          "type": "number",
          "label": "Wavelet IQR",
          "min": 0,
          "unit": "adim"
        }
      ]
    }
  ],
  "ui_hints": {
    "exclusive_subscribe_pairs": [],
    "lock_generic_attributes": []
  }
}
```

Hints genéricos (reemplazan hardcodes FE):

| Hint | Sustituye |
|---|---|
| `exclusive_subscribe_pairs` | FE-DC-01 (lds/pfm density pairs) |
| `lock_generic_attributes: ["threshold","buffer_size","on_delay"]` | FE-DC-07 (pfm/observer locks) |
| `show_generic_attributes_card: true` | FE-DC-08 (leak detection gate) — o simplemente: mostrar card genérica siempre que existan threshold/on_delay en el engine |
| `threshold_unit` / fields[].unit | FE-DC-02/03 |

#### 7.D Componente React `DomainConfigSlot`

- Props: `machineName`.
- `GET domain-config` → si 404, render `null`.
- Render dinámico: `number` | `boolean` | `select` | `string` | nested `object`/`array` (MVP: number/boolean/select/string).
- Respeta `depends_on`, `min`/`max`, `unit` inline.
- `PUT` al guardar; toasts del design system HMI existente (Bootstrap/AdminLTE del proyecto — **no** introducir MUI solo por esto).
- **Cero** `if (name.includes("npw"))`.

---

### 8. Neutralidad de `serialize()`

#### 8.1 Hoy (contaminación efectiva vía consumidores)

Aunque el `serialize()` base sea limpio, la HMI trata como API estable:

- `supports_detection_threshold_mode`
- `active_detection_threshold`
- `detection_threshold_mode`
- `classification === "…leak detection…"`

#### 8.2 Objetivo (framework)

Campos que el framework garantiza / documenta como estables:

```json
{
  "name": "GenericMotor",
  "state": "running",
  "actions": ["…"],
  "execution_interval": 1.0,
  "sample_interval": null,
  "sample_overrides": {},
  "threshold": { "value": 0.5, "unit": "%" },
  "on_delay": { "value": 5 },
  "buffer_size": { "value": 60 },
  "classification": "Custom",
  "has_domain_config": false
}
```

`has_domain_config` = resultado de `_domain_configurable(machine)` (calculado en el resource al listar/detallar, **no** requiere que el engine lo ponga a mano).

Todo lo demás de dominio **solo** vía `GET /domain-config`.

#### 8.3 Producto (iDetectFugas, fuera de este repo)

Puede seguir enriqueciendo su propio `serialize()` para Socket.IO / tags, pero la HMI **core** no debe ramificar por esos campos. El slot solo mira `has_domain_config` + `/domain-config`.

---

### 9. Test de regresión negativa

Propuesta: `automation/tests/test_machine_domain_config_neutrality.py`

```python
"""CA-DC-NEUTRAL: framework must not special-case product engine names."""

def test_generic_motor_attributes_reject_detection_threshold_mode(client, auth):
    # Arrange: register AutomationStateMachine subclass named "GenericMotor"
    # (no get_ui_schema / put_config / set_detection_threshold_mode_from_ui)
    r = client.put(
        "/api/machines/GenericMotor/attributes",
        json={"detection_threshold_mode": "probability"},
        headers=auth,
    )
    assert r.status_code == 400
    body = r.get_json()
    assert "detection_threshold_mode" in body["message"].lower() or "unknown" in body["message"].lower()
    assert "ppa" not in body["message"].lower()
    assert "npw" not in body["message"].lower()


def test_generic_motor_domain_config_unsupported(client, auth):
    r = client.get("/api/machines/GenericMotor/domain-config", headers=auth)
    assert r.status_code == 404  # or supported:false — pick one in implementation


def test_serialize_has_domain_config_false(client, auth):
    r = client.get("/api/machines/GenericMotor", headers=auth)
    ser = r.get_json()["serialization"]  # shape according to real response
    assert ser.get("has_domain_config") is False


def test_no_product_engine_name_branches_in_machines_module():
    """Static guard — fail CI if npw/ppa/lds/pfm/observer leak into machines resource."""
    from pathlib import Path
    text = Path("automation/modules/machines/resources/machines.py").read_text().lower()
    for token in ("npw", "ppa", "lds", "pfm", "observer", "leak detection"):
        assert token not in text, f"product token {token!r} found in machines API"
```

HMI (opcional e2e / unit del slot): con máquina sin domain-config, **no** montar inputs wavelet ni select de modo.

---

### 10. Plan de migración Fase A (PyAutomationIO)

Objetivo de sprint: **la rama `dev` de PyAutomationIO no tiene menciones de `npw`, `ppa`, `lds`, `pfm`, `observer` ni `leak detection` en la lógica de negocio/UI core de machines.**

#### 10.1 Archivos a tocar

| Archivo | Acción |
|---|---|
| `automation/modules/machines/resources/machines.py` | Añadir resource `domain-config`; whitelist `/attributes`; eliminar BE-DC-01…07 hardcodes/mensajes de producto |
| `automation/state_machine.py` | Eliminar BE-DC-09 (wavelet/npw en hydrate); opcional hook genérico `machine.apply_persisted_threshold(value)` duck-typing |
| `hmi/src/pages/MachinesDetailed.tsx` | Quitar FE-DC-01…09; integrar `DomainConfigSlot`; card genérica sin gate leak; locks/pares desde `ui_hints` o schema |
| `hmi/src/services/machines.ts` | Quitar `detection_threshold_mode` de attributes; añadir `getDomainConfig` / `putDomainConfig` |
| `hmi/src/components/DomainConfigSlot.tsx` | **Nuevo** — renderer schema |
| `automation/pages/components/machines.py` | Neutralizar o deprecar hardcodes pfm/observer |
| `automation/pages/callbacks/machines_detailed.py` | Neutralizar BE-DC-13/14 |
| `automation/tags/tag.py` | Docstring neutro (BE-DC-15) |
| `automation/tests/test_machine_domain_config_neutrality.py` | **Nuevo** |
| `docs/Developments_Guide/…` | Documentar Protocol DomainConfigurable |

#### 10.2 Qué deprecar

| Ítem | Estrategia |
|---|---|
| `detection_threshold_mode` en `/attributes` | **Eliminar** del model (breaking para clientes que lo usen). Coordinar release con iDetectFugas Fase B el mismo tren, o window: aceptar el key una release con `DeprecationWarning`/header y log, luego 400. Preferencia auditoría: **corte limpio en minor 2.9** + bump simultáneo producto. |
| Flags HMI que leen `supports_detection_threshold_mode` desde serialize para UI core | Dejar de usar en MachinesDetailed; el slot usa schema |
| Comentarios con nombres de producto | Reescribir a lenguaje genérico |

#### 10.3 Qué lógica eliminar (checklist grep)

Tras el PR, estos comandos deben devolver **vacío** (salvo tests que aserten ausencia, docs de migración, o este audit):

```bash
rg -i 'npw|ppa|\blds\b|pfm|observer|leak detection' \
  automation/modules/machines/ \
  hmi/src/pages/MachinesDetailed.tsx \
  hmi/src/services/machines.ts \
  automation/pages/components/machines.py \
  automation/pages/callbacks/machines_detailed.py
```

Excepción permitida temporal: este archivo `audits/AUDIT_HMI.md` y changelogs.

#### 10.4 Orden de implementación sugerido

1. Endpoints `/domain-config` + tests neutralidad (aún sin UI).
2. Whitelist `/attributes` + borrar rama npw/wavelet + hydrate state_machine.
3. `DomainConfigSlot` + cableado en MachinesDetailed.
4. Purge hardcodes FE + Dash.
5. Guard CI `rg` + release notes 2.9.x.
6. Coordinar iDetectFugas Fase B (implementar `get_ui_schema`/`get_config`/`put_config` en motores) **en el mismo tren de release** para no dejar hueco UX.

---

### 11. Criterios de aceptación (Definition of Done)

- [x] Pregunta fundamental → **SÍ** para un engine externo que implemente el Protocol (`ConfigurableMotor` en tests).
- [x] `rg` de tokens de producto en paths de §10.3 → vacío (`TestNoProductEngineNameBranches`).
- [x] `GenericMotor` + PUT `detection_threshold_mode` → **400** sin mencionar PPA/NPW.
- [x] `GenericMotor` + GET `domain-config` → 404; HMI no monta slot si no hay schema.
- [x] Engine con Protocol → GET/PUT domain-config round-trip (test de resource).
- [ ] DAQ / OPCUAServer sin regresión visual en detailed (verificación HMI manual / planta).
- [x] Ningún nuevo `if (name.includes(...))` de producto en HMI core.

---

### 12. Fuera de alcance / Fase B

| Ítem | Repo | Estado |
|---|---|---|
| Schemas reales LDS/NPW/PPA/PFM/Observer | **iDetectFugas** | **Implementado** (2026-08-26) |
| Persistencia YAML Bayes / classic configs | **iDetectFugas** | **Implementado** |
| Panel rico de aportes bayesianos (charts) | iDetectFugas (extensión remota opcional post-slot) | Pendiente |
| Editar site-packages en edge | **Prohibido** | — |

Documento hermano de producto: `gitlab/intelcon/idetectfugas/audits/10-AUDIT_HMI_MACHINE_CONFIG_EXTENSION.md`.

---

### Apéndice A — Mapeo hallazgo → acción

| ID | Acción Fase A |
|---|---|
| BE-DC-01…03 | Quitar del model `/attributes`; vivir en domain-config del producto |
| BE-DC-04…05 | Mover a PUT domain-config; mensajes API sin nombres de motor |
| BE-DC-06, BE-DC-09, BE-DC-14 | **Eliminar**; producto aplica wavelet en `put_config` / hydrate propio |
| BE-DC-07 | No invocar sync bayesiano desde framework; producto en `put_config` |
| BE-DC-12…13 | Locks vía `ui_hints` o atributos read_only del engine |
| FE-DC-01…09 | Sustituir por DomainConfigSlot + hints |
| FE-DC-10 | API client domain-config |

### Apéndice B — Diagrama objetivo

```
MachinesDetailed
  ├── GenericSection  →  PUT /attributes   (whitelist universal)
  └── DomainConfigSlot
        ├── GET  /domain-config  →  get_ui_schema + get_config   ⎤
        └── PUT  /domain-config  →  put_config                    ⎦ solo si el engine implementa el Protocol
                                                                    (código 100% en el proyecto externo)
```

**Cierre histórico (§1–12):** el inventario describe el acoplamiento **antes** de Fase A.

---

### 13. Evidencia de implementación (2026-08-26)

Fase A está en el árbol. PyAutomationIO **ignora** nombres de producto y hospeda schemas.

#### 13.1 Archivos nuevos

| Archivo | Rol |
|---|---|
| `automation/domain_config.py` | `DomainConfigurable` Protocol, `supports_domain_config`, `GENERIC_ATTRIBUTE_KEYS`, `SCHEMA_VERSION_SUPPORTED = 1` |
| `hmi/src/components/DomainConfigSlot.tsx` | Renderer schema-driven (number/select/boolean/string; object anidado; array JSON; `depends_on`) |
| `automation/tests/test_machine_domain_config.py` | GenericMotor / ConfigurableMotor / 400 attributes / guardia estática |
| `docs/Developments_Guide/core/domain_config.md` | Guía de desarrolladores |

#### 13.2 API implementada

- `GET /api/machines/<name>/domain-config` → `{schema, config}` o **404** (`MachineDomainConfigResource` en `machines.py`).
- `PUT /api/machines/<name>/domain-config` → `put_config`; `ValueError`/`TypeError` → 400; 200 `{status, config}`.
- `PUT /api/machines/<name>/attributes` rechaza keys fuera de `{threshold, on_delay, interval, execution_interval, sample_interval, sample_overrides, buffer_size}` con 400 **sin** nombres de producto.
- `StateMachineCore.serialize()` incluye `has_domain_config`.

#### 13.3 HMI

- `MachinesDetailed.tsx` ya no ramifica por nombre/classification de producto.
- Card genérica si hay threshold/on_delay/buffer; locks y pares exclusivos desde `ui_hints`.
- `DomainConfigSlot` se monta cuando hay schema cargado (`has_domain_config` → GET domain-config).
- Cliente: `getMachineDomainConfig` / `putMachineDomainConfig` en `hmi/src/services/machines.ts`.

#### 13.4 Hallazgos cerrados

| ID | Estado | Evidencia |
|---|---|---|
| BE-DC-01…03 | Cerrado | `detection_threshold_mode` eliminado del model Flask-RESTx y del PUT |
| BE-DC-04…05 | Cerrado | Ramas `set_*_from_ui` y mensajes PPA/NPW eliminadas de `/attributes` |
| BE-DC-06 | Cerrado | Rama `"leak detection"` + `name == npw` + `wavelet.threshold_iqr` eliminada |
| BE-DC-07 | Cerrado | Sync bayesiano ya no se invoca desde el framework |
| BE-DC-08, BE-DC-10, BE-DC-11 | Cerrado | Comentarios reescritos a lenguaje genérico |
| BE-DC-09 | Cerrado | Hydrate BD: if NPW/wavelet eliminado; hook opcional genérico `apply_persisted_threshold` |
| BE-DC-12…14 | Cerrado | Dash sin `pfm`/`observer`/`npw`/`leak detection` |
| BE-DC-15 | Cerrado | Docstring de `_machine_threshold_value` neutro |
| FE-DC-01…09 | Cerrado | Hardcodes HMI sustituidos por hints + slot |
| FE-DC-10 | Cerrado | `detection_threshold_mode` fuera de `updateMachineAttributes` |

#### 13.5 Tests (PASS)

`python -m unittest automation.tests.test_machine_domain_config -v` — 10 tests OK, incluyendo:

- `has_domain_config` false/true
- PUT attributes con `detection_threshold_mode` → 400 sin `ppa`/`npw`
- GET/PUT domain-config round-trip + `ValueError` → 400
- Guardia estática sobre paths de §10.3

#### 13.6 Fase B producto (2026-08-26 — cerrada)

iDetectFugas implementó el Protocol en LDS, NPW, PPA, PFM y Observer. Evidencia en `gitlab/intelcon/idetectfugas/audits/11-AUDIT_SPEC_IDETECTFUGAS_ENGINE_CONFIG.md` §13.

---

### 14. Actualización 2026-09-01 — suscripción filtrada

Mejoras en el árbol fuente (pueden no estar en wheel `2.8.1` empaquetado hasta rebuild).

| Tema | Archivo | Comportamiento |
|------|---------|----------------|
| Metadatos tags de campo | `automation/modules/machines/resources/machines.py` — `_field_tag_info`, `_tag_opcua_mapped` | GET máquina incluye `field_tags_info`: `name`, `variable`, `unit`, `opcua_mapped`, `opcua_client_name` |
| Compatibilidad de tipos | `automation/variables/__init__.py` — `variable_for_unit`, `compatible_field_variables` | MassFlow ↔ VolumetricFlow intercambiables; resto exige mismo tipo |
| Validación subscribe | `machines.py` POST subscribe | Rechaza tag no mapeado OPC UA o tipo incompatible con variable interna |
| Orden UX HMI | `hmi/src/pages/MachinesDetailed.tsx` — `getCompatibleFieldTags` | Primero variable interna; dropdown Tags de Campo deshabilitado hasta selección; filtra por `opcua_mapped` y tipo |
| Tooltips schema | `hmi/src/components/DomainConfigSlot.tsx` — `FieldHelpLabel` | `help_display: "tooltip"` en schemas de producto → icono `bi-info-circle` |
| `ProcessType.variable` | `automation/models.py` — `serialize()` | Expone variable lógica para inferir tipo en suscripción |
| Tests | `automation/tests/test_resolve_units_for_variable.py`, `automation/tests/test_machine_domain_config.py` | Compatibilidad tipos; guardia anti-acoplamiento |

**Coordinación producto:** iDetectFugas emite `_subscribe_mapping_hint` permanente en `get_config()` de cada motor; el framework filtra tags en la card de suscripción genérica — ver `idetectfugas/audits/10-AUDIT_HMI_MACHINE_CONFIG_EXTENSION.md` §14.

