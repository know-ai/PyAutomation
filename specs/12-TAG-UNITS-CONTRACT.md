# Documento 12: Contrato de unidades de tags (tres planos)

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 2026-09-21 |
| **Producto** | PyAutomationIO (`automation/`) |
| **Estado** | **Implementado v1** (Planos 1–2; Plano 3 diferido) |
| **Auditoría** | [AUDIT_TAG_UNITS.md](../audits/AUDIT_TAG_UNITS.md) |
| **Runbook** | [tag-units-runbook.md](../docs/tag-units-runbook.md) |
| **Complementa** | [11-CATALOG-SQLITE-LOCAL.md](./11-CATALOG-SQLITE-LOCAL.md), [AUDIT_TAGS.md](../audits/AUDIT_TAGS.md) |
| **Producto consumidor** | iDetectFugas declara SI (`Pa`, `kg/sec`); no edita este contrato |

---

## Índice

- [§1 Tres planos](#planos)
- [§2 v1 vs v2](#v1-v2)
- [§3 Reglas de oro](#reglas)
- [§4 `unit_source`](#unit-source)
- [§5 Freeze SAF](#saf)
- [§6 Bootstrap no destructivo](#bootstrap)
- [§7 Suscripción SI](#si)
- [§8 Alias](#alias)
- [§9 Migraciones](#migraciones)
- [§10 Criterios de aceptación](#ca)

---

## §1 Tres planos

<a id="planos"></a>

| Plano | Superficie | Quién gana |
|---|---|---|
| **1. SI de código** | `ProcessType.unit` (p. ej. `Pa`) | Motor / producto |
| **2. Persistido (v1)** | `tag.unit` + `tag.display_unit` en CVT, catálogo e historiador; `journal.unit` congelado | BD si la fila existe; código en insert frío; operador en `PUT /api/tags` |
| **3. Presentación (v2, diferido)** | Conversión HMI / Socket.IO on the fly; CVT en `storage_unit` distinto | Fuera de este contrato |

En **v1**, `display_unit` **no** es “solo HMI”. Es la unidad persistida en CVT, Socket.IO y `TagValue` (el nombre conceptual de almacenamiento es `storage_unit`, pero las columnas siguen siendo `unit` / `display_unit`).

```
ProcessType.unit  --cold start create_tag-->  tag.display_unit (CVT / TagValue)
                                              tag.unit (ingeniería / OPC nativo)
PUT /api/tags     --unit_source=operator-->   mismas columnas
bootstrap set_tag --no pisa si existe------>  BD gana; CVT se alinea
SAF journal       --unit congelado--------->  mapper ignora el tag vivo
```

---

## §2 v1 vs v2

<a id="v1-v2"></a>

| | v1 (este spec) | v2 (posterior) |
|---|---|---|
| Columnas BD | `unit`, `display_unit`, `unit_source`, `unit_locked_at` | Posible `storage_unit`; `display_unit` solo presentación |
| Valor en CVT | En `display_unit` | En unidad de almacenamiento SI / nativa |
| HMI | Muestra `display_unit` tal cual | Convierte al vuelo |
| Deploy 2.10 | **No cambia** símbolos existentes; solo semántica de muestras **nuevas** y bootstrap | Sprint HMI aparte |

---

## §3 Reglas de oro

<a id="reglas"></a>

1. **Insert frío** (no hay fila): el código escribe `ProcessType.unit` → `unit`/`display_unit`, `unit_source=engine`.
2. **Fila existente + bootstrap / reconcile**: no se pisan `unit`, `display_unit` ni `unit_source`. El objeto CVT se **alinea** a lo persistido.
3. **`PUT /api/tags` / `update_tag`**: el operador gana; `unit_source=operator`, `unit_locked_at=now`.
4. **Muestra SAF**: el símbolo viaja en el JSON (`unit`). El mapper **nunca** usa el tag vivo si hay `unit` en el payload.
5. **`NULL unit_source`**: se trata como `engine` (filas pre-2.10).
6. **Migración de símbolo** (`bar`→`Pa`): nunca auto-apply en arranque. Dry-run en boot; apply opt-in.
7. **Nunca migrar** filas con `unit_source=operator`.

---

## §4 `unit_source`

<a id="unit-source"></a>

| Valor | Significado |
|---|---|
| `engine` | Creado por `create_tag` / bootstrap de máquina |
| `operator` | Último cambio vía `PUT /api/tags` o `update_tag` |
| `imported` | Carga de catálogo / réplica / import |
| `NULL` | Legacy; **equivalente a `engine`** en migraciones |

`unit_locked_at`: timestamp del último PUT de unidades del operador (nullable).

---

## §5 Freeze SAF

<a id="saf"></a>

`PersistableRecord.tag_sample` admite kwargs opcionales:

- `unit` — símbolo canónico en el instante de captura
- `unit_source` — procedencia en ese instante
- `display_unit_at_sample` — forense (qué mostraba el tag)

Claves extra en JSON: el mapper 2.9 las ignora (rollback seguro del journal).

Captura: `TagObserver.update` escribe el mismo símbolo que `convert(get_display_unit())`.

Mapper: `item["unit"]` → `Units.read_by_unit` / auto-create con warning. Sin clave: fallback al `display_unit` vivo + contador `SAF_SAMPLES_WITHOUT_UNIT` (**CA-UNIT-11**).

---

## §6 Bootstrap no destructivo

<a id="bootstrap"></a>

`DataLogger.set_tag(..., update_units=False)` (default) y `persist_tag_to_local`:

- Si la fila existe: omitir `unit` / `display_unit` / `unit_source` del PUT; alinear CVT a BD.
- Insert nuevo: `unit_source=engine`.

`ensure_tag_historian_catalog` y el reconcile de arranque **no** pasan `update_units=True`.

---

## §7 Suscripción SI

<a id="si"></a>

`StateMachine.notify` / `subscribe_to`: flujo sigue usando `mass_flow_unit_base` / `volumetric_flow_unit_base`. El resto convierte a `ProcessType.unit` (helper `resolve_value_for_process_type`). Si no hay conversión, evento + `UNITS_MISMATCH_COUNT`.

El producto puede declarar `pressure_unit_base = "Pa"` (simetría con caudal).

---

## §8 Alias

<a id="alias"></a>

`UNIT_ALIASES` (símbolo de entrada → canónico de catálogo):

| Alias | Canónico |
|---|---|
| `kg/s` | `kg/sec` |
| `m3/s`, `m³/s` | `m3/sec` |
| `°K` | `K` |
| `barg` | `bar` |

Aplican en `Units.read_by_unit`, `create_tag`, `EngUnit.convert` / `change_unit`.

---

## §9 Migraciones

<a id="migraciones"></a>

Registro versionado en `automation/migrations/unit_migrations.py`. Arranque: **solo dry-run** (log). Apply:

- `POST /api/admin/unit-migrations/apply` con `confirm=true` (rol admin/integrator), o
- `AUTOMATION_UNIT_MIGRATIONS_APPLY=1`

Registro inicial: `PI_*` `bar`→`Pa`; `FI_*` `kg/s`→`kg/sec`; solo `unit_source in {engine, imported, NULL}`. Evento `Unit migrated:`.

---

## §10 Criterios de aceptación

<a id="ca"></a>

| ID | Criterio |
|---|---|
| **CA-UNIT-01** | `tag_sample` incluye `unit` (y opcionalmente `unit_source`, `display_unit_at_sample`) |
| **CA-UNIT-02** | Encolar en Pa, cambiar `display_unit` a bar, drenar → `TagValue.unit` sigue Pa |
| **CA-UNIT-03** | Restart: `set_tag` no pisa `unit`/`display_unit` de filas existentes |
| **CA-UNIT-04** | 10 reinicios: dump de unidades estable |
| **CA-UNIT-05** | Cold start: `create_tag` escribe la unidad del `ProcessType` |
| **CA-UNIT-06** | Suscripción no-flujo convierte a `ProcessType.unit` |
| **CA-UNIT-07** | PUT tags marca `unit_source=operator` |
| **CA-UNIT-08** | Alias `kg/s` → `kg/sec` (y familia) |
| **CA-UNIT-09** | Fallo de conversión → evento + `UNITS_MISMATCH_COUNT` |
| **CA-UNIT-10** | Migración opt-in; nunca `operator`; dry-run en boot |
| **CA-UNIT-11** | Sample SAF sin `unit` → fallback + `SAF_SAMPLES_WITHOUT_UNIT` |
| **CA-UNIT-12** | Health expone `UNITS_MISMATCH_COUNT` y `SAF_SAMPLES_WITHOUT_UNIT` |

Métricas: `GET /api/health/system`.
