# Auditoría compacta: acondicionamiento de señal en tags (Wavelet RT / IAD)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/Tags.tsx`) |
| **Alcance** | Filtro wavelet DWT en worker, deadband, calidad OPC en `.f`, IAD (outlier / out-of-range / frozen). CPU en hot path, fugas, idoneidad industrial |
| **Fuera de alcance** | `DedupeFilter` de logs, `filter_by` de API, Plotly, algoritmos LDS/PFM de iDetectFugas |
| **Fecha original** | 2026-08-16 |
| **Revisión wavelet** | 2026-08-19 — implementación `feature/wavelet-rt`: DWT por bloques en `WaveletWorker`, hot path O(1), tag derivado `.f`, sync a `sample_interval` SM |
| **Revisión A+** | 2026-08-19 — propagación calidad OPC al tag `.f`, eliminación definitiva de legado (`gaussian_filter*`, `process_filter`, Kalman), HMI observabilidad |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [specs/08-WAVELET-RPA-RT.md](../specs/08-WAVELET-RPA-RT.md) |
| **Veredicto estático** | **A− (wavelet RT operativo)** / **C (nuclear/DCS)**. Pipeline wavelet completo: calidad OPC, deadband único, persistencia eager, API/HMI observabilidad, esquema BD limpio. Pendiente: IAD, soak 24 h, golden trace, integración SM en CI |
| **Clasificación** | Auditoría de acondicionamiento de señal |

---

## 0. Respuesta directa

| Palanca | ¿Runtime? | Qué es hoy |
|---|---|---|
| **Filtro wavelet (`filter_enabled`)** | **Sí** | DWT + soft-threshold + IDWT en `WaveletWorker`; hot path solo encola O(1). SM consume tag `.f` |
| **Calidad OPC en `.f`** | **Sí** | Muestra BAD/NaN → `HOLD` + publicación `UNCERTAIN` con último valor bueno; GOOD al recuperar señal |
| **Filtro gaussiano / Kalman** | **Eliminado** | Columnas BD, API, HMI, `filter.py`, `@filter` y páginas Dash retirados (2026-08-19) |
| **Filtro de proceso (`process_filter`)** | **Eliminado** | Columna SQL eliminada por migración idempotente `_drop_legacy_tag_columns()` |
| **Deadband** | **Sí** | Puerta única en `Tag.set_value`; CVT respeta `False` y no re-emite |
| **Outlier / OOR / frozen (IAD)** | **No en hot path** | Decoradores IAD **comentados**. Stubs sin enganche |

**Mensaje operativo:** el filtrado de señal para control de proceso es **wavelet RT** vía tag `{nombre}.f`. Raw permanece en el tag source. Ante datos inválidos, el operador ve calidad **UNCERTAIN** en `.f` y estado **hold** en HMI/Performance.

Cadena con wavelet ON y SM suscrita:

```
OPC datachange (hilo suscripción)
  → set_value_fast → CVT.set_value(..., quality)
  → Tag.set_value (deadband único, raw + quality)
  → _ingest_wavelet_sample → SampleRing.append O(1)   [sin pywt]

WaveletWorker (hilo dedicado, tick ~50 ms)
  → cada sample_interval de la SM:
       WaveletBlockFilter.process()
         · BAD/NaN → HOLD, publica UNCERTAIN + last_good_value
         · buffer lleno → OK, publica GOOD
  → CVT.set_value(tag.f, ..., quality=result.quality)
  → SM buffer ← valores filtrados alineados al ciclo de muestreo
  → SAF (si filter_persist) almacena value + quality en journal
```

---

## 1. Inventario de código (post-A+)

| Pieza | Archivo | Rol |
|---|---|---|
| Calidad OPC | `automation/signal_conditioning/quality.py` | `GOOD` / `UNCERTAIN` / `BAD`; helpers ingest |
| Anillo O(1) | `automation/signal_conditioning/sample_ring.py` | `SampleRing`: encolado thread-safe |
| DWT bloques | `automation/signal_conditioning/wavelet_block.py` | `WaveletBlockFilter`: DWT, HOLD, métricas status |
| Tags `.f` | `automation/signal_conditioning/filtered_tags.py` | `ensure_filtered_tag`, `resolve_subscription_tag` |
| Worker | `automation/workers/wavelet_worker.py` | Publicación con `quality` en `.f` |
| Hot path | `automation/tags/tag.py`, `automation/tags/cvt.py` | Deadband + ingest + `quality` en `set_value` |
| SM | `automation/state_machine.py` | `subscribe_to` → `.f` + registro worker |
| Persistencia / API | `dbmodels/tags.py`, `modules/tags/resources/tags.py` | Solo `filter_*`; migración + drop legacy |
| HMI | `WaveletFilterPanel.tsx`, `Tags.tsx`, `Performance.tsx` | Panel wavelet, badge calidad, widget filtros activos |
| Tests | `automation/tests/test_wavelet_filter.py` | 14 tests (calidad HOLD/OK, deadband, worker publish) |
| IAD | `automation/iad/*.py` | **no enganchado** |

**Eliminados:** `automation/tags/filter.py`, `automation/filter/__init__.py`, páginas Dash `/filter`, columnas `gaussian_filter*`, `process_filter`.

---

## 2. Filtro wavelet — diseño e idoneidad

### 2.1. Decisiones de arquitectura (conformes a spec)

| Requisito | Estado |
|---|---|
| Hot path O(1), sin DWT en OPC | **Cumple** |
| Worker off-thread | **Cumple** |
| Alineación temporal SM | **Cumple** |
| Tag derivado trazable | **Cumple** — sufijo `.f` |
| Persistencia opcional / eager | **Cumple** — `filter_persist` + `_sync_wavelet_runtime` |
| Calidad OPC en `.f` | **Cumple** — HOLD + UNCERTAIN ante BAD/NaN |
| Coste acotado por publicación | **Cumple** |

### 2.2. Semántica de calidad (operador)

| Condición ingest | Estado filtro | Calidad `.f` | Valor `.f` |
|---|---|---|---|
| Muestra GOOD, buffer en warmup | `warmup` | `UNCERTAIN` | Último raw / parcial |
| Muestra GOOD, buffer lleno | `ok` | `GOOD` | Valor DWT filtrado |
| Muestra BAD / NaN / inf | `hold` | `UNCERTAIN` | Último valor bueno conocido |
| Sin datos en anillo | `no_data` | — | Sin publicación |
| Error DWT irrecuperable | `failed` | — | Último resultado si existe |

El contador `bad_samples_dropped` (alias `drop_count`) y `last_publication_quality` se exponen en `GET /tags/{name}/filter/status`.

### 2.3. Huecos respecto a grado industrial

| ID | Sev. | Hallazgo |
|---|---|---|
| **WF-2** | Media | Lazy register antes de suscripción SM |
| **WF-4** | Baja | Sin golden trace / bench p95 documentado |
| **WF-6** | Baja | Sin test integración SM + `.f` en CI |

---

## 3. Legado gaussiano / process_filter — eliminado

Migración `DBManager._drop_legacy_tag_columns()` elimina de forma idempotente: `gaussian_filter`, `gaussian_filter_threshold`, `gaussian_filter_r_value`, `process_filter`.

Modelo Peewee, API REST, CVT, Tag, HMI, audit trail y páginas Dash ya no referencian estos campos. **NF-7 ampliado: cerrado en todo el stack.**

---

## 4. IAD — sigue muerto en el hot path

Sin cambio. Decoradores comentados en `CVT.set_value`. Hallazgos **NF-IAD-1..4** vigentes si se reactiva sin refactor.

---

## 5. CPU / memoria

Hot path OPC: O(1) con wavelet ON. DWT solo en `WaveletWorker`. Deadband único (**NF-6 cerrado**).

---

## 6. ¿Grado nuclear / DCS?

| Dimensión | Nota |
|---|---|
| Wavelet RT (funcional) | **A−** — listo para producción operativa |
| Nuclear / DCS / SIL | **C** — IAD desconectado, soak/golden trace pendientes |

---

## 7. Hallazgos numerados (consolidado)

| ID | Sev. | Estado | Hallazgo |
|---|---|---|---|
| **NF-1** | Crítica | **Cerrado** | `process_filter` eliminado (código + BD) |
| **NF-2..NF-4** | Alta | **Cerrado** | Kalman / `@filter` eliminados del repo |
| **NF-6** | Media | **Cerrado** | Deadband único en `Tag.set_value` |
| **NF-7** | Media | **Cerrado** | Gaussiano eliminado de UI, API, BD, Dash |
| **NF-8** | Media | Abierto | IAD comentado |
| **WF-1** | Media | **Cerrado** | Calidad OPC propagada a `.f` + API + HMI |
| **WF-5** | Baja | **Cerrado** | Panel Wavelet RT + widget Performance |

---

## 8. Recomendaciones (priorizadas)

1. Soak RSS 24 h con wavelet ON (**CA-A+-06** / **CA-NF-2**).
2. Golden trace wavelet vs referencia offline (**CA-WF-1**).
3. Tests de integración SM → `.f` en CI (**WF-6**).
4. Propagar `quality` desde OPC UA subscription (hoy default GOOD en adquisición).

---

## 9. Certificación

| ID | Criterio | Estado |
|---|---|---|
| **CA-A+-01** | Panel Wavelet: switch, parámetros, estado en vivo | **Cerrado** |
| **CA-A+-02** | Persistencia eager `.f` si `filter_persist` | **Cerrado** |
| **CA-A+-03** | Deadband único; no encola si `\|Δ\| < dead_band` | **Cerrado** |
| **CA-A+-04** | Endpoints `/filter/status` | **Cerrado** |
| **CA-A+-05** | Gaussiano/process_filter retirados de UI Tags | **Cerrado** |
| **CA-A+-07.1** | BAD → `.f` UNCERTAIN + HOLD | **Cerrado** (unit tests) |
| **CA-A+-07.2** | GOOD tras HOLD → OK/GOOD | **Cerrado** (unit tests) |
| **CA-A+-07.3** | API: `bad_samples_dropped`, `last_publication_quality`, `last_good_value` | **Cerrado** |
| **CA-A+-07.4** | Widget Performance muestra calidad `.f` | **Cerrado** |
| **CA-A+-08.1** | Columnas legacy no existen en `Tags` | **Cerrado** (migración) |
| **CA-A+-08.2** | Modelo Peewee sin campos legacy | **Cerrado** |
| **CA-A+-08.3** | Serialización GET/POST sin legacy | **Cerrado** |
| **CA-A+-08.4** | `filter.py` y `filter/__init__.py` eliminados | **Cerrado** |
| **CA-A+-08.5** | Arranque y carga de tags sin errores | **Pendiente** validación manual deploy |
| **CA-WF-1** | Golden trace offline | **Pendiente** |
| **CA-WF-2** | Integración SM + `.f` | **Pendiente** |
| **CA-WF-3** | Bench p95 multi-tag | **Pendiente** |
| **CA-NF-2** | Soak 24 h RSS | **Pendiente** |
| **CA-HMI-1** | Panel + i18n + rebuild bundle | **Cerrado** en código |

**Formulación actual (2026-08-19):** *adquisición raw + deadband; filtrado wavelet off-thread vía `.f` con calidad OPC; legado gaussiano/process_filter eliminado; certificación nuclear/DCS pendiente de IAD y V&V de campo.*

---

## 10. HMI — configuración wavelet RT

### 10.1. Ubicación

| Aspecto | Diseño |
|---|---|
| **Pantalla** | `hmi/src/pages/Tags.tsx` — modales Crear/Editar |
| **Componente** | `WaveletFilterPanel.tsx` — switch, badge estado, parámetros colapsables |
| **Solo tags fuente** | Controles ocultos en `*.f` |
| **Tipos** | Solo `data_type === 'float'` |

### 10.2. Observabilidad en panel

| Elemento | Fuente |
|---|---|
| Badge estado | `GET /tags/{name}/filter/status` → `status` |
| Badge calidad `.f` | `last_publication_quality` (GOOD / UNCERTAIN) |
| Contador descartes | `bad_samples_dropped` |
| Tag derivado | `{nombre}.f` (solo lectura) |
| Latencia | `age_ms` |

### 10.3. Widget Performance (`/performance`)

Tabla «Filtros wavelet activos»: source, `.f`, status, **calidad .f**, age, rate. Poll cada 5 s vía `GET /tags/filter/status`.

### 10.4. Persistencia BD (`Tags`)

| Columna | Tipo | Default |
|---|---|---|
| `filter_enabled` | `BOOLEAN` | `false` |
| `filter_wavelet` | `VARCHAR(16)` | `'db4'` |
| `filter_level` | `INTEGER` | `4` |
| `filter_threshold_factor` | `FLOAT` | `3.0` |
| `filter_persist` | `BOOLEAN` | `false` |

**Columnas eliminadas:** `gaussian_filter`, `gaussian_filter_threshold`, `gaussian_filter_r_value`, `process_filter`.

### 10.5. API filter status (respuesta ampliada)

```json
{
  "enabled": true,
  "status": "hold",
  "source": "Area1.Presion",
  "filtered_tag": "Area1.Presion.f",
  "age_ms": 1200.5,
  "last_value": 4.82,
  "last_good_value": 4.82,
  "bad_samples_dropped": 3,
  "last_publication_quality": "UNCERTAIN",
  "raw_rate": 1.0,
  "sample_interval": 1.0
}
```

### 10.6. Claves i18n

| Clave | ES | EN |
|---|---|---|
| `tags.waveletFilter` | Filtro wavelet (tiempo real) | Wavelet filter (real-time) |
| `tags.waveletPublicationQuality` | Calidad .f | .f quality |
| `tags.waveletDropped` | Descartes | Dropped |
| `performance.waveletQuality` | Calidad .f | .f quality |

### 10.7. Estado de implementación

| Capa | Estado |
|---|---|
| BD + migración `filter_*` + drop legacy | **Implementado** |
| Calidad OPC en `.f` + SAF journal | **Implementado** |
| API `/filter/status` ampliado | **Implementado** |
| HMI panel + Performance widget | **Implementado** |
| Tests unitarios calidad | **Implementado** (14 tests OK) |
| Rebuild bundle HMI en deploy | **Pendiente** operación |

---

## 11. Runbook operativo (calidad `.f`)

1. Si el operador ve **UNCERTAIN** en tendencia `.f` o badge **hold** en Tags/Performance → revisar calidad OPC del tag **source** (instrumento, cableado, servidor OPC).
2. El valor mostrado en `.f` durante hold es el **último valor bueno filtrado**, no el raw defectuoso.
3. Al recuperar muestras GOOD, el filtro reanuda automáticamente; puede haber 1–N ciclos de **warmup** antes de **ok**.
4. Consultas históricas: el journal SAF incluye campo `quality` cuando está disponible en el sample.
