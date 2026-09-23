# Auditoría: consistencia de unidades de tags (CVT ↔ BD ↔ SAF)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Fecha** | 2026-09-21 (hallazgo) · **cierre v1 2026-09-21** (spec 12) |
| **Alcance** | Ciclo de vida de `unit` / `display_unit` / `unit_source`: cold start, restart, upgrade, SAF, catálogo SQLite, historiador, suscripción SI |
| **Fuera de alcance** | Plano 3 (HMI-only `display_unit` + conversión on-the-fly) — v2. Algoritmos LDS/NPW: [18-AUDIT_TAG_UNITS.md](../../gitlab/intelcon/idetectfugas/audits/18-AUDIT_TAG_UNITS.md) |
| **Complementa** | [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) |
| **Contrato** | [specs/12-TAG-UNITS-CONTRACT.md](../specs/12-TAG-UNITS-CONTRACT.md) · [docs/tag-units-runbook.md](../docs/tag-units-runbook.md) |
| **Veredicto** | Arranque en frío **A** · restart / bootstrap **A** · SAF freeze **A** · suscripción SI **A−** · alias **A** · migraciones opt-in **A** · Plano 3 **diferido** |
| **Clasificación** | Contraste código vs diseño. IDs `TU-F*` · CAs `CA-UNIT-01`…`12` |
| **Tests** | `automation/tests/test_tag_units_{saf,bootstrap,aliases,migrations}.py` (18 OK) |

---

## 0. Respuesta directa (post-v1)

| Pregunta | Respuesta |
|---|---|
| ¿Cold start (BD vacía) crea tags con la unidad del `ProcessType`? | **Sí.** `create_tag_internal_process_type` usa `value.unit`; insert marca `unit_source=engine`. |
| ¿Tras crash/restart se conservan unidades sin edición manual? | **Sí** (hydrate + duplicado CVT). Además, si la fila existe, `set_tag(..., update_units=False)` **omite** `unit`/`display_unit`/`unit_source` del PUT y alinea el objeto CVT a BD. |
| ¿Tras crash se conservan si el operador cambió `display_unit`? | **Sí.** BD gana en bootstrap; PUT explícito marca `unit_source=operator` + `unit_locked_at`. Migraciones **nunca** tocan `operator`. |
| ¿SAF y historiador hablan la misma unidad? | **Sí en muestras nuevas.** `tag_sample` congela `unit` (+ `unit_source`, `display_unit_at_sample`). El mapper prioriza el símbolo del payload. Journal legado sin `unit` → fallback al display vivo + contador `SAF_SAMPLES_WITHOUT_UNIT` (**CA-UNIT-11**). |
| ¿El motor recibe SI del `ProcessType`? | **Sí.** `subscribe_to` llama `resolve_value_for_process_type(..., mutate=True)` hacia `process_type.unit` (no al `display_unit` del tag). Mismatch → warning + `UNITS_MISMATCH_COUNT`. |
| ¿Dónde vive el contrato SI de producto? | iDetectFugas (`Pa`, `kg/sec`, `pressure_unit_base`). Este repo no impone el algoritmo. |

### Modelo v1 (tres planos; Plano 3 diferido)

```
Plano 1  ProcessType.unit          → SI declarado en código (producto)
Plano 2  tag.unit / tag.display_unit → persistido en CVT + TagValue (v1: display_unit = storage conceptual)
         unit_source ∈ {engine, operator, imported, NULL≡engine}
         journal.unit                → congelado en muestreo (TagObserver)
Plano 3  HMI conversion on the fly → fuera de v1
```

En v1, `display_unit` **no** es “solo HMI”: es la unidad del valor en CVT/historiador. DAQ sigue convirtiendo `unit → display_unit` antes de publicar.

---

## 1. Ciclo de vida (evidencia post-fix)

### 1.1 Arranque

```
bootstrap_local_catalog()
connect_to_db()                  # hydrate: load_db_to_cvt
  └─ si PG caído: _hydrate_from_local_catalog()
…
Machine.start(machines)          # create_tag_internal_process_type
load_db_tags_to_machine()
reconcile_runtime_tag_catalog()  # set_tag(..., update_units=False)
Unit migrations dry-run (log)    # apply solo POST/env — nunca auto
```

### 1.2 Creación desde máquinas

Cold start: insert con `ProcessType.unit` + `unit_source=engine`.  
Restart hidratado: duplicado CVT → se reutiliza; `ensure_tag_historian_catalog` **no** pasa `update_units=True`.

### 1.3 Persistencia (`DataLogger.set_tag`)

| Caso | Comportamiento |
|---|---|
| Fila nueva | Escribe `unit` / `display_unit`; `unit_source=engine` (default) |
| Fila existente, `update_units=False` (default) | Omite claves de unidad del PUT; **alinea CVT** a lo persistido |
| `update_tag` / PUT API | `update_units=True`, `unit_source=operator`, `unit_locked_at=now` |

`persist_tag_to_local`: misma regla (no pisa `unit_id`/`display_unit_id` si la fila ya existe).

### 1.4 SAF

`PersistableRecord.tag_sample` (kwargs opcionales; mapper 2.9 ignora desconocidos = rollback seguro):

```json
{ "tag", "value", "timestamp", "sample_uuid", "area", "owner_node",
  "unit", "unit_source", "display_unit_at_sample", "quality"? }
```

`TagObserver.update` congela el símbolo tras `convert(get_display_unit())`.  
`TagValuePayloadMapper._lookup_unit`: prioriza `item["unit"]` → `Units.read_by_unit` / auto-create; legacy sin clave → display vivo + métrica.

### 1.5 Suscripción SI

Callback de `subscribe_to` (~1477): no-flujo → `resolve_value_for_process_type` a `process_type.unit`. Alias vía `UNIT_ALIASES` / `canonical_symbol` (`kg/s`→`kg/sec`, `barg`→`bar`, …).

### 1.6 Migraciones opt-in

`automation/migrations/unit_migrations.py` + `POST /api/admin/unit-migrations/{dry-run,apply}`.  
Registro inicial: `PI_*` `bar`→`Pa`, `FI_*` `kg/s`→`kg/sec`, solo `unit_source in {engine, imported, NULL}`. Nunca `operator`. Evento `Unit migrated:`.

### 1.7 Observabilidad

`GET /api/health/system`: `UNITS_MISMATCH_COUNT`, `SAF_SAMPLES_WITHOUT_UNIT`.

---

## 2. Hallazgos (estado)

| ID | Sev. original | Hallazgo (histórico) | Estado v1 |
|---|---|---|---|
| **TU-F1** | Alta | Journal sin unidad; mapper usaba display live | **Mitigado** — freeze en `tag_sample` + mapper prioriza símbolo (**CA-UNIT-01/02/11**) |
| **TU-F2** | Alta | Bootstrap/reconcile upsertaba unidades | **Mitigado** — `update_units=False` por defecto; BD gana (**CA-UNIT-03/04/05**) |
| **TU-F3** | Media | Suscripción a `display_unit`, no a `ProcessType.unit` | **Mitigado** — `resolve_value_for_process_type` (**CA-UNIT-06/09**) |
| **TU-F4** | Media | Default Pressure = `bar` en catálogo | **Abierto (aceptado)** — cold start de producto pasa `Pa` explícito; HMI sin unit sigue en `bar` |
| **TU-F5** | Media | Sin alias `kg/s` | **Mitigado** — `UNIT_ALIASES` (**CA-UNIT-08**) |
| **TU-F6** | Media | Sin migración SI versionada | **Mitigado (opt-in)** — dry-run/apply; no auto en boot (**CA-UNIT-10**) |
| **TU-F7** | Baja | Rama `Tags.create` “already exists” confusa | **Abierto (P2)** — cosmético |
| **TU-F8** | Baja | Seed `name_exist` símbolo vs name | **Abierto (P2)** — edge frío raro |
| **TU-F9** | Info | `.f` hereda unidades del source | **OK** |

### Escenarios (post-v1)

| Escenario | Qué ocurre | ¿Consistente? |
|---|---|---|
| A. Primera instalación, PG vacío | Tags con unidad del `ProcessType`; `unit_source=engine` | Sí |
| B. Restart, PG up, sin edición | Hydrate → mismas unidades; PUT sin campos de unidad | Sí |
| C. Restart, operador puso `display_unit=bar` | BD gana; motor recibe Pa vía suscripción SI | Sí (display) + Sí (algoritmo) |
| D. Restart, PG caído, catalog íntegro | Hydrate local; no pisa unidades | Sí |
| E. Restart, CVT vacío / hydrate omitido | `set_tag` no actualiza unidades de filas existentes | Sí (ya no pisa) |
| F. Journal PENDING + cambio display | Muestras **nuevas** congelan unidad; legado → fallback + contador | Sí (nuevas) / controlado (legado) |
| G. Upgrade de app, código SI nuevo | Fila existente gana; apply opcional si `unit_source≠operator` | Sí (política) |

---

## 3. Pros y contras (post-v1)

### Pros

| # | Qué funciona |
|---|---|
| P1 | Dos capas `unit` / `display_unit` + `unit_source` |
| P2 | Hydrate antes de `Machine.start` |
| P3 | Bootstrap no destructivo (`update_units=False`) |
| P4 | Freeze SAF con rollback seguro (claves JSON extra) |
| P5 | Suscripción convierte a SI del motor |
| P6 | Alias canónicos; migraciones opt-in + eventos |
| P7 | Métricas en `/api/health/system` |
| P8 | Suite de regresión 18 tests |

### Contras / deuda restante

| # | Qué queda | Notas |
|---|---|---|
| C1 | Plano 3 diferido | CVT sigue en `display_unit`; HMI-only conversion = v2 |
| C2 | Default Pressure = `bar` (TU-F4) | Solo afecta creates sin `unit` explícito |
| C3 | Journal pre-2.10 sin `unit` | Fallback CA-UNIT-11; drenar PENDING antes de deploy |
| C4 | Producto debe instalar wheel nuevo | iDetectFugas no parchea site-packages |

---

## 4. Frontera con iDetectFugas

No duplicar persistencia/SAF en `app/`. El producto:

- Declara SI en `ProcessType` y `pressure_unit_base` / `mass_flow_unit_base`.
- Puede delegar a `resolve_value_for_process_type` en paths propios (`_eng_value_to_pa`).
- Reinstala el wheel desde este repo; no edita `venv/.../site-packages/automation`.

---

## 5. Criterios de aceptación (cerrados)

| CA | Estado |
|---|---|
| CA-UNIT-01 Freeze `unit` en `tag_sample` | **Cerrado** (`test_tag_units_saf.py`) |
| CA-UNIT-02 Mapper usa símbolo congelado | **Cerrado** |
| CA-UNIT-03 Bootstrap no pisa unidades | **Cerrado** (`test_tag_units_bootstrap.py`) |
| CA-UNIT-04 Dump estable en N reinicios | **Cerrado** |
| CA-UNIT-05 Cold start escribe ProcessType | **Cerrado** (`unit_source=engine`) |
| CA-UNIT-06 Suscripción → `ProcessType.unit` | **Cerrado** |
| CA-UNIT-07 PUT marca `operator` | **Cerrado** (`update_tag`) |
| CA-UNIT-08 Alias `kg/s`… | **Cerrado** (`UNIT_ALIASES`) |
| CA-UNIT-09 Mismatch + métrica | **Cerrado** (`UNITS_MISMATCH_COUNT`) |
| CA-UNIT-10 Migraciones opt-in | **Cerrado** (`unit_migrations.py`) |
| CA-UNIT-11 Fallback SAF sin `unit` | **Cerrado** (`SAF_SAMPLES_WITHOUT_UNIT`) |
| CA-UNIT-12 Health | **Cerrado** (`GET /api/health/system`) |

---

## 6. Archivos clave

| Área | Ruta |
|---|---|
| Spec | `specs/12-TAG-UNITS-CONTRACT.md` |
| Runbook | `docs/tag-units-runbook.md` |
| Payload SAF | `automation/persistence/records.py` |
| Observer freeze | `automation/tags/tag.py` (`TagObserver.update`) |
| Mapper | `automation/persistence/remote.py` |
| Bootstrap | `automation/logger/datalogger.py`, `catalog/seed.py`, `catalog/runtime_tag.py` |
| Modelo BD | `automation/dbmodels/tags.py` (`unit_source`, `unit_locked_at`) |
| SI subscribe | `automation/variables/units_contract.py`, `state_machine.py` |
| Alias | `automation/variables/unit_symbols.py` / `__init__.py` |
| Migraciones | `automation/migrations/unit_migrations.py`, `modules/admin/resources/admin.py` |
| Métricas | `automation/modules/health/…`, `unit_metrics.py` |

---

## 7. Veredicto

v1 **cierra** la integridad P0 (SAF + bootstrap) y el puente SI de suscripción. El deploy del wheel **no cambia** símbolos ya persistidos; solo congela muestras nuevas y deja de pisar filas. Migraciones `bar`→`Pa` / `kg/s`→`kg/sec` son opt-in.

Pendiente explícito: Plano 3 (v2), TU-F4/F7/F8 cosméticos, y validación en planta tras reinstalar el wheel.
