# Auditoría: UI/UX de Tendencias en Tiempo Real (`/real-time-trends`)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomation HMI (`hmi/src`) |
| **Alcance** | Estética, usabilidad, layout/canvas, edición de cards, picker de tags y granularidad de movimiento de la vista de tendencias en tiempo real. **No** cubre fidelidad de serie ni heap (eso vive en [AUDIT_HMI.md](./AUDIT_HMI.md)) |
| **Fecha** | 2026-09-09 · **implementación spec HMI 2.10** misma fecha |
| **Evidencia** | Código `hmi/src/pages/RealTimeTrends.tsx`, `StripChart.tsx`, `workspaceStore.ts`, `realtimeTrendsGrid.ts`, `usePlotlyResize.ts`, `global.css`; backend `automation/modules/settings/workspace.py`; tests `test_realtime_trends_workspace.py` |
| **Complementa** | [AUDIT_HMI.md](./AUDIT_HMI.md) (rendimiento RT / forma de onda), [AUDIT_TIMEZONE.md](./AUDIT_TIMEZONE.md), [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md) |
| **Veredicto vigente** | Layout **B+ (en implementación, código)** — módulos A–E de la spec UI/UX cerrados en esta entrega. Datos RT **A−** (vía AUDIT_HMI). Fuera de alcance: RT-LAY-02 (Ctrl+drag libre) y RT-EDIT-03 (guías). Verificación planta CA-RT-01…08 pendiente de corrida en HMI vivo |
| **Clasificación** | Auditoría de frontend · UI/UX · layout · Confidencialidad interna |
| **Estado** | **En implementación** — schema v3 + canvas 48×10 + Plotly desacoplado + MultiSelectSearch + persistencia con circuit breaker |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-09-09) |
|---|---|
| ¿Qué es la pantalla? | Un canvas de **strip charts Plotly** sobre `react-grid-layout`, con workspace por estación (local + servidor) |
| ¿Cómo se edita? | **Doble clic** en la página → modo edición. Toolbar (Agregar Gráfico, umbrales) **solo** aparece ahí |
| ¿El card nuevo “latea” (crece/decrece) hasta hacer click? | **Sí, reproducible en código.** Cadena Plotly `useResizeHandler` + `autosize` + transición CSS 200 ms del grid item + leyenda externa. Hallazgo **UX-RT-1** (crítico) |
| ¿El botón Tags muestra mal la lista? | **Sí.** Dropdown absoluto dentro de un panel con `overflow-y: auto` → la lista de ~280 px se **recorte** y a menudo se ve ~1 fila. Hallazgo **UX-RT-2** (alto) |
| ¿Se puede mover un card píxel a píxel? | **No.** Snap a celda: 12 columnas × `rowHeight=40` px + margen 10. Paso mínimo ≈ **~1/12 del ancho** y **50 px** en vertical (40+10). Hallazgo **UX-RT-3** (medio–alto, requisito de producto) |
| ¿Es estética “industrial / sala de control”? | Parcial. Chrome Bootstrap genérico, mode bar Plotly siempre visible, densidad no alineada con Trends históricos. Funcional en planta; no es una composición de diseño deliberada |

---

## 1. Mapa del código (evidencia)

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

## 2. Cómo funciona la vista (scope completo)

### 2.1 Modelo mental

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

### 2.2 Modos

| Aspecto | Visualización | Edición |
|---|---|---|
| Entrada | Doble clic en el `row` de la página | Mismo toggle |
| Toolbar | Ausente | Título, switch umbrales, badge “Modo Edición”, “Agregar Gráfico” |
| Drag / resize | `static`, deshabilitados | Activos; handle `.drag-handle` = **todo el header** |
| Título | Texto + `QualityBadge` por tag | `<input>` |
| Tags / ventana / borrar | Ocultos | Visibles |
| Umbrales Plotly | **Nunca** (`showThresholds={isEditMode && showThresholds}`) | Solo si el switch está ON |

Implicación UX: en **producción** el operador no ve umbrales aunque los haya configurado, y no hay affordance visible de “puedo editar” salvo el empty state o conocimiento tribal del doble clic.

### 2.3 Grid / canvas — números

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

### 2.4 Flujo “Agregar Gráfico”

1. Modo edición → botón success “Agregar Gráfico”.
2. Se inserta un card **vacío** (`tagNames: []`) con empty state (“configura tags…”).
3. El operador abre **Tags (0)** en el header del card.
4. Panel flotante + búsqueda → al elegir el **primer tag**, se monta `<Plot/>`.
5. Ahí es donde aparece el lateo de tamaño (**UX-RT-1**).

### 2.5 Flujo “Tags” (botón `bi-tags`)

No es `MultiSelectSearch`. Es un panel propio:

1. Toggle abre `.stripchart-tag-config` (absoluto, `z-index: 10000`).
2. Si ya hay tags, la lista de búsqueda arranca **cerrada** (chips primero).
3. Focus / tipeo en el input abre `.stripchart-tag-search-list` con `VirtualList` (`height={280}`, `itemHeight={52}` → ~5 filas teóricas).
4. Escape / click fuera cierra lista o panel.
5. Límite de 2 unidades → toast; `loadingTags` se setea pero **nunca se pinta** en UI.

### 2.6 Persistencia

- Cache: `localStorage` `pyautomation.workspace.realtime-trends.v1` (+ migración legacy).
- Fuente de verdad de estación: `GET/PUT /settings/workspace/realtime-trends`.
- Hidratación: remoto con charts gana; si vacío, migra local.
- Sanitize: clamps de `w/h`, tope 24 charts, títulos y tags.

---

## 3. Hallazgos del operador (prioridad)

### UX-RT-1 — Card de plot nuevo latea de tamaño hasta el click (crítico)

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

### UX-RT-2 — Lista de tags casi ilegible al pulsar Tags (alto)

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

### UX-RT-3 — Movimiento de cards solo por celdas, no px a px (medio–alto)

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

## 4. Pros (lo que está bien)

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

## 5. Contras estéticos y de UX (además de UX-RT-1…3)

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

## 6. Estética — lectura de diseño

### 6.1 Primera impresión (modo planta)

- Sin toolbar: el canvas es solo cards + empty state.
- Cards Bootstrap `shadow-sm`, header compacto, Plotly con mode bar.
- No hay hero ni branding de la vista; depende del layout global (sidebar + MainLayout).
- Sensación: **tablero técnico funcional**, no composición deliberada.

### 6.2 Primera impresión (modo edición)

- Aparece toolbar con badge warning “Modo Edición” — buena señal de estado.
- Handles de resize y grip vertical ayudan, pero el lateo del plot (**UX-RT-1**) domina la percepción de calidad.
- El picker Tags (**UX-RT-2**) rompe el flujo en el momento más crítico (añadir señal).

### 6.3 Comparación con hermanas del HMI

| Vista | Layout | Selección tags | Densidad |
|---|---|---|---|
| Real-time trends | RGL celdas 12×40 | Panel ad-hoc | Sin fit viewport |
| Trends históricos | Charts fijos / fit | `MultiSelectSearch` | `trends-fit-viewport` |
| Performance | RGL (API v2) | N/A (métricas fijas) | Tiles densos |
| LDS dashboard | RGL + tabs | N/A | Paneles densos |

La vista RT es la que **más necesita** un canvas de diseño y, a la vez, la que tiene la **metáfora de edición menos madura**.

---

## 7. Matriz de severidad y criterios de aceptación (futuros)

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

## 8. Runbook de verificación manual (planta / lab)

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

## 9. Residual / fuera de alcance de este documento

| ID | Nota |
|---|---|
| UX-R1 | Fidelidad 1 Hz / huecos de serie → [AUDIT_HMI.md](./AUDIT_HMI.md), no UI |
| UX-R2 | Coste de Plotly con muchos tags @ throttle 200 ms → performance, no estética |
| UX-R3 | i18n de strings de banner socket vs copy del picker → menor |
| UX-R4 | RT-LAY-02 (lienzo libre px) y RT-EDIT-03 (guías) quedan **fuera** de HMI 2.10; granularidad = grid 48×10 (§11) |

---

## 10. Cierre

La pantalla de tiempo real **cumple** como visor de series con workspace de estación durable y buen cuidado del canal de datos. Como **herramienta de diseño de layouts** —que es lo que el modo edición promete— hoy **no** está a nivel industrial:

1. El card nuevo que latea (**UX-RT-1**) rompe la sesión de edición.
2. El picker Tags ilegible (**UX-RT-2**) bloquea el flujo de añadir señales.
3. El snap grueso (**UX-RT-3**) impide la flexibilidad de composición que el operador pide.

Pros reales (workspace, empty states, límites, tema Plotly) no compensan esos tres puntos en la percepción del producto. El siguiente paso no es “pulir CSS”: es **cerrar el bucle de resize**, **sacar la lista de tags del overflow**, y **decidir el contrato de granularidad del canvas** antes de tocar código.

**Veredicto (auditoría original):** UI/UX de layout **C+ / B−**; datos RT y persistencia **A−** (vía AUDIT_HMI + workspace). Prioridad de remedio: UX-RT-1 → UX-RT-2 → decisión UX-RT-3 → affordances de edición (UX-RT-4/6/5).

La entrega posterior está en la **§11**.

---

## 11. Implementación 2026-09-09 — spec UI/UX HMI 2.10 (módulos A–E)

**Decisión de producto:** grid canónico **48 columnas / `rowHeight=10`** en edición y visualización. Migración **una vez** al hidratar (schema 2 → 3). **No** se incluye RT-LAY-02 (Ctrl+drag libre en px) ni RT-EDIT-03 (guías de alineación). Flag Vite `VITE_RT_TRENDS_LAYOUT_V3` (default `true`).

### 11.1 Contrato schema v3

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

### 11.2 Remediación vs hallazgos

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

### 11.3 Criterios CA-RT (spec)

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

### 11.4 Persistencia

- Debounce 300 ms; localStorage primero; PUT con timeout 10 s.
- Circuit breaker: 3 fallos → `offline` 5 min; `setInterval` 60 s para reintentar; banner «Cambios guardados localmente».
- Export/import JSON v3 pasa por `sanitize` + `migrateLayout`.

### 11.5 Fuera de esta entrega

Fuse.js, `@floating-ui`, DOMPurify, pixel-perfect libre, snap guides, cifrado de localStorage, CSP nonce nuevo, `REACT_APP_GRID_V2`.
