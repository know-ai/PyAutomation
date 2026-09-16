# Auditoría: Tags (acondicionamiento, calidad OPC, catálogo)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Documento canónico** | 02 / 10 |
| **Fecha de agrupación** | 2026-09-16 |
| **Fuentes absorbidas** | `AUDIT_SIGNAL_CONDITIONING`, `AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP`, `AUDIT_CATALOG_SQLITE_LOCAL`, `AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE` (+ JSON de planta) |
| **Complementa** | [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) |
| **Veredicto vigente** | Wavelet RT **A−** / nuclear **C** · OPC **A−** disponibilidad y calidad · catálogo local **A** código / sync planta **A−** · consistencia proceso **A** / sidecar **B−** |
| **Clasificación** | Auditoría de contraste código vs diseño. IDs de hallazgos conservados. |


Este archivo agrupa **todas** las auditorías del dominio. Cada parte conserva el texto original.

## Índice de partes

- [Parte A — Acondicionamiento de señal (wavelet RT / IAD)](#parte-a-acondicionamiento-de-señal-wavelet-rt-iad)
- [Parte B — Calidad OPC y arranque degradado](#parte-b-calidad-opc-y-arranque-degradado)
- [Parte C — Catálogo local SQLite](#parte-c-catálogo-local-sqlite)
- [Parte D — Consistencia de catálogo en planta (multi-edge)](#parte-d-consistencia-de-catálogo-en-planta-multi-edge)
- [Parte E — Dump JSON consistencia catálogo planta](#parte-e-dump-json-consistencia-catálogo-planta)

---

## Parte A — Acondicionamiento de señal (wavelet RT / IAD)

> Fuente original: `AUDIT_SIGNAL_CONDITIONING.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/Tags.tsx`) |
| **Alcance** | Filtro wavelet DWT en worker, deadband, calidad OPC en `.f`, IAD (outlier / out-of-range / frozen). CPU en hot path, fugas, idoneidad industrial |
| **Fuera de alcance** | `DedupeFilter` de logs, `filter_by` de API, Plotly, algoritmos LDS/PFM de iDetectFugas |
| **Fecha original** | 2026-08-16 |
| **Revisión wavelet** | 2026-08-19 — implementación `feature/wavelet-rt`: DWT por bloques en `WaveletWorker`, hot path O(1), tag derivado `.f`, sync a `sample_interval` SM |
| **Revisión A+** | 2026-08-19 — propagación calidad OPC al tag `.f`, eliminación definitiva de legado (`gaussian_filter*`, `process_filter`, Kalman), HMI observabilidad |
| **Controles ops** | 2026-08-25 — `POST /api/admin/tags/rebuild-derived` y métrica `DERIVED_TAGS_COUNT` en `/performance` |
| **Complementa** | [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_HMI.md](./AUDIT_HMI.md), [specs/08-WAVELET-RPA-RT.md](../specs/08-WAVELET-RPA-RT.md) |
| **Veredicto estático** | **A− (wavelet RT operativo)** / **C (nuclear/DCS)**. Pipeline wavelet completo: calidad OPC, deadband único, persistencia eager, API/HMI observabilidad, esquema BD limpio. Pendiente: IAD, soak 24 h, golden trace, integración SM en CI |
| **Clasificación** | Auditoría de acondicionamiento de señal |

---

### 0. Respuesta directa

| Palanca | ¿Runtime? | Qué es hoy |
|---|---|---|
| **Filtro wavelet (`filter_enabled`)** | **Sí** | DWT + soft-threshold + IDWT en `WaveletWorker`; hot path solo encola O(1). SM puede consumir raw o `.f` |
| **Calidad OPC en `.f`** | **Sí** | Muestra BAD/NaN → `HOLD` + publicación `UNCERTAIN` con último valor bueno; GOOD al recuperar señal |
| **Filtro gaussiano / Kalman** | **Eliminado** | Columnas BD, API, HMI, `filter.py`, `@filter` y páginas Dash retirados (2026-08-19) |
| **Filtro de proceso (`process_filter`)** | **Eliminado** | Columna SQL eliminada por migración idempotente `_drop_legacy_tag_columns()` |
| **Deadband** | **Sí** | Puerta única en `Tag.set_value`; CVT respeta `False` y no re-emite |
| **Outlier / OOR / frozen (IAD)** | **No en hot path** | Decoradores IAD **comentados**. Stubs sin enganche |

**Mensaje operativo:** el filtrado de señal para control de proceso es **wavelet RT** vía tag `{nombre}.f`. Raw permanece en el tag source. Cada máquina elige por suscripción (`signal_modes`: `raw` | `filtered`, default **filtrado**) qué valor consumir; el dropdown «Tags de Campo» lista solo el raw y lo oculta si ya está mapeado (raw o `.f`). Ante datos inválidos, el operador ve calidad **UNCERTAIN** en `.f` y estado **hold** en HMI/Performance. Admin/supervisor pueden **Reconstruir derivados** en `/performance` (`POST /api/admin/tags/rebuild-derived`): asegura `.f` si el filtro está ON y elimina `.f` cuyo source ya no existe.

Cadena con wavelet ON y SM suscrita (modo filtrado, default):

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

Con `signal_modes[source]=raw`, el worker sigue publicando `.f`, pero la SM lee el tag source.
---

### 1. Inventario de código (post-A+)

| Pieza | Archivo | Rol |
|---|---|---|
| Calidad OPC | `automation/signal_conditioning/quality.py` | `GOOD` / `UNCERTAIN` / `BAD`; helpers ingest |
| Anillo O(1) | `automation/signal_conditioning/sample_ring.py` | `SampleRing`: encolado thread-safe |
| DWT bloques | `automation/signal_conditioning/wavelet_block.py` | `WaveletBlockFilter`: DWT, HOLD, métricas status |
| Tags `.f` | `automation/signal_conditioning/filtered_tags.py` | `ensure_filtered_tag`, `resolve_subscription_tag`, `resolve_bind_tag` |
| Preferencia SM | `automation/state_machine.py` | `signal_modes`, `set_signal_mode`; HMI columna Señal en MachinesDetailed |
| Worker | `automation/workers/wavelet_worker.py` | Publicación con `quality` en `.f` |
| Hot path | `automation/tags/tag.py`, `automation/tags/cvt.py` | Deadband + ingest + `quality` en `set_value` |
| SM | `automation/state_machine.py` | `subscribe_to` → `.f` + registro worker |
| Persistencia / API | `dbmodels/tags.py`, `modules/tags/resources/tags.py` | Solo `filter_*`; migración + drop legacy |
| HMI | `WaveletFilterPanel.tsx`, `Tags.tsx`, `Performance.tsx` | Panel wavelet, badge calidad, widget filtros activos |
| Tests | `automation/tests/test_wavelet_filter.py` | 14 tests (calidad HOLD/OK, deadband, worker publish) |
| IAD | `automation/iad/*.py` | **no enganchado** |

**Eliminados:** `automation/tags/filter.py`, `automation/filter/__init__.py`, páginas Dash `/filter`, columnas `gaussian_filter*`, `process_filter`.

---

### 2. Filtro wavelet — diseño e idoneidad

#### 2.1. Decisiones de arquitectura (conformes a spec)

| Requisito | Estado |
|---|---|
| Hot path O(1), sin DWT en OPC | **Cumple** |
| Worker off-thread | **Cumple** |
| Alineación temporal SM | **Cumple** |
| Tag derivado trazable | **Cumple** — sufijo `.f` |
| Persistencia opcional / eager | **Cumple** — `filter_persist` + `_sync_wavelet_runtime` |
| Calidad OPC en `.f` | **Cumple** — HOLD + UNCERTAIN ante BAD/NaN |
| Coste acotado por publicación | **Cumple** |

#### 2.2. Semántica de calidad (operador)

| Condición ingest | Estado filtro | Calidad `.f` | Valor `.f` |
|---|---|---|---|
| Muestra GOOD, buffer en warmup | `warmup` | `UNCERTAIN` | Último raw / parcial |
| Muestra GOOD, buffer lleno | `ok` | `GOOD` | Valor DWT filtrado |
| Muestra BAD / NaN / inf | `hold` | `UNCERTAIN` | Último valor bueno conocido |
| Sin datos en anillo | `no_data` | — | Sin publicación |
| Error DWT irrecuperable | `failed` | — | Último resultado si existe |

El contador `bad_samples_dropped` (alias `drop_count`) y `last_publication_quality` se exponen en `GET /tags/{name}/filter/status`.

#### 2.3. Huecos respecto a grado industrial

| ID | Sev. | Hallazgo |
|---|---|---|
| **WF-2** | Media | Lazy register antes de suscripción SM |
| **WF-4** | Baja | Sin golden trace / bench p95 documentado |
| **WF-6** | Baja | Sin test integración SM + `.f` en CI |

---

### 3. Legado gaussiano / process_filter — eliminado

Migración `DBManager._drop_legacy_tag_columns()` elimina de forma idempotente: `gaussian_filter`, `gaussian_filter_threshold`, `gaussian_filter_r_value`, `process_filter`.

Modelo Peewee, API REST, CVT, Tag, HMI, audit trail y páginas Dash ya no referencian estos campos. **NF-7 ampliado: cerrado en todo el stack.**

---

### 4. IAD — sigue muerto en el hot path

Sin cambio. Decoradores comentados en `CVT.set_value`. Hallazgos **NF-IAD-1..4** vigentes si se reactiva sin refactor.

---

### 5. CPU / memoria

Hot path OPC: O(1) con wavelet ON. DWT solo en `WaveletWorker`. Deadband único (**NF-6 cerrado**).

---

### 6. ¿Grado nuclear / DCS?

| Dimensión | Nota |
|---|---|
| Wavelet RT (funcional) | **A−** — listo para producción operativa |
| Nuclear / DCS / SIL | **C** — IAD desconectado, soak/golden trace pendientes |

---

### 7. Hallazgos numerados (consolidado)

| ID | Sev. | Estado | Hallazgo |
|---|---|---|---|
| **NF-1** | Crítica | **Cerrado** | `process_filter` eliminado (código + BD) |
| **NF-2..NF-4** | Alta | **Cerrado** | Kalman / `@filter` eliminados del repo |
| **NF-6** | Media | **Cerrado** | Deadband único en `Tag.set_value` |
| **NF-7** | Media | **Cerrado** | Gaussiano eliminado de UI, API, BD, Dash |
| **NF-8** | Media | Abierto | IAD comentado |
| **WF-1** | Media | **Cerrado** | Calidad OPC propagada a `.f` + API + HMI |
| **WF-5** | Baja | **Cerrado** | Panel Wavelet RT + widget Performance |
| **OPS-F** | Baja | **Cerrado (código)** | Reconstruir `.f` huérfanos desde `/performance` (`rebuild_derived_tags`) |

---

### 8. Recomendaciones (priorizadas)

1. Soak RSS 24 h con wavelet ON (**CA-A+-06** / **CA-NF-2**).
2. Golden trace wavelet vs referencia offline (**CA-WF-1**).
3. Tests de integración SM → `.f` en CI (**WF-6**).
4. Propagar `quality` desde OPC UA subscription (hoy default GOOD en adquisición).

---

### 9. Certificación

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

### 10. HMI — configuración wavelet RT

#### 10.1. Ubicación

| Aspecto | Diseño |
|---|---|
| **Pantalla** | `hmi/src/pages/Tags.tsx` — modales Crear/Editar |
| **Componente** | `WaveletFilterPanel.tsx` — switch, badge estado, parámetros colapsables |
| **Solo tags fuente** | Controles ocultos en `*.f` |
| **Tipos** | Solo `data_type === 'float'` |

#### 10.2. Observabilidad en panel

| Elemento | Fuente |
|---|---|
| Badge estado | `GET /tags/{name}/filter/status` → `status` |
| Badge calidad `.f` | `last_publication_quality` (GOOD / UNCERTAIN) |
| Contador descartes | `bad_samples_dropped` |
| Tag derivado | `{nombre}.f` (solo lectura) |
| Latencia | `age_ms` |

#### 10.3. Widget Performance (`/performance`)

Tabla «Filtros wavelet activos»: source, `.f`, status, **calidad .f**, age, rate. Poll cada 5 s vía `GET /tags/filter/status`.

#### 10.4. Persistencia BD (`Tags`)

| Columna | Tipo | Default |
|---|---|---|
| `filter_enabled` | `BOOLEAN` | `false` |
| `filter_wavelet` | `VARCHAR(16)` | `'db4'` |
| `filter_level` | `INTEGER` | `4` |
| `filter_threshold_factor` | `FLOAT` | `3.0` |
| `filter_persist` | `BOOLEAN` | `false` |

**Columnas eliminadas:** `gaussian_filter`, `gaussian_filter_threshold`, `gaussian_filter_r_value`, `process_filter`.

#### 10.5. API filter status (respuesta ampliada)

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

#### 10.6. Claves i18n

| Clave | ES | EN |
|---|---|---|
| `tags.waveletFilter` | Filtro wavelet (tiempo real) | Wavelet filter (real-time) |
| `tags.waveletPublicationQuality` | Calidad .f | .f quality |
| `tags.waveletDropped` | Descartes | Dropped |
| `performance.waveletQuality` | Calidad .f | .f quality |

#### 10.7. Estado de implementación

| Capa | Estado |
|---|---|
| BD + migración `filter_*` + drop legacy | **Implementado** |
| Calidad OPC en `.f` + SAF journal | **Implementado** |
| API `/filter/status` ampliado | **Implementado** |
| HMI panel + Performance widget | **Implementado** |
| Tests unitarios calidad | **Implementado** (14 tests OK) |
| Rebuild bundle HMI en deploy | **Pendiente** operación |

---

### 11. Runbook operativo (calidad `.f`)

1. Si el operador ve **UNCERTAIN** en tendencia `.f` o badge **hold** en Tags/Performance → revisar calidad OPC del tag **source** (instrumento, cableado, servidor OPC).
2. El valor mostrado en `.f` durante hold es el **último valor bueno filtrado**, no el raw defectuoso.
3. Al recuperar muestras GOOD, el filtro reanuda automáticamente; puede haber 1–N ciclos de **warmup** antes de **ok**.
4. Consultas históricas: el journal SAF incluye campo `quality` cuando está disponible en el sample.


## Parte B — Calidad OPC y arranque degradado

> Fuente original: `AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Verificación de [specs/09-OPC-QUALITY-AND-DEGRADED-STARTUP.md](../specs/09-OPC-QUALITY-AND-DEGRADED-STARTUP.md) v1.0 (P0/P1) **y** [specs/10-OPC-QUALITY-A-PLUS.md](../specs/10-OPC-QUALITY-A-PLUS.md) v2.0 (A+) |
| **Fecha** | 2026-08-21 |
| **Evidencia** | Revisión estática del código + `automation/tests/test_opc_quality.py` — **19 OK / 3 skipped** (soak planta) |
| **Baseline** | Auditoría gap 2026-08-20 (mismo archivo, § histórico): **B− operativo / D calidad de señal** |
| **Complementa** | [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_DB.md](./AUDIT_DB.md), [docs/opc-quality-runbook.md](../docs/opc-quality-runbook.md) |
| **Normas de referencia** | OPC UA Part 4 (StatusCodes), ISA-18.2, IEC 61508 (SIL-ready, sin certificación), prácticas DCS (hold-last, inhibit, stale PV, degraded mode) |
| **Veredicto vigente** | **A− disponibilidad** · **A− calidad de señal** (A+ condicionado a soak 24 h) · **A Login / UX degradada** |
| **Clasificación** | Auditoría de verificación · calidad de señal · degradación segura |

---

### 0. Respuesta directa

| Escenario | ¿Qué hace PyAutomation **ahora** (2026-08-21)? | Spec | Grado nuclear / DCS |
|---|---|---|---|
| **Servidor OPC publica BAD / UNCERTAIN / NaN** | StatusCode → `Quality` (severity + substatus); hold-last en PV; gate de proceso; `ALM.QUALITY.*`; badge G/U/B + tooltip substatus | 09+10 | **A−** (A+ pendiente soak/SIL) |
| **Arranque / pérdida con OPC offline** | App no bloquea; `ALM.OPCUA.*`; reconnect; tags del cliente → **BAD/stale** sin pisar last-good; `ALM.QUALITY.*` | 09+10 | **A−** |
| **Arranque sin historiador** | App no bloquea; SAF; Login/Signup **503 + `event_id` visible** en HMI; banner «modo degradado» | 09+10 | **A** |
| **Operador cambia política UNCERTAIN** | Settings → checkbox; PUT `/settings/update`; caché hot path sin `json.load` | 10 | **A−** |

Cadena hot path **post-spec 10**:

```
OPC UA datachange (subscription.py)
  → SourceTimestamp + StatusCode
  → map_opc_status() → Quality(severity, opc_code, substatus)
  → cvt.set_value_fast(..., quality, opc_code, substatus)
  → Tag.set_value: Bad/NaN/Inf → hold-last + stale; GOOD → actualiza PV
  → QualityAlarmEngine → SYS.QUALITY.<tag> / ALM.QUALITY.<tag> (+ Event rate-limited)
  → Alarm.notify: gate BAD; UNCERTAIN vía get_inhibit_uncertain_quality() (caché)
  → serialize_socket { quality, quality_label, quality_substatus, stale, stale_age_ms }
  → HMI QualityBadge G/U/B* (+ substatus tooltip)
```

---

### 1. Matriz de criterios de aceptación (CA-OQ)

| ID | Criterio | Resultado | Evidencia primaria | Test |
|---|---|---|---|---|
| **CA-OQ-01** | `CVTEngine.set_value(..., quality=BAD)` persiste quality | **PASS** | `cvt.py` `set_value` → `set_value_fast` | `TestCVTQualityPropagation` |
| **CA-OQ-02** | StatusCode Bad → CVT quality ≠ GOOD | **PASS** | `subscription.py` `_extract_status_quality` + `datachange_notification` | `TestSubscriptionStatusCode` |
| **CA-OQ-03** | Bad/NaN/Inf no modifica PV raw; sí quality/stale | **PASS** | `tag.py` `set_value` hold-last | `TestHoldLast` |
| **CA-OQ-04** | `Alarm.notify` no evalúa setpoint en BAD | **PASS** | `alarms/__init__.py` `_quality_allows_process_evaluation` | `TestAlarmQualityGate` |
| **CA-OQ-05** | Disconnect OPC → tags BAD/stale sin pisar last-good | **PASS** | `models.py` + `cvt.mark_opcua_client_tags_stale` | `TestOpcDisconnectStale` |
| **CA-OQ-06** | HMI badge G/U/B + stale age (+ substatus) | **PASS** | `QualityBadge.tsx`, Tags, Alarms, StripChart | Revisión estática + suite |
| **CA-OQ-07** | Login 503 incluye `event_id` (API) | **PASS** | `users.py` + `db_audit.ensure_degraded_event_id` | `TestLoginEventId` |
| **CA-OQ-08** | Banner modo degradado si BD offline | **PASS** | `DegradedModeBanner.tsx` + `MainLayout.tsx` | Revisión estática HMI |
| **CA-OQ-09** | `ALM.QUALITY.<tag>` ON en BAD/stale, OFF en GOOD | **PASS** | `quality_gate.py` + `quality_alarms.py` + hook `Tag` | `TestQualityAlarmEngine` |
| **CA-OQ-10** | Login/Signup HMI muestra `event_id` | **PASS** | `Login.tsx` / `Signup.tsx` + `DatabaseConfigForm` | `TestHmiQualitySurfaces` |
| **CA-OQ-11** | Toggle UNCERTAIN en caliente (caché) | **PASS** | `set_inhibit_uncertain_quality` + `QualityPolicyPanel.tsx` | `TestInhibitUncertainCache` |
| **CA-OQ-12** | Trends históricos / DataLogger badge o «sin calidad» | **PASS** | `HistoricalQualityLegend.tsx` | `TestHmiQualitySurfaces` |
| **CA-OQ-13…15** | Soak 24 h planta | **PENDIENTE** | [opc-quality-runbook.md](../docs/opc-quality-runbook.md) § 4 | `TestSoakDocumented` (3 skip) |

**Suite:** `./venv/bin/python -m unittest automation.tests.test_opc_quality` — **22 tests: 19 OK, 3 skipped** (2026-08-21).

---

### 2. Inventario de código (evidencia)

#### 2.1 Mapeo StatusCode → Quality (borde OPC)

| Artefacto | Rol | Estado |
|---|---|---|
| `automation/signal_conditioning/quality.py` | `Quality` frozen; `map_opc_status`; `status_code_to_quality` (bits 30–31); `status_code_substatus`; caché inhibit | ✅ |
| `automation/opcua/subscription.py` | `_extract_status_quality` → `Quality`; `_quality_write_kwargs` propaga `opc_code`/`substatus` | ✅ |

```42:50:automation/signal_conditioning/quality.py
@dataclass(frozen=True)
class Quality:
    """Immutable quality snapshot at the OPC / CVT boundary."""

    severity: float = GOOD
    opc_code: int | None = None
    substatus: str | None = None
    stale: bool = False
    stale_age_ms: int | None = None
```

```153:159:automation/signal_conditioning/quality.py
def map_opc_status(status_code) -> Quality:
    """OPC-edge mapper: StatusCode → immutable Quality (severity + forensics)."""
    return Quality(
        severity=status_code_to_quality(status_code),
        opc_code=_status_int(status_code),
        substatus=status_code_substatus(status_code),
    )
```

```43:49:automation/opcua/subscription.py
def _extract_status_quality(data):
    """Pull StatusCode from a datachange notification payload → Quality."""
    try:
        status = data.monitored_item.Value.StatusCode
    except Exception:
        return map_opc_status(None)
    return map_opc_status(status)
```

```380:386:automation/opcua/subscription.py
    def datachange_notification(self, node, val, data):
        ...
        timestamp = data.monitored_item.Value.SourceTimestamp
        quality = _extract_status_quality(data)
        self.update_tag_value(node, val, timestamp, quality=quality)
```

El hot path del Tag sigue en **float** `1.0 / 0.5 / 0.0` (O(1), sin allocation extra en el camino GOOD).

#### 2.2 Propagación CVT (bug P0 cerrado + forense)

| Artefacto | Antes (2026-08-20) | Ahora |
|---|---|---|
| `CVTEngine.set_value` | Descartaba 4.º arg → siempre GOOD | Reenvía `quality`, `opc_code`, `substatus` |

```1247:1253:automation/tags/cvt.py
    def set_value(self, id:str, value, timestamp:datetime, quality:float=1.0, opc_code:int|None=None, substatus:str|None=None):
        r"""
        Tag value write. Acquisition uses the fast path; CRUD stays on __query.
        """
        return self.set_value_fast(
            id, value, timestamp, quality=quality, opc_code=opc_code, substatus=substatus
        )
```

Impacto colateral: publicación wavelet `.f` vía `app.cvt.set_value(..., quality=UNCERTAIN)` ya no pierde calidad ([AUDIT_TAGS.md](./AUDIT_TAGS.md)).

#### 2.3 Hold-last + stale + hook de calidad en Tag

| Comportamiento | Evidencia |
|---|---|
| Bad / NaN / Inf → no `value.set_value`; sí `quality`, `stale`, `stale_timestamp` | `tag.py` `set_value` |
| Persiste `opc_status_code` / `quality_substatus` | kwargs opcionales |
| Transición degraded → `notify_quality_transition` **fuera del lock** | `_notify_quality_engine` |
| Wire | `serialize` / `serialize_socket`: `quality`, `quality_label`, `quality_substatus`, `opc_status_code`, `stale`, `stale_age_ms` |

```351:358:automation/tags/tag.py
    def _notify_quality_engine(self, previous_degraded: bool, degraded: bool) -> None:
        if bool(previous_degraded) == bool(degraded):
            return
        try:
            from ..alarms.quality_gate import notify_quality_transition

            notify_quality_transition(self, degraded=bool(degraded))
```

#### 2.4 Gate ISA-18.2 en alarmas de proceso (caché, sin I/O)

```350:363:automation/alarms/__init__.py
    def _quality_allows_process_evaluation(self) -> bool:
        """Gate process setpoints on PV quality (ISA-18.2 inhibit on Bad)."""
        from ..signal_conditioning.quality import is_process_alarm_allowed
        ...
            from ..signal_conditioning.quality import get_inhibit_uncertain_quality

            inhibit_uncertain = bool(get_inhibit_uncertain_quality())
        ...
        return is_process_alarm_allowed(quality, inhibit_uncertain=inhibit_uncertain)
```

| Política | Default | Configurable |
|---|---|---|
| BAD | **Inhibe** setpoint | — |
| UNCERTAIN | **Permite** evaluación | `alarm_inhibit_uncertain_quality=true` (Settings UI + API) |
| GOOD | Evalúa | — |

El shelve timeout permanece **fuera** del gate (lifecycle ISA-18.2 intacto).

#### 2.5 `ALM.QUALITY.<tag>` (spec 10 / CA-OQ-09)

| Pieza | Ruta | Comportamiento |
|---|---|---|
| Engine | `automation/alarms/quality_gate.py` | Transición BAD/stale ↔ GOOD; `threading.local` anti-reentrada; Event rate-limited 5 s |
| BOOL ISA | `automation/utils/quality_alarms.py` | Lazy `SYS.QUALITY.<tag>` / `ALM.QUALITY.<tag>`; excluye `SYS.*`, `ALM.*`, `.f` |
| Fail-safe | Ambos | Nunca levantan excepción al hot path de adquisición |

```24:38:automation/alarms/quality_gate.py
def notify_quality_transition(tag, *, degraded: bool) -> None:
    """Drive ALM.QUALITY and a forensic Event. Never raises. Never re-enters."""
    if getattr(_tls, "active", False):
        return
    if tag is None or not is_quality_subject(tag):
        return
    _tls.active = True
    try:
        name = getattr(tag, "name", "") or ""
        set_quality_degraded(name, degraded)
        _emit_quality_event(tag, degraded=degraded)
    ...
```

Coexiste con `ALM.OPCUA.*` (enlace) y con setpoints de proceso (inhibidos, no sustituidos).

#### 2.6 Stale al disconnect OPC

`_sync_connection_alarm(True)` en connect-fail / disconnect / lost-link → `mark_opcua_client_tags_stale` escribe valor held con `quality=BAD` → hold-last garantiza el PV y dispara `ALM.QUALITY.*`.

#### 2.7 Login 503 + `event_id` visible (CA-OQ-07 / 10)

```18:25:automation/modules/users/resources/users.py
def _database_unavailable_payload(message: str, details: str) -> dict:
    event_id = database_connection_auditor.ensure_degraded_event_id()
    return {
        "message": message,
        "error_type": "database_connection_error",
        "details": details,
        "event_id": event_id,
    }
```

| Capa | Artefacto | Estado |
|---|---|---|
| API | `users.py` + `db_audit.ensure_degraded_event_id` | ✅ UUID hex estable por episodio |
| HMI Login | `Login.tsx` `extractBackendEventId` | ✅ |
| HMI Signup | `Signup.tsx` | ✅ |
| Formulario | `DatabaseConfigForm.tsx` prop `eventId` + alert | ✅ |
| i18n | `auth.databaseUnavailableWithEventId` ES/EN | ✅ |

#### 2.8 Settings — política UNCERTAIN (CA-OQ-11)

```93:99:automation/modules/settings/resources/settings.py
        if 'alarm_inhibit_uncertain_quality' in data:
            inhibit = bool(data['alarm_inhibit_uncertain_quality'])
            app.set_app_config(alarm_inhibit_uncertain_quality=inhibit)
            try:
                from ....signal_conditioning.quality import set_inhibit_uncertain_quality

                set_inhibit_uncertain_quality(inhibit)
```

| Capa | Artefacto |
|---|---|
| API | PUT `/settings/update` campo `alarm_inhibit_uncertain_quality` |
| Caché | `set_inhibit_uncertain_quality` / `get_inhibit_uncertain_quality` |
| HMI | `QualityPolicyPanel.tsx` en Settings (capítulo `settings-quality`) |

#### 2.9 HMI — superficies de calidad

| Superficie | Artefacto | Comportamiento |
|---|---|---|
| Tags | `Tags.tsx` + `QualityBadge` | Badge + tooltip substatus / stale age |
| Alarmas | `AlarmTableRow.tsx` | Badge sobre valor del tag |
| Trends RT | `StripChart.tsx` | Badge por tag + substatus |
| Trends históricos | `Trends.tsx` + `HistoricalQualityLegend` | Live G/U/B o «N/A» |
| DataLogger | `DataLogger.tsx` + misma leyenda | Idem |
| Modo degradado | `DegradedModeBanner.tsx` en `MainLayout` | Visible si BD offline |
| Settings | `QualityPolicyPanel.tsx` | Toggle UNCERTAIN en caliente |

---

### 3. Contraste baseline → post-spec 09 → post-spec 10

| Requisito DCS / spec | Baseline 2026-08-20 | Post-09 | Post-10 (ahora) |
|---|---|---|---|
| StatusCode → quality CVT | No | Sí (severidad) | **Sí + substatus / opc_code** |
| Hold-last PV raw | No (solo `.f`) | Sí | Sí |
| Inhibit alarmas proceso en Bad | No | Sí | Sí (caché, no JSON) |
| Toggle UNCERTAIN en Settings | No | Solo config archivo | **UI + API en caliente** |
| Disconnect → Bad/stale | Solo BOOL enlace | BOOL + PVs | + `ALM.QUALITY.*` |
| Badge HMI G/U/B | No | Tags/Alarms/StripChart | **+ Trends históricos / DataLogger** |
| Login `event_id` | No | Solo API | **Visible al operador** |
| Banner degradado | Overlay parcial | Persistente | Persistente |
| `ALM.QUALITY.<tag>` | No | Residual OQ-R1 | **Implementado** |
| Certificación SIL / soak 24 h | Fuera / no | Fuera / no | Procedimiento documentado; **runtime pendiente** |

---

### 4. Disponibilidad (no regresiones)

| Capacidad previa (A−) | ¿Intacta? | Notas |
|---|---|---|
| Arranque no bloqueante OPC down | **Sí** | Stale mark fail-safe |
| Reconnect `LoggerWorker` + re-subscribe | **Sí** | GOOD limpia stale y `ALM.QUALITY.*` |
| Arranque BD down + SAF | **Sí** | Sin cambios en journal/replicator |
| Alarmas BOOL `ALM.OPCUA.*` / `ALM.DB.Connection` | **Sí** | Coexisten con `ALM.QUALITY.*` |
| Hot path sin I/O de config | **Sí** | `get_inhibit_uncertain_quality()` O(1) tras primer load |

---

### 5. Tests y cobertura

| Suite | Cobertura vs CA | Resultado (2026-08-21) |
|---|---|---|
| `automation/tests/test_opc_quality.py` | CA-OQ-01…12 + helpers; 13–15 documentados/skipped | **19 OK, 3 skipped** |
| `TestQualityAlarmEngine` | CA-OQ-09 (subject filter + ON/OFF) | OK |
| `TestInhibitUncertainCache` | CA-OQ-11 | OK |
| `TestHmiQualitySurfaces` | CA-OQ-10, 12 (artefactos HMI) | OK |
| `TestSoakDocumented` | CA-OQ-13…15 runbook + skip runtime | 1 OK + 3 skip |
| Wavelet hold-last BAD | Alineado a calidad BAD (no UNCERTAIN forzado) | OK (suite wavelet) |

Pendiente de formalizar (bloquea **A+**, no **A−**):

- Soak planta 24 h según [opc-quality-runbook.md](../docs/opc-quality-runbook.md) § 4.
- E2E browser de badge/banner (hoy revisión estática + asserts de archivos HMI).
- Persistencia de quality por muestra en historiador (fuera de alcance spec 10; badge histórico usa live CVT).

---

### 6. Hallazgos residuales (priorizados)

| ID | Severidad | Hallazgo | Estado |
|---|---|---|---|
| **OQ-R1** | — | `ALM.QUALITY.<tag>` | **Cerrado** — `quality_gate.py` + `quality_alarms.py` |
| **OQ-R2** | — | Toggle UNCERTAIN en Settings | **Cerrado** — `QualityPolicyPanel` + caché |
| **OQ-R3** | — | Login HMI sin `event_id` | **Cerrado** — form + toast |
| **OQ-R4** | — | Trends históricos sin badge | **Cerrado** — `HistoricalQualityLegend` |
| **OQ-R5** | Info | Subcódigo Part 4 | **Cerrado en wire/tooltip**; no se historifica por muestra |
| **OQ-R6** | Info | Sin V&V / IAD / certificación SIL | Fuera de alcance |
| **OQ-R7** | Medio (V&V) | Soak 24 h CA-OQ-13…15 no ejecutado en planta | Procedimiento listo; bloquea veredicto **A+** |

---

### 7. Veredicto

| Dimensión | Baseline | Meta 09 | Meta 10 | **Veredicto 2026-08-21** |
|---|---|---|---|---|
| Disponibilidad (arranque / reconnect / SAF) | **A−** | Mantener | Mantener | **A−** |
| Calidad de señal (StatusCode → CVT → alarmas → HMI) | **D** | **B+ / A−** | **A− / A+** | **A−** (`ALM.QUALITY.*` + Settings + substatus; **A+** bloqueado por soak) |
| Trazabilidad Login / modo degradado UX | **B** | **A−** | **A** | **A** (`event_id` visible) |

**Conclusión:** las specs 09 y 10 están cerradas en código con evidencia unitaria y estática. El producto ya no engaña al operador con GOOD aparente: hold-last, inhibit, `ALM.QUALITY.*`, badge en RT e histórico, y correlación Login↔Events. El salto a **A+** en calidad de señal requiere completar el soak 24 h (CA-OQ-13…15).

---

### 8. Histórico

#### 8.1 Gap analysis 2026-08-20 (obsoleto)

StatusCode ignorado, `CVTEngine.set_value` descartando quality, ausencia de hold-last en raw, alarmas sin gate, PVs no stale al disconnect OPC, Login 503 sin correlation id, ausencia de banner degradado.

**Cadena pre-fix (obsoleta):**

```
OPC datachange → (NO StatusCode) → set_value_fast(quality=GOOD) → Alarm.notify sin gate
```

#### 8.2 Verificación post-spec 09 (misma fecha, supersedida por §0–7)

Cerró CA-OQ-01…08 con veredicto **B+ calidad / A− Login**. Residuales OQ-R1…R4 motivaron la spec 10; quedan cerrados en esta revisión.


## Parte C — Catálogo local SQLite

> Fuente original: `AUDIT_CATALOG_SQLITE_LOCAL.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Verificación de [specs/11-CATALOG-SQLITE-LOCAL.md](../specs/11-CATALOG-SQLITE-LOCAL.md) v1.3 + **paridad CRUD offline** + **integridad P0 units/tags al reinicio** (2026-08-21) |
| **Fecha** | 2026-08-21 (rev. integridad P0) · **aislamiento Bulkhead 2026-08-25** (sync por fila, sin rollback de tabla) · **controles `/performance` 2026-08-25** · **planta 2-edge 2026-08-25** ([AUDIT_TAGS.md](./AUDIT_TAGS.md)) |
| **Evidencia** | Revisión estática + `automation.tests.test_catalog_sqlite` — **31 OK / 2 skipped** (soak planta) · PR [#16](https://github.com/know-ai/PyAutomation/pull/16) |
| **Baseline** | Spec 11 «propuesta»; historiador Peewee único; sin espejo de catálogo; SQLite configurable como motor central en HMI |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_TAGS.md](./AUDIT_TAGS.md), [docs/catalog-sqlite.md](../docs/catalog-sqlite.md), [docs/catalog-sqlite-runbook.md](../docs/catalog-sqlite-runbook.md) |
| **Normas de referencia** | ISA-95 · ISA-18.2 · IEC 61508 (SIL-ready, sin certificación) · IEC 62443 |
| **Veredicto vigente** | **A autonomía de catálogo (CRUD offline)** · **A separación SAF/historiador** · **A integridad units/tags al reinicio (código)** · **A aislamiento de filas (Bulkhead, código)** · **A prevención binds cruzados (CA-CODE-01…05)** · **A DAQ por área (CA-DAQ-01)** · **A opcuaserver push-only (CA-OPC-PUSH-01)** · **C datos de partición tagsmachines en planta** (CA-CODE-06 pendiente de wipe+redeploy) · **A− sync planta** · **A HMI/API (sin SQLite central)** |
| **Clasificación** | Auditoría de verificación · catálogo edge · modo degradado · sync bidireccional · paridad offline · no-regresión de metadatos |

---

### 0. Respuesta directa

| Escenario | ¿Qué hace PyAutomation **ahora** (2026-08-21 P0)? | Spec | Grado |
|---|---|---|---|
| **Arranque sin PG/MySQL** | Abre siempre `./db/catalog.db`; seed frío **solo si** `units`/`datatypes`/`roles` están vacías; hidrata CVT/roles/users/OPC/alarmas/máquinas desde local **sin pisar** unidades existentes | 11 | **A** |
| **CRUD de catálogo sin PG** | Crear/editar/borrar tags, alarmas, users/roles/password, OPC clients/server, máquinas + `tagsmachines`, LRS, nodes → `catalog.db` + versiones dirty | 11 | **A** |
| **Historiador caído en runtime** | `CATALOG_SOURCE=local`; banner HMI; login/signup contra espejo; mutaciones locales; replicator espera 30 s | 11 | **A** |
| **Reconexión** | `CatalogReplicatorWorker` push→pull orden FK; **remoto SoT si espejo limpio**; solo filas `dirty` offline compiten por timestamp; dual-write online; connect/reconnect `cycle(force=True)` | 11 | **A** (código) / **A−** (planta) |
| **Reinicio × N (idempotencia)** | Seed no muta maestros poblados; upserts de tags no blanquean `unit_id`; dump de `tags` estable entre reinicios (CA planta) | 11 + P0 | **A** (código) |
| **Operador elige SQLite como historiador** | **Rechazado** (HMI sin opción; API 400) | 11 CA-11 | **A** |
| **Journal SAF** | Intacta `./db/saf/.../journal.db`; **no** se mezcla con `catalog.db`; TagObservers se adjuntan sin PG | 11 + SAF | **A** |
| **Proxy Peewee historiador** | **No se rebindéa**; segundo `catalog_proxy` solo para el espejo | 11 + AUDIT_DB | **A** |

Cadena de arranque / sync:

```
__start_workers
  → bootstrap_local_catalog()          # siempre, WAL + FK
  → connect_to_db()                    # PG/MySQL; puede fallar
  → [si remoto down] seed_local_catalog_defaults  # units/datatypes/roles solo si vacías
       + hydrate local
  → start_catalog_replicator()         # hilo OS, interval 30 s, startup_grace 15 s
       → si is_db_connected y fuera de gracia (o force=True):
            push dirty (padres→hijos) → pull → conflictos dirty/timestamp → Event
       → si no: sleep 30 s + ALM.CATALOG.LocalOnly (>1 h)
```

Mutaciones offline (capa única):

```
API / HMI / core / loggers
  → CVT / managers (memoria)
  → catalog.mutations.*  |  catalog.seed.persist_*_to_local  |  write_catalog_row
  → LocalCatalogProvider.upsert/delete + catalog_versions (conflict_resolved=False = dirty)
  → [al reconectar] CatalogReplicatorWorker push dirty / pull remoto si limpio
```

---

### Roles de las bases de datos SQLite (G-DISK-06)

| Base de datos | Propósito | `synchronous` | `temp_store` | Durabilidad |
|---|---|---|---|---|
| `journal.db` (`./db/saf/<node_id>/`) | Outbox SAF de muestras, alarmas, eventos, logs | **FULL** | MEMORY | Crítica (Plan A local) |
| `catalog.db` (`./db/catalog.db`) | Espejo de configuración, usuarios, OPC, máquinas | **NORMAL** (1) | MEMORY | No crítica; se reconstruye desde el historiador o seed |

El historiador remoto (PostgreSQL) **nunca** se sustituye por SQLite. Ver [AUDIT_DB.md](./AUDIT_DB.md).

---

| ID | Criterio | Resultado | Evidencia primaria | Test |
|---|---|---|---|---|
| **CA-CATALOG-01** | Edge opera sin PG/MySQL (catálogo local) | **PASS** | Bootstrap + seed frío condicional + hydrate + CRUD offline | `TestColdStartLocalSeed`, roundtrip |
| **CA-CATALOG-02** | Cambios degradados se push-ean al reconectar | **PASS** (diseño) | Dual-write + dirty local + `CatalogReplicatorWorker._sync_table` push | Unitario parcial; planta pending |
| **CA-CATALOG-03** | Cambios central → edge en pull | **PASS** (diseño) | Pull en replicator; limpio → remoto siempre | Unitario conflictos dirty |
| **CA-CATALOG-04** | Conflictos: dirty+timestamp; limpio → remoto; Events | **PASS** | `conflict.resolve(..., local_dirty=)`; `persist_system_event` | `TestConflictResolver` |
| **CA-CATALOG-05** | Banner modo degradado / catálogo local | **PASS** | `DegradedModeBanner` + i18n ES/EN | `TestHmiCatalogSurfaces` |
| **CA-CATALOG-06** | Login local en degradado | **PASS** | `catalog.auth.login_local` + `core.login` fallback | `test_login_local_catalog` |
| **CA-CATALOG-07** | Sync no degrada p95 `set_value` | **PENDIENTE** | Runbook §5 | `@skip` soak |
| **CA-CATALOG-08** | `catalog.db` ≤ 500 MB | **PENDIENTE** | Runbook §5 | Planta |
| **CA-CATALOG-09** | Rollback remoto-only sin pérdida | **PENDIENTE** | Runbook §5 | Planta |
| **CA-CATALOG-10** | Alarmas/eventos de sync | **PASS** (código) | `catalog/alarms.py` + Events en ciclo | Revisión estática |
| **CA-CATALOG-11** | SQLite fuera del historiador HMI/API | **PASS** | Forms + `database.py` 400 | HMI estático + `TestApiSqliteRejected` |
| **CA-CATALOG-12** | Orden FK + tablas §4.1 | **PASS** | `schema.SYNC_ORDER`; `hmi_sessions` sin filas | `TestSchemaOrder` |
| **CA-CATALOG-13** | Integridad referencial post-sync | **PASS** (diseño) | Orden padres→hijos; clones locales; parents en mutaciones | `test_offline_catalog_mutations_parity` |
| **CA-CATALOG-14** | Multi-edge offline, central arbitra | **PENDIENTE** | Runbook §5 | `@skip` soak |
| **CA-CATALOG-15** | Paridad CRUD offline ≡ online (tablas de catálogo) | **PASS** (código) | `catalog/mutations.py` + enganches core/loggers | `test_offline_catalog_mutations_parity` + OPC/role |
| **CA-CATALOG-16** *(nuevo P0)* | Seed no sobrescribe units/datatypes/roles poblados | **PASS** | `seed_*` early-return si `count()>0` | `test_seed_does_not_overwrite_existing_units` |
| **CA-CATALOG-17** *(nuevo P0)* | Tag upsert no blanquea `unit_id` con NULL/0 | **PASS** | `rows._resolve_tag_unit_fks` + `_update_instance` | `test_tag_upsert_does_not_blank_unit_fk` |
| **CA-CATALOG-18** *(nuevo P0)* | Startup grace 15 s en replicator de fondo | **PASS** | `CatalogReplicatorWorker._startup_grace_s`; `force=True` en connect | `TestReplicatorStartupGrace` |
| **CA-ISOLATION-02** | Fila huérfana / `IntegrityError` no impide sync de hermanas ni de otras tablas | **PASS** (código) | `_sync_table`: `atomic()` **por fila**; error de tabla no revierte las demás | `test_integrity_error_continues_and_does_not_latch_sync_failed`; `test_mid_pull_error_isolates_other_tables` |
| **CA-ISOLATION-03** | `DataLogger.set_tag` `IntegrityError` no detiene el resto del lote | **PASS** | Warning + `return None`; no relanza | `test_set_tag_integrity_error_does_not_raise_and_allows_next_tag` |
| **CA-ISOLATION-04** | `MachinesLogger.bind_tag` FK missing no detiene otros binds | **PASS** | Warning + `return None`; no relanza | `test_bind_tag_integrity_error_does_not_raise_and_allows_next_bind` |
| **CA-OPS-01/03** *(dashboard)* | Sync forzada y limpieza de huérfanos desde `/performance` | **PASS** (código) | `POST /api/admin/catalog/sync` y `/clean-orphans`; `drop_orphans_older_than` | `test_ops_controls.py`; HMI planta pendiente |

**Suite:** `python3 -m unittest automation.tests.test_catalog_sqlite -v` — **31 tests: 31 OK, 2 skipped** (2026-08-21 P0).

---

### 2. Inventario de código (evidencia)

#### 2.1 Paquete `automation/catalog/`

| Módulo | Rol | Estado |
|---|---|---|
| `schema.py` | Registro ordenado 19 tablas; `REPLICATED_TABLES` (18); skip filas `hmi_sessions` | ✅ |
| `local_db.py` | `SqliteDatabase` + `catalog_proxy`; WAL; FK | ✅ |
| `models.py` | Clones Peewee; FK → columnas escalares; `CatalogVersionsLocal` | ✅ |
| `rows.py` | `row_to_raw` / `apply_raw` / `upsert_model`; prioriza `column_name`; coerce ISO→datetime; **`_resolve_tag_unit_fks`**; **no blanquear FK unit**; no reasignar `variable_id` de units existentes | ✅ |
| `versions.py` / `dbmodels/catalog_versions.py` | Sidecar local + historiador; `conflict_resolved=False` = **dirty** offline | ✅ |
| `provider.py` | `get_active()` = remoto si `is_db_connected()` else local | ✅ |
| `local_provider.py` / `remote_provider.py` | CRUD dict por tabla | ✅ |
| `conflict.py` | **Limpio → remoto**; dirty + timestamp; empate → remoto | ✅ |
| `replicator.py` | `BaseWorker` OS thread; batch 200; interval 30 s; **`startup_grace_s=15`**; `cycle(force=)`; **`_sync_table` transacción por fila**; `drop_orphans_older_than` (ops) | ✅ |
| `hydrate.py` / `auth.py` | Hidratación CVT/users/OPC/alarmas; login local; skip tags `active=False` y alarmas OOS | ✅ |
| `bootstrap.py` | `bootstrap_local_catalog`, `mirror_historian_row`, `write_catalog_row` | ✅ |
| `seed.py` | Seed frío **vacío-only** para units/datatypes/roles; `ensure_unit_symbol`; `persist_*` (merge OPC) | ✅ |
| **`mutations.py`** | **Capa única de mutaciones offline**: soft-delete tags/alarmas, tagsmachines, LRS, OPC UA server, machine fields, parents | ✅ |
| `alarms.py` | `ALM.CATALOG.SyncFailed` / `Conflict` / `LocalOnly` | ✅ |
| `metrics.py` | Snapshot O(1) `CATALOG_*` | ✅ |

#### 2.2 Enganches de producto (CRUD offline)

| Acción | Offline | Dual-write online | Evidencia |
|---|---|---|---|
| Tag create / update | `persist_tag_to_local` | `mirror_historian_row` / update mirror | `core.create_tag` / `update_tag` |
| Tag delete | `soft_deactivate_tag_local` (`active=False`) | logger + local | `core.delete_tag` |
| Alarm create / update / delete | `persist_alarm_*` / soft OOS | mirror + local | `core` + `logger/alarms.py` |
| User signup / role / password | `write_catalog_row` / upsert users | dual-write password/role | `core.signup` / `update_user_role` / `change_password` |
| Role create | `write_catalog_row("roles")` | sí | `core.set_role` |
| OPC UA client add/update/remove | siempre local | `OPCUA.create` + local | `managers/opcua_client.py` |
| OPC UA server + accesstype | `persist_opcua_server_local` | mirror | `logger/opcua_server.py` |
| Machine create / put attrs | `persist_machine_*` | mirror | `state_machine` / `logger/machines.py` / API machines |
| `tagsmachines` bind/unbind/override | mutations | mirror | `logger/machines.py` |
| LRS CRUD / import / interpolate | mutations (sin gate PG) | mirror en create/update online | `core.*linear_referencing*` |
| Nodes register | upsert `nodes` aunque falle historiador | — | `core._register_node` |
| Filtered `.f` tags | `persist_tag_to_local` si `filter_persist` | historian set_tag | `filtered_tags.py` |
| SAF TagObserver | `db_manager.attach` **siempre** (no gated a PG) | — | `create_tag` / machine persist |
| Catalog sync on connect | `cycle(force=True)` antes de hydrate | — | `core._sync_catalog_with_historian` |

#### 2.3 Tres SQLite — separación obligatoria

| Archivo | Motor | Propósito | ¿En HMI? |
|---|---|---|---|
| `./db/catalog.db` | Peewee `catalog_proxy` | Espejo de configuración | No |
| `./db/saf/<node>/journal.db` | `sqlite3` nativo SAF | Históricos store-and-forward | No |
| Historiador central | Peewee `proxy` → PG/MySQL | TagValue, Events, Logs, catálogo remoto | Sí |

**Invariante auditada:** el handle Peewee del historiador **no** se rebindéa a SQLite en runtime (rompe SAF / LoggerWorker). El espejo es un segundo database.

#### 2.4 Superficie HMI correctamente gated (no catálogo)

| Ruta / feature | Comportamiento sin PG |
|---|---|
| Trends / datalogger / alarm summary / events / operational logs | Overlay `REMOTE_DB_DEPENDENT_PATHS` — **correcto** (series temporales) |
| Tags config, users, OPC clients, machines | **Operables** offline vía espejo |
| User management | Fuera de `dbDependentRoutes`; listado hidrata desde local |

---

### 3. Hallazgos

#### Fortalezas

1. Arquitectura alineada con AUDIT_DB: segundo proxy, no rebind.
2. Fall-safe: mirror/write/mutations nunca levantan excepciones al hot path de adquisición.
3. Política de conflictos industrial: **remoto SoT** salvo dirty offline; auditable vía Events.
4. Superficie HMI limpia: SQLite ya no se presenta como historiador.
5. **Paridad CRUD offline** centralizada en `catalog/mutations.py` + seed helpers.
6. Cobertura unitaria: cold-start, OPC mapping, role_id, mutaciones, **seed no-overwrite**, **FK unit**, **grace**, dirty conflict.
7. Seed frío: edge vacío sin PG arranca con roles/units/datatypes/system user; edge poblado **no** se re-siembra.

#### Defectos corregidos

| ID | Defecto | Causa raíz | Fix | Fecha |
|---|---|---|---|---|
| **CAT-BUG-01** | Rol de usuario (p. ej. GUEST→ADMIN) no sobrevivía reinicio offline | `apply_raw` prefería campo Peewee `role` (stale) sobre columna `role_id` | `rows._pick_raw_value` prioriza `column_name`; `update_user_role` escribe ambos | 2026-08-21 |
| **CAT-BUG-02** | Mapeo OPC de tags (p. ej. PI_02) se perdía al reiniciar | `update_tag` offline no persistía; re-seed de máquina podía vaciar OPC | `persist_tag_to_local` en update + merge OPC si payload vacío | 2026-08-21 |
| **CAT-BUG-03** | Cliente OPC no quedaba en tabla `opcua` sin PG | Persist solo si `logger.get_db()` | `_persist_opcua_client_local` siempre | 2026-08-21 |
| **CAT-BUG-04** | Upsert de filas con `timestamp` ISO fallaba en silencio | `TimestampField` no acepta `str` | coerce ISO→`datetime` en `rows._coerce` | 2026-08-21 |
| **CAT-BUG-05** | Deletes/updates de alarmas/tags/máquinas/LRS no tocaban espejo | Gates `is_db_connected` sin rama local | `mutations.py` + enganches | 2026-08-21 |
| **CAT-BUG-06** | **P0:** `unit_id` / metadatos de tags mutaban a defaults al reiniciar (bar→None / planta limpia) | **A+C+D:** seed podía upsert maestros; conflicto newest-wins empujaba espejo limpio; upsert aceptaba `unit` NULL/0 o string sin resolver | Seed vacío-only; `local_dirty` en `conflict.resolve`; `_resolve_tag_unit_fks` + no blank FK; grace 15 s | 2026-08-21 P0 |

#### Investigación forense CAT-BUG-06 (hipótesis)

| Hipótesis | Veredicto | Evidencia / remedio |
|---|---|---|
| **A — Seed intrusivo** | **Confirmada (riesgo)** | `seed_variables_and_units` / datatypes / roles ahora **return 0** si la tabla tiene filas; alarmtypes/states siguen upsert seguros |
| **B — Provider/hydrate race** | **Mitigada** | `startup_grace_s=15` en bucle de fondo; connect/reconnect `cycle(force=True)` tras DB live |
| **C — Timestamp / clock skew** | **Confirmada** | Espejo limpio (`conflict_resolved=True` o no dirty) **siempre cede al remoto**; solo dirty+versión mayor gana local |
| **D — FK unit string→id** | **Confirmada** | `_resolve_tag_unit_fks` + `ensure_unit_symbol`; `_update_instance` ignora NULL/0 en FK de tags; no reasigna `variable_id` de units |

#### Gaps / riesgos residuales

| ID | Hallazgo | Severidad | Mitigación |
|---|---|---|---|
| **CAT-R1** | Recursos Peewee residuales fuera de funnels principales podrían atrasar espejo hasta el pull | Baja | Mutations + dual-write en funnels; inventario residual menor |
| **CAT-R2** | Soak 24 h / tamaño / multi-edge no ejecutados | Alta (para A+) | Runbook §5; tests `@skip` |
| **CAT-R3** | Banner usa `connected === false`, no lee `CATALOG_SOURCE` del health system | Baja | Texto i18n ya habla de catálogo local; mejora opcional |
| **CAT-R4** | Primer arranque frío: seed defaults + vacío de tags de proceso hasta que la app/plant los cree | Info | Esperado; seed + `persist_*` al crear máquinas/tags |
| **CAT-R5** | Históricos (TagValue / AlarmSummary / Events) **no** son catálogo — siguen requiriendo PG o SAF | Info | Fuera de alcance spec 11 |
| **CAT-R6** | CA planta P0 (10 reinicios / conflicto alfa-beta en vivo) aún no firmados en iDetectFugas | Media | Checklist §6; wheel desde `fix/catalog-integrity-p0` / PR #16 |
| **CAT-R7** | Identidad natural de `units` sigue siendo `(unit, name)` sin `variable` — colisión cross-variable posible en sync | Baja | Mitigado: no reasignar `variable_id` en update; evolución futura de identity key |
| **CAT-R8** | `atomic()` por fila es más commits SQLite que un wrap de tabla | Baja | Filas/ciclo = cambios recientes; CA-ISOLATION-05 (Txn/min) es soak de planta |

---

### 4. Matriz de paridad offline (tablas §4.1)

| Tabla | Create | Update | Delete / soft | Hydrate | Sync push |
|---|---|---|---|---|---|
| datatypes / variables / units / roles | seed **solo si vacía** | no vía seed | — | sí | sí (dirty) |
| alarmtypes / alarmstates | seed upsert seguro | — | — | sí | sí |
| manufacturer / segment / accesstype | ensure en mutaciones | — | — | vía FK | sí |
| users | signup offline | role / password | N/A producto | sí | sí |
| tags | sí | sí (FK unit seguro) | soft `active=False` | skip inactive | dirty |
| alarms | sí | sí | soft OOS | skip OOS | dirty |
| opcua | sí | sí | hard local | sí | dirty |
| opcuaserver | sí (local) | access_type | — | **push-only** al remoto; **nunca pull** | dirty local |
| nodes | register local | — | — | — | dirty |
| machines | sí | attrs | — | payloads | dirty |
| tagsmachines | bind | sample_override | unbind | (runtime) | dirty |
| linearreferencinggeospatial | sí | sí | hard | list/interpolate | dirty |
| hmi_sessions | local only | — | — | — | **no** (by design) |

---

### 5. Veredicto

| Dimensión | Nota | Condición A+ |
|---|---|---|
| Autonomía de catálogo (arranque + login + **CRUD offline**) | **A** | Soak CA-01 en planta con catálogo poblado y mutaciones reales |
| Integridad metadatos al reinicio (units/tags/OPC) | **A** (código) | Firmar CA planta §6 (10 reinicios + offline baz) |
| Sync bidireccional / conflictos | **A** (código) / **A−** (planta) | Soak CA-02/03/04/14 |
| Aislamiento de fallos (fila huérfana / FK) | **A** (código) | CA-ISOLATION-02…04 unitarios; soak Txn/min CA-ISOLATION-05 |
| Separación SAF / historiador / espejo | **A** | — |
| HMI + API sin SQLite central | **A** | — |
| Observabilidad (`CATALOG_*`, `ALM.CATALOG.*`) | **A−** | Validar alarmas en soak |

**Veredicto global:** **A** en autonomía e integridad de configuración edge en código; **A−** global solo por soak de planta pendiente (CA-07…09, 14 + CA planta P0). El bloqueo «units/tags vuelven a default al reinicio» queda **cerrado en código** (CAT-BUG-06 / PR #16).

---

### 6. Cómo reproducir evidencia

```bash
cd github/PyAutomation
PYTHONPATH=. python3 -m unittest automation.tests.test_catalog_sqlite -v
# Esperado: Ran 31 tests … OK (skipped=2)
```

Tests clave de esta revisión (P0):

- `TestColdStartLocalSeed.test_seed_defaults_and_system_user`
- `TestColdStartLocalSeed.test_seed_does_not_overwrite_existing_units`
- `TestColdStartLocalSeed.test_tag_upsert_does_not_blank_unit_fk`
- `TestColdStartLocalSeed.test_persist_opcua_client_and_preserve_tag_opc_mapping`
- `TestColdStartLocalSeed.test_user_role_update_prefers_role_id_column`
- `TestColdStartLocalSeed.test_offline_catalog_mutations_parity`
- `TestConflictResolver.test_clean_local_defers_to_remote_even_if_newer`
- `TestConflictResolver.test_dirty_newer_local_wins`
- `TestReplicatorStartupGrace.test_cycle_skips_during_grace_unless_forced`
- `TestReplicatorScopeAndIntegrity.test_integrity_error_continues_and_does_not_latch_sync_failed` (CA-ISOLATION-02)
- `TestCatalogSyncNuclear.test_mid_pull_error_isolates_other_tables`
- `TestHmiCatalogSurfaces.test_user_management_not_remote_db_gated`

#### Checklist CA planta (integridad P0)

1. **Offline bar→baz:** apagar PG; cambiar unidad de un tag a `baz`; reiniciar servicio sin remoto → tag sigue en `baz`.
2. **Online estable:** PG con `baz`; reiniciar → sin mutación; logs sin merges anómalos.
3. **Conflicto dirty:** offline `alfa` vs remoto `beta` → gana dirty/timestamp; otras filas intactas.
4. **Idempotencia:** 10 reinicios con/sin remoto → dump de `tags` idéntico.

Documentación de producto: [docs/catalog-sqlite.md](../docs/catalog-sqlite.md).  
Operación: [docs/catalog-sqlite-runbook.md](../docs/catalog-sqlite-runbook.md).  
Controles en caliente (forzar sync / limpiar huérfanos): [docs/node-performance-runbook.md](../docs/node-performance-runbook.md) y vista `/performance`.  
PR: [know-ai/PyAutomation#16](https://github.com/know-ai/PyAutomation/pull/16).


## Parte D — Consistencia de catálogo en planta (multi-edge)

> Fuente original: `AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/catalog`) + historiador PostgreSQL + `catalog.db` por edge |
| **Alcance** | Integridad referencial y partición de `tags`, `machines`, `tagsmachines`, `alarms`, `opcua`, `pending_rows` |
| **Fecha de ejecución** | 2026-08-25 19:15–19:20 UTC |
| **Entorno** | Planta Supe · 2 edges reales · historiador compartido `idetect_db` @ `192.168.1.95:5432` |
| **JSON crudo** | [AUDIT_TAGS.md](./AUDIT_TAGS.md) |
| **Complementa** | [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) |
| **Veredicto de esta corrida** | FK nulas/huérfanas **A** (0 filas). Partición `tagsmachines` **C**. Catálogo local Linea2 **B−**. **No es A+ de planta.** |
| **Clasificación** | Auditoría de datos · evidencia de planta · no es spec |

---

### 0. Respuesta directa

| ID | Pregunta | Hallazgo 2026-08-25 |
|---|---|---|
| **AUD-01** | `tagsmachines.tag_id` nulo o tag inexistente | **0** en remoto y en ambos `catalog.db` |
| **AUD-02** | `tagsmachines.machine_id` nulo o machine inexistente | **0** en remoto y en ambos `catalog.db` |
| **AUD-03** | `alarms.tag_id` nulo o tag inexistente | **0** en remoto y en ambos `catalog.db` |
| **AUD-04** | `tags.area` ≠ `nodes.area` del `owner_node` | **0**. Los 160 tags coinciden con el nodo dueño |
| **AUD-05** | Conteos remoto vs local (por área) | Linea1 **cuadrado**. Linea2: tags/alarms OK; **machines +2** (fuga Linea1); **tagsmachines 0 vs 3** |
| **AUD-06** | Reporte JSON | Este documento + JSON hermano |

`opcua` **no tiene** `tag_id` (es cliente OPC, no binding). Tabla de pending real: **`pending_rows`**, no `tagsmachines_pending`. PK de nodos: **`nodes.id`**, no `nodes.node_id`.

---

### 1. Dónde se midió

| Origen | Ruta / endpoint | Identidad |
|---|---|---|
| Historiador | `192.168.1.95:5432 / idetect_db` | Fuente de verdad |
| Edge A | `192.168.1.80:/home/intelcon/idetectfugas_backend/compose/temp/db/catalog.db` (+ WAL) | **edge-linea1** · área Linea1 |
| Edge B | `192.168.1.81:/home/intelcon/idetectfugas_backend/compose/temp/db/catalog.db` (+ WAL) | **edge-linea2** · área Linea2 |

Copia de auditoría: `catalog.db` + `catalog.db-wal` + `catalog.db-shm` (SQLite WAL; un `.db` solo mentiría). El path de la spec (`idetefugas_backend`) no existe; el real es `idetectfugas_backend`.

Nodos en PG:

| id | area | site | hostname contenedor |
|---|---|---|---|
| edge-linea1 | Linea1 | Supe | 455aa0deb63c |
| edge-linea2 | Linea2 | Supe | b69ea7260fb8 |

---

### 2. Conteos (AUD-05)

| Tabla | Remoto total | Remoto Linea1 | Local .80 | Δ | Remoto Linea2 | Local .81 | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| tags | 160 | 80 | 80 | 0 | 80 | 80 | 0 |
| machines | 12 | 7 | 7 | 0 | 5 | 7 | **+2** |
| tagsmachines | 6 | 3 | 3 | 0 | 3 | **0** | **−3** |
| alarms | 49 | 25 | 25 | 0 | 24 | 24 | 0 |
| opcua | 2 | 1 | 1 | 0 | 1 | 1 | 0 |
| pending_rows | n/a (solo local) | — | **0** | — | — | **1** | — |

Lookups (`units` 172, `users` 3) coinciden en los tres sitios. Eso es esperado: no están particionados.

---

### 3. Hallazgos (prioridad ops)

#### CAT-XAREA-01 — binds cruzados (crítico de partición)

En PostgreSQL **no hay FK rota**: `tag_id` y `machine_id` existen. El fallo es de **partición**: tres tags de Linea2 apuntan a la máquina **DAQ-1000**, que vive en **Linea1**.

| tagsmachines.id | Tag | Tag area / owner | Máquina | Machine area |
|---|---|---|---|---|
| 4 | `Supe.Linea2.FI_02` (id 104) | Linea2 / edge-linea2 | DAQ-1000 (id 12) | **Linea1** |
| 8 | `Supe.Linea2.PI_02` (id 122) | Linea2 / edge-linea2 | DAQ-1000 (id 12) | **Linea1** |
| 9 | `Supe.Linea2.DI_02` (id 106) | Linea2 / edge-linea2 | DAQ-1000 (id 12) | **Linea1** |

Los tres binds de Linea1 (`FI_02`/`PI_02`/`DI_02` → DAQ-1000) están bien: tag y máquina son Linea1. Están en el `catalog.db` de .80.

**Causa probable:** una sola fila `machines` DAQ-1000 (id=12, area=Linea1). No hay DAQ de Linea2. Quien enlazó los tags de Linea2 reutilizó la máquina de la otra línea.

#### CAT-SCOPE-01 — fugas en catalog.db de Linea2

`machines` en .81:

| id | name | area |
|---|---|---|
| 7, 8, 9, 10, 11 | Supe.Linea2.{LDS,PPA,NPW,PFM,Observer} | Linea2 (correcto) |
| **12** | **DAQ-1000** | **Linea1** (fuga) |
| **6** | **OPCUAServer** | **Linea1** (fuga) |

El replicador arrastró padres Linea1 para resolver el bind cruzado. Linea1 (.80) **no** tiene máquinas Linea2.

#### CAT-PENDING-01 — pending en Linea2

`pending_rows` (.81): una fila `tagsmachines` identity `104|12`, retries=1, first_seen `2026-08-25 19:15:22Z`, payload remoto id=4 (`FI_02`→DAQ-1000). Los binds 8 y 9 no están en pending ahora (pueden haberse descartado en ciclos previos).

`tagsmachines` local de Linea2 = **0**. El edge no puede aplicar el enlace sin romper la partición, o lo aplaza porque el padre no es de su área.

#### CAT-VER-01 — sidecar `catalog_versions`

| Sitio | `catalog_versions` de tagsmachines |
|---|---|
| Remoto | Solo row_id **4, 8, 9** (Linea2). **Faltan 1, 2, 3** (Linea1, que sí existen en la tabla) |
| Local .80 | row_id **1, 2, 3** (alineado con las filas reales de Linea1) |
| Local .81 | row_id **1, 2, 3** con los **mismos version timestamps** que el remoto 4/8/9 — remap de PK incorrecto |

---

### 4. Qué está sano (no tocar)

- 0 `tag_id`/`machine_id` NULL o =0 en `tagsmachines`.
- 0 alarms huérfanas.
- 0 tags con `area` distinta del `nodes.area` de su `owner_node`.
- 0 `unit_id` huérfano; 0 `opcua.owner_node` huérfano.
- Tags 80/80 y alarms 25/24 por línea, espejo perfecto contra el remoto filtrado por área.
- Linea1: `tagsmachines` local ≡ remoto de esa línea.

---

### 5. Plan de corrección (ops, no ejecutado en esta corrida)

Orden sugerido. Hacer backup de PG y de ambos `catalog.db` antes.

1. **Decidir el modelo DAQ por línea.** Opciones: (A) crear `DAQ-1000` (u otro nombre) con `area=Linea2` y rebind 4/8/9 a esa máquina; (B) si Linea2 no debe historizar esos tres tags en DAQ, borrar 4/8/9.
2. **No** dejar tags Linea2 colgando de `machine_id=12`.
3. En edge-linea2: quitar máquinas `DAQ-1000` y `OPCUAServer` de area Linea1 (o forzar sync limpio tras el paso 1).
4. Reconstruir `catalog_versions` de `tagsmachines` para ids 1–3 en el remoto (hoy no existen).
5. Volver a correr esta auditoría. Criterio de cierre: 0 cross-area, pending_rows=0 en ambos edges, Δ tagsmachines=0 por área, versions 1:1 con la tabla.

No usar «Vaciar cola SAF» ni `drop_orphans` como atajo: aquí el problema es **catálogo mal particionado**, no journal.

---

### 6. CA de la auditoría (proceso, no de los datos)

| ID | Criterio | Evidencia |
|---|---|---|
| CA-AUDIT-01 | Tablas críticas | `tagsmachines`, `alarms`, `pending_rows` |
| CA-AUDIT-02 | tag_id NULL | 0 filas |
| CA-AUDIT-03 | FK inválida | 0 huérfanas; 3 cross-area documentadas |
| CA-AUDIT-04 | Remoto vs cada local | Tabla §2 |
| CA-AUDIT-05 | JSON | `AUDIT_TAGS.md` |
| CA-AUDIT-06 | &lt; 5 min | PG + SFTP WAL + SQLite ≈ 2 s de queries + copia |

---

### 7. Veredicto

**No A+.** El historiador no tiene filas huérfanas clásicas (AUD-01/02/03 numéricos en cero). Sí tiene **tres bindings que rompen el contrato multi-edge** (un tag de Linea2 escrito contra una máquina de Linea1). Eso explica el pending en .81 y las dos máquinas Linea1 filtradas hacia el catálogo de Linea2.

Cierre A de **datos** cuando CAT-XAREA-01, CAT-SCOPE-01, CAT-PENDING-01 y CAT-VER-01 estén en cero en una segunda corrida.

---

### 8. Corrección de raíz en código (2026-08-25, post-auditoría)

No se parchearon filas en planta. El código ahora **impide** volver a crear o a replicar binds cruzados:

| Defensa | Dónde | CA |
|---|---|---|
| `tag.area == machine.area` al bindear | `MachinesLogger.bind_tag`, `StateMachineCore.subscribe_to`, `TagsMachines.create` | CA-CODE-01, CA-CODE-02 |
| HTTP 400 si el área no coincide | `POST /machines/<name>/subscribe` | CA-CODE-02 |
| Pull ignora `tagsmachines` cruzados (no `pending_rows`) | `replicator._filter_tagsmachines_rows` / `_skip_pull_reason` | CA-CODE-03 |
| Máquinas solo `area = NODE_AREA` (sin fallback `read_all`) | `_build_area_filter("machines")`, `_load_remote_rows` | CA-CODE-04 |
| Alarma `ALM.CATALOG.RemoteInconsistency` | `catalog/alarms.py` + latch del replicador | CA-CODE-05 |

Tests: `automation/tests/test_cross_area_bind.py` + `TestReplicatorScopeAndIntegrity` + `test_bind_tag_rejects_cross_area`.

**CA-CODE-06** (arranque limpio, 0 inconsistencias en planta) queda **pendiente** hasta desplegar el wheel en ambos edges y recrear catálogos vacíos. `TRUNCATE tags … CASCADE` en el historiador **borra TagValue/Events**; el wipe de planta debe limitarse a tablas de catálogo (o recrear `catalog.db`) **después** de instalar el código nuevo, no antes.

---

### 9. Recorrida 2026-08-25 19:50 UTC (logs del usuario)

Contraste de `docker logs idetectfugas` contra PG `idetect_db` y ambos `catalog.db` (WAL copiado).

#### Qué cambió vs 19:15

| Check | 19:15 | 19:50 |
|---|---|---|
| Binds cruzados en PG | 3 (Linea2→DAQ Linea1) | **0** |
| tagsmachines PG | 6 | **3** (solo Linea1 FI/PI/DI_02→DAQ-1000) |
| tagsmachines .80 | 3 | 3, mismos tag_id 28/46/30 |
| tagsmachines .81 | 0 | 0 |
| Máquinas Linea1 en .81 | DAQ-1000 + OPCUAServer | **igual** |
| DAQ de Linea2 | no existe | **sigue sin existir** |
| opcuaserver PG | (no medido como problema) | **3999** nodos |

#### Interpretación de los logs

1. **`.81` `Cannot bind … cross-area`** — la guarda de código **está activa y hace lo correcto**. El operador mapeó tags Linea2 a `DAQ-1000` (`area=Linea1`). HMI lo ofrece porque esa máquina **sigue en el catalog.db de Linea2**. En memoria `StateMachine.area` se pisa con `NODE_AREA`, por eso `subscribe_to` llega a `bind_tag`; Peewee lee `machines.area=Linea1` y rechaza. El texto `Remote historian unreachable during bind_tag` es **una etiqueta falsa** (`log_historian_link_issue` sobre `CrossAreaBindError`). PG está vivo (PLC81 conectó; hay writes).
2. **`.80` `IntegrityError … tag_id null` keys `28|12` `46|12` `30|12`** — esas tres filas **ya existen y están bien** en PG y en `.80`. `catalog_versions` local las tiene `conflict_resolved=0`; el remoto **no versiona** `tagsmachines`. Cada ciclo reintenta PUSH, remapea FKs a null e INSERT `(serial, null, …)`. No hay filas nulas persistidas (el INSERT falla).
3. **ambos `opcuaserver` skipped / cycle timeout 10 s** — la tabla no es “el servidor OPC”; es el **address space** (1937 nodos en `.80`, 2345 en `.81`, 3999 en PG). El cliente OPC (`opcua`: PLC80 / PLC81) está OK.

#### Qué no hacer

No borrar las 3 filas de `tagsmachines` de Linea1. No truncar `tags`. No “arreglar” el bind de Linea2 apuntando otra vez a `DAQ-1000`.

#### Qué sí hacer en planta

Crear una máquina DAQ **con `area=Linea2`**, bindear FI/PI/DI_02 a esa máquina, y quitar del `catalog.db` de `.81` las dos máquinas Linea1. El spam IntegrityError/timeout se cierra en código (no rebind).

---

### 10. Código 2026-08-25 — DAQ por nodo y opcuaserver push-only

Tras wipe limpio, el mapeo de tags **sí** crea el poller correcto **si** está este código:

| ID | Cambio | Evidencia |
|---|---|---|
| **CA-DAQ-01** | Nombre `{area}.DAQ-{ms}` (p. ej. `Linea1.DAQ-1000` ≠ `Linea2.DAQ-1000`). Unique global de `machines.name` se elimina en `ensure_schema`. Unique parcial `(area, name)` donde `area` no es nulo. Un scan time distinto en la misma línea sigue siendo otro poller (`Linea1.DAQ-200`). | `test_daq_node_scope.py` |
| **CA-OPC-PUSH-01** | `opcuaserver` ∈ `PUSH_ONLY_TABLES`: backup al PG, **cero pull** al `catalog.db` local (ni LWW remoto). Scope de nombre `{area}_…` si algún ciclo residual lee remoto. | `test_opcuaserver_is_push_only_never_pulled` |

Requiere **rebuild del wheel** en ambos edges. Un wipe con el 2.8.1 viejo **repite** la colisión `DAQ-1000`.

---

### 11. Corrida 2026-08-25 22:36 UTC — .80 vs .81 (rendimiento + CATALOG.*)

| Campo | Valor |
|---|---|
| **Imagen** | `idetectfugas/app:3.0.0` healthy en ambos (~35 min) |
| **PG** | `idetect_db` · 0 binds cruzados · `Linea1.DAQ-1000` (id 14) · `Linea2.DAQ-1000` (id 15) |
| **Canvas** | [node-perf-80-vs-81](/home/crivero/.cursor/projects/home-crivero-repo/canvases/node-perf-80-vs-81.canvas.tsx) |

#### Plano A (proceso) — ambos bien

| | .80 | .81 |
|---|---:|---:|
| TagValue 15 min | 19 661 | 19 257 |
| ACQUISITION_READY | true | true |
| SAMPLE_LAG_MS | 0 | 0 |
| PLC | PLC80 22:01:44 | PLC81 22:14:23 |

#### Plano B (sidecar) — .81 peor

| | .80 | .81 |
|---|---:|---:|
| CPU contenedor app | 20.3 % | **46.9 %** |
| EXECUTION_CYCLE_US | 92 ms | **191 ms** |
| CATALOG_SYNC_PENDING | 21 | **396** |
| consecutive_failures | 10 | **16** |
| opcuaserver local (ajenos) | 1778 (98) | **2222 (476)** |
| «No OPC UA clients» / 90 min | 11 | **82** (hasta configurar PLC) |
| DB_CONNECTIONS_ALERT | false (6) | **true (8)** |

**Causa de SyncFailed:** el replicador sumaba skips de `opcuaserver` (backup) y remap deferred de `tagsmachines` al contador de fallos duros. Con umbral 5 y ciclo ~30 s, la alarma latcheaba aunque `pending_rows=0` y el CVT estuviera sano.

**Parche en código (esta sesión):** CA-CATALOG-NOISE-01/02 — deferred remap y blips push-only **no** disparan `ALM.CATALOG.SyncFailed`; OrphanRows solo si hay huérfanos reales; warning OPC vacío una sola vez. Requiere rebuild del wheel para planta.


## Parte E — Dump JSON consistencia catálogo planta

> Fuente original: `AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.json` — contenido íntegro, sin omisiones.

```json
{
  "audit_timestamp": "2026-08-25T19:15:50.579927+00:00",
  "schema_notes": {
    "pending_table": "pending_rows (not tagsmachines_pending)",
    "nodes_pk": "nodes.id (not nodes.node_id)",
    "opcua_has_tag_id": false,
    "local_counts_are_area_scoped": true
  },
  "remote_database": {
    "name": "idetect_db",
    "host": "192.168.1.95",
    "port": 5432,
    "nodes": [
      {
        "id": "edge-linea1",
        "area": "Linea1",
        "site": "Supe",
        "hostname": "455aa0deb63c",
        "version": null
      },
      {
        "id": "edge-linea2",
        "area": "Linea2",
        "site": "Supe",
        "hostname": "b69ea7260fb8",
        "version": null
      }
    ],
    "row_counts": {
      "tags": 160,
      "machines": 12,
      "tagsmachines": 6,
      "alarms": 49,
      "opcua": 2,
      "nodes": 2,
      "users": 3,
      "units": 172,
      "catalog_versions": 4154
    },
    "row_counts_scoped_by_node": {
      "edge-linea1": {
        "area": "Linea1",
        "tags": 80,
        "machines": 7,
        "tagsmachines": 3,
        "alarms": 25
      },
      "edge-linea2": {
        "area": "Linea2",
        "tags": 80,
        "machines": 5,
        "tagsmachines": 3,
        "alarms": 24
      }
    },
    "inconsistencies": {
      "tagsmachines_tag_id_null": 0,
      "tagsmachines_tag_id_orphan": 0,
      "tagsmachines_tag_id_zero": 0,
      "tagsmachines_machine_id_null": 0,
      "tagsmachines_machine_id_orphan": 0,
      "tagsmachines_machine_id_zero": 0,
      "tagsmachines_cross_area": 3,
      "tagsmachines_duplicate_pairs": 0,
      "alarms_tag_id_null": 0,
      "alarms_tag_id_orphan": 0,
      "alarms_tag_id_zero": 0,
      "tags_area_vs_owner_node": 0,
      "tags_owner_node_missing": 0,
      "tags_unit_id_orphan": 0,
      "opcua_owner_node_missing": 0
    },
    "details": {
      "tagsmachines_tag_id_null": [],
      "tagsmachines_tag_id_orphan": [],
      "tagsmachines_tag_id_zero": [],
      "tagsmachines_machine_id_null": [],
      "tagsmachines_machine_id_orphan": [],
      "tagsmachines_machine_id_zero": [],
      "tagsmachines_cross_area": [
        {
          "id": 4,
          "tag_id": 104,
          "tag_name": "Supe.Linea2.FI_02",
          "tag_area": "Linea2",
          "owner_node": "edge-linea2",
          "machine_id": 12,
          "machine_name": "DAQ-1000",
          "machine_area": "Linea1"
        },
        {
          "id": 8,
          "tag_id": 122,
          "tag_name": "Supe.Linea2.PI_02",
          "tag_area": "Linea2",
          "owner_node": "edge-linea2",
          "machine_id": 12,
          "machine_name": "DAQ-1000",
          "machine_area": "Linea1"
        },
        {
          "id": 9,
          "tag_id": 106,
          "tag_name": "Supe.Linea2.DI_02",
          "tag_area": "Linea2",
          "owner_node": "edge-linea2",
          "machine_id": 12,
          "machine_name": "DAQ-1000",
          "machine_area": "Linea1"
        }
      ],
      "tagsmachines_duplicate_pairs": [],
      "alarms_tag_id_null": [],
      "alarms_tag_id_orphan": [],
      "alarms_tag_id_zero": [],
      "tags_area_vs_owner_node": [],
      "tags_owner_node_missing": [],
      "tags_unit_id_orphan": [],
      "opcua_owner_node_missing": []
    },
    "truncated": {}
  },
  "local_databases": {
    "edge-linea1": {
      "path": "/tmp/catalog-audit/edge-192.168.1.80/catalog.db",
      "sqlite_tables": [
        "accesstype",
        "alarms",
        "alarmstates",
        "alarmtypes",
        "catalog_versions",
        "datatypes",
        "hmi_sessions",
        "linearreferencinggeospatial",
        "machines",
        "manufacturer",
        "nodes",
        "opcua",
        "opcuaserver",
        "pending_rows",
        "roles",
        "segment",
        "tags",
        "tagsmachines",
        "units",
        "user_api_sessions",
        "users",
        "variables"
      ],
      "identity": {
        "nodes": [
          {
            "id": "edge-linea1",
            "area": "Linea1",
            "site": "Supe",
            "hostname": "455aa0deb63c",
            "version": null
          },
          {
            "id": "edge-linea2",
            "area": "Linea2",
            "site": "Supe",
            "hostname": "b69ea7260fb8",
            "version": null
          }
        ]
      },
      "wal_bytes": 4140632,
      "row_counts": {
        "tags": 80,
        "machines": 7,
        "tagsmachines": 3,
        "alarms": 25,
        "opcua": 1,
        "nodes": 2,
        "users": 3,
        "units": 172,
        "pending_rows": 0,
        "catalog_versions": 2246
      },
      "inconsistencies": {
        "tagsmachines_tag_id_null": 0,
        "tagsmachines_tag_id_orphan": 0,
        "tagsmachines_tag_id_zero": 0,
        "tagsmachines_machine_id_null": 0,
        "tagsmachines_machine_id_orphan": 0,
        "tagsmachines_machine_id_zero": 0,
        "tagsmachines_cross_area": 0,
        "alarms_tag_id_null": 0,
        "alarms_tag_id_orphan": 0,
        "alarms_tag_id_zero": 0,
        "pending_rows_all": 0,
        "pending_rows_tagsmachines": 0,
        "pending_rows_orphan_fk": 0,
        "tagsmachines_pending_orphan": 0
      },
      "details": {
        "tagsmachines_tag_id_null": [],
        "tagsmachines_tag_id_orphan": [],
        "tagsmachines_tag_id_zero": [],
        "tagsmachines_machine_id_null": [],
        "tagsmachines_machine_id_orphan": [],
        "tagsmachines_machine_id_zero": [],
        "tagsmachines_cross_area": [],
        "alarms_tag_id_null": [],
        "alarms_tag_id_orphan": [],
        "alarms_tag_id_zero": [],
        "pending_rows_all": [],
        "pending_rows_tagsmachines": [],
        "pending_rows_orphan_fk": [],
        "tagsmachines_pending_orphan": []
      },
      "truncated": {},
      "host": "192.168.1.80",
      "remote_path": "/home/intelcon/idetectfugas_backend/compose/temp/db/catalog.db",
      "copied_files": [
        "app_config.json",
        "catalog.db",
        "catalog.db-shm",
        "catalog.db-wal",
        "db_config.json"
      ],
      "node_id": "edge-linea1",
      "area": "Linea1"
    },
    "edge-linea2": {
      "path": "/tmp/catalog-audit/edge-192.168.1.81/catalog.db",
      "sqlite_tables": [
        "accesstype",
        "alarms",
        "alarmstates",
        "alarmtypes",
        "catalog_versions",
        "datatypes",
        "hmi_sessions",
        "linearreferencinggeospatial",
        "machines",
        "manufacturer",
        "nodes",
        "opcua",
        "opcuaserver",
        "pending_rows",
        "roles",
        "segment",
        "tags",
        "tagsmachines",
        "units",
        "user_api_sessions",
        "users",
        "variables"
      ],
      "identity": {
        "nodes": [
          {
            "id": "edge-linea2",
            "area": "Linea2",
            "site": "Supe",
            "hostname": "b69ea7260fb8",
            "version": null
          },
          {
            "id": "edge-linea1",
            "area": "Linea1",
            "site": "Supe",
            "hostname": "455aa0deb63c",
            "version": null
          }
        ]
      },
      "wal_bytes": 4161232,
      "row_counts": {
        "tags": 80,
        "machines": 7,
        "tagsmachines": 0,
        "alarms": 24,
        "opcua": 1,
        "nodes": 2,
        "users": 3,
        "units": 172,
        "pending_rows": 1,
        "catalog_versions": 2649
      },
      "inconsistencies": {
        "tagsmachines_tag_id_null": 0,
        "tagsmachines_tag_id_orphan": 0,
        "tagsmachines_tag_id_zero": 0,
        "tagsmachines_machine_id_null": 0,
        "tagsmachines_machine_id_orphan": 0,
        "tagsmachines_machine_id_zero": 0,
        "tagsmachines_cross_area": 0,
        "alarms_tag_id_null": 0,
        "alarms_tag_id_orphan": 0,
        "alarms_tag_id_zero": 0,
        "pending_rows_all": 1,
        "pending_rows_tagsmachines": 1,
        "pending_rows_orphan_fk": 1,
        "tagsmachines_pending_orphan": 0
      },
      "details": {
        "tagsmachines_tag_id_null": [],
        "tagsmachines_tag_id_orphan": [],
        "tagsmachines_tag_id_zero": [],
        "tagsmachines_machine_id_null": [],
        "tagsmachines_machine_id_orphan": [],
        "tagsmachines_machine_id_zero": [],
        "tagsmachines_cross_area": [],
        "alarms_tag_id_null": [],
        "alarms_tag_id_orphan": [],
        "alarms_tag_id_zero": [],
        "pending_rows_all": [
          {
            "table_name": "tagsmachines",
            "row_id": "104|12",
            "retries": 1,
            "first_seen": "2026-08-25 19:15:22.053823+00:00"
          }
        ],
        "pending_rows_tagsmachines": [
          {
            "table_name": "tagsmachines",
            "row_id": "104|12",
            "retries": 1,
            "first_seen": "2026-08-25 19:15:22.053823+00:00"
          }
        ],
        "pending_rows_orphan_fk": [
          {
            "table_name": "tagsmachines",
            "row_id": "104|12",
            "retries": 1,
            "first_seen": "2026-08-25 19:15:22.053823+00:00",
            "row_data": "{\"id\": 4, \"tag_id\": 104, \"machine_id\": 12, \"default_tag_name\": null, \"sample_override\": null, \"_pk\": \"4\"}"
          }
        ],
        "tagsmachines_pending_orphan": []
      },
      "truncated": {},
      "host": "192.168.1.81",
      "remote_path": "/home/intelcon/idetectfugas_backend/compose/temp/db/catalog.db",
      "copied_files": [
        "app_config.json",
        "catalog.db",
        "catalog.db-shm",
        "catalog.db-wal",
        "db_config.json"
      ],
      "node_id": "edge-linea2",
      "area": "Linea2"
    }
  },
  "sync_comparison": [
    {
      "node_id": "edge-linea1",
      "host": "192.168.1.80",
      "area": "Linea1",
      "remote_scoped": {
        "area": "Linea1",
        "tags": 80,
        "machines": 7,
        "tagsmachines": 3,
        "alarms": 25
      },
      "local": {
        "tags": 80,
        "machines": 7,
        "tagsmachines": 3,
        "alarms": 25,
        "opcua": 1,
        "pending_rows": 0
      },
      "delta": {
        "tags": 0,
        "machines": 0,
        "tagsmachines": 0,
        "alarms": 0
      }
    },
    {
      "node_id": "edge-linea2",
      "host": "192.168.1.81",
      "area": "Linea2",
      "remote_scoped": {
        "area": "Linea2",
        "tags": 80,
        "machines": 5,
        "tagsmachines": 3,
        "alarms": 24
      },
      "local": {
        "tags": 80,
        "machines": 7,
        "tagsmachines": 0,
        "alarms": 24,
        "opcua": 1,
        "pending_rows": 1
      },
      "delta": {
        "tags": 0,
        "machines": 2,
        "tagsmachines": -3,
        "alarms": 0
      }
    }
  ],
  "summary": {
    "total_inconsistencies": 6,
    "action_required": true,
    "remote_inconsistencies": 3,
    "local_inconsistencies": {
      "edge-linea1": 0,
      "edge-linea2": 3
    }
  },
  "findings": [
    {
      "id": "CAT-XAREA-01",
      "severity": "high",
      "check": "AUD-01/AUD-02 (semantic, not NULL FK)",
      "title": "tagsmachines cruzan Linea2 tags con m\u00e1quina Linea1 DAQ-1000",
      "count": 3,
      "rows": [
        {
          "id": 4,
          "tag_id": 104,
          "tag_name": "Supe.Linea2.FI_02",
          "tag_area": "Linea2",
          "owner_node": "edge-linea2",
          "machine_id": 12,
          "machine_name": "DAQ-1000",
          "machine_area": "Linea1"
        },
        {
          "id": 8,
          "tag_id": 122,
          "tag_name": "Supe.Linea2.PI_02",
          "tag_area": "Linea2",
          "owner_node": "edge-linea2",
          "machine_id": 12,
          "machine_name": "DAQ-1000",
          "machine_area": "Linea1"
        },
        {
          "id": 9,
          "tag_id": 106,
          "tag_name": "Supe.Linea2.DI_02",
          "tag_area": "Linea2",
          "owner_node": "edge-linea2",
          "machine_id": 12,
          "machine_name": "DAQ-1000",
          "machine_area": "Linea1"
        }
      ],
      "action": "Crear DAQ-1000 de Linea2 (o rebind a m\u00e1quina Linea2) y reescribir ids 4, 8, 9."
    },
    {
      "id": "CAT-SCOPE-01",
      "severity": "medium",
      "check": "AUD-05",
      "title": "edge-linea2 catalog.db contiene 2 m\u00e1quinas de Linea1",
      "machines": [
        "DAQ-1000",
        "OPCUAServer"
      ],
      "action": "Eliminar del cat\u00e1logo local de Linea2 las m\u00e1quinas area=Linea1 y forzar sync."
    },
    {
      "id": "CAT-PENDING-01",
      "severity": "medium",
      "check": "AUD-01 local pending",
      "title": "edge-linea2 pending_rows tagsmachines 104|12 (bind remoto id=4)",
      "retries": 1,
      "first_seen": "2026-08-25 19:15:22Z",
      "action": "Se resuelve al corregir el bind cruzado; no vaciar pending a ciegas."
    },
    {
      "id": "CAT-VER-01",
      "severity": "medium",
      "check": "catalog_versions",
      "title": "Remoto: tagsmachines ids 1,2,3 sin fila en catalog_versions; ids 4,8,9 s\u00ed. Local Linea2 versiona row_id 1,2,3 con los timestamps de 4,8,9.",
      "action": "Tras corregir binds, reconstruir sidecar catalog_versions de tagsmachines."
    }
  ],
  "ca_audit": {
    "CA-AUDIT-01": "PASS \u2014 tagsmachines, alarms, pending_rows",
    "CA-AUDIT-02": "PASS \u2014 0 filas tag_id NULL",
    "CA-AUDIT-03": "PASS \u2014 0 FK hu\u00e9rfanas; 3 binds cross-area (FK v\u00e1lidas, partici\u00f3n rota)",
    "CA-AUDIT-04": "PASS \u2014 conteos remoto vs local por \u00e1rea",
    "CA-AUDIT-05": "PASS \u2014 JSON generado",
    "CA-AUDIT-06": "PASS \u2014 < 5 min"
  }
}
```

