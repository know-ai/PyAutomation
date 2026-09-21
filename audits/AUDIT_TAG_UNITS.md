# Auditoría: consistencia de unidades de tags (CVT ↔ BD ↔ SAF)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Fecha** | 2026-09-21 |
| **Alcance** | Ciclo de vida de `unit` / `display_unit`: cold start, restart, upgrade, SAF, catálogo SQLite, historiador |
| **Fuera de alcance** | Algoritmos LDS/NPW (contrato SI del producto: [18-AUDIT_TAG_UNITS.md](../../gitlab/intelcon/idetectfugas/audits/18-AUDIT_TAG_UNITS.md) en el repo iDetectFugas) |
| **Complementa** | [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md) |
| **Veredicto** | Arranque en frío **B+** · restart con hydrate **B** · SAF vs unidad **D** · upsert bootstrap **C** · contrato SI producto↔display **C** |
| **Clasificación** | Contraste código vs diseño. IDs `TU-F*` |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Cold start (BD vacía) crea tags con la unidad del `ProcessType`? | **Sí.** `create_tag_internal_process_type` usa `value.unit` (p. ej. `Pa` en NPW). |
| ¿Tras un crash/restart se conservan unidades si el operador no las tocó? | **Sí, si el hydrate corre antes de las máquinas** (`connect_to_db` → `load_db_to_cvt` → luego `Machine.start`). |
| ¿Tras un crash se conservan si el operador **sí** cambió `display_unit`? | **Sí en el camino feliz** (hydrate carga BD → `create_tag` ve duplicado en CVT y no recrea). **No está garantizado** si el hydrate falla o el CVT está vacío: el bootstrap **upserta** unidades desde el objeto en memoria. |
| ¿SAF y historiador hablan la misma unidad? | **No de forma fiable.** El journal **no guarda** el símbolo de unidad; al drenar, el mapper usa el `display_unit` **actual** del tag remoto. |
| ¿Dónde hay que corregir? | **PyAutomation** (persistencia, SAF, upsert). iDetectFugas solo define el contrato SI (`Pa`, `kg/sec`, …). |

### Modelo de dos unidades (diseño actual)

```
tag.unit            → unidad de ingeniería / supuesto nativo OPC (conversión DAQ)
tag.display_unit    → unidad en CVT, HMI, Socket.IO y TagValue del historiador
ProcessType.unit    → unidad que declara el motor en código (producto)
```

DAQ y `ProcessType.set_value` convierten `unit → display_unit` **antes** de publicar. El valor en CVT/HMI/SAF es el de **display**, no el de ingeniería, salvo que ambas coincidan.

---

## 1. Ciclo de vida (evidencia de código)

### 1.1 Arranque (`automation/core.py` `__start_workers`)

```
bootstrap_local_catalog()
connect_to_db()                  # hydrate: load_db_to_cvt  (tags desde historiador)
  └─ si PG caído: _hydrate_from_local_catalog()
…
Machine.start(machines)          # create_tag_internal_process_type
load_db_tags_to_machine()        # solo suscripciones, no unidades
reconcile_runtime_tag_catalog()  # ensure_tag_historian_catalog por cada tag CVT
```

El orden **hydrate → máquinas** es la salvaguarda principal del restart. No hay un flag “unidad de código vs unidad de operador”.

### 1.2 Creación desde máquinas (`state_machine.py` `create_tag_internal_process_type`)

1. Recorre `ProcessType` **escribibles** → `create_tag(name="{machine}.{attr}", unit=value.unit, …, skip_validation=True)`.
2. Recorre `internal_tags_relationships` + `ProcessType` **read-only** → tags de campo (`PI_01`, `FI_01`, …) con `unit` del atributo.
3. La variable física se infiere recorriendo `VARIABLES` hasta que `value.unit` está en el catálogo (`Pa` → `Pressure`).
4. Si `cvt.set_tag` reporta duplicado, con `skip_validation=True` se **reutiliza** el tag ya hidratado y se llama `ensure_tag_historian_catalog`.

Cold start: no hay duplicado → se crea con la unidad del código.  
Restart hidratado: duplicado → se conserva lo de BD.

### 1.3 Persistencia historiador (`logger/datalogger.py` `set_tag`)

Si la fila **ya existe** por nombre/id:

```
Tags.put(..., unit=..., display_unit=..., ...)
```

Es un **UPDATE completo**, no un insert-if-missing. `_tag_put_fields` omite `None`/vacío en FKs, pero **no** omite una unidad distinta a la persistida.

`ensure_tag_historian_catalog` (`catalog/runtime_tag.py`) llama `logger_engine.set_tag(tag)` en cada `create_tag`, cada tag interno de máquina y en el reconcile de arranque.

### 1.4 Catálogo local (`catalog/seed.py` `persist_tag_to_local`)

Preserva con cuidado `opcua_*` y `scan_time` si el espejo ya los tiene. **No** preserva `unit_id` / `display_unit_id`: siempre escribe los del objeto CVT.

El seed de la tabla `units` (`seed_variables_and_units`) **sí** es conservador: si hay filas, no pisa símbolos de operador.

### 1.5 SAF (`persistence/records.py` + `persistence/remote.py`)

`PersistableRecord.tag_sample` guarda:

```json
{ "tag", "value", "timestamp", "sample_uuid", "area", "owner_node", "quality"? }
```

**No hay `unit`.** Al replicar, `TagValuePayloadMapper._lookup_unit` resuelve:

```
Units.get_or_none(id=tag.display_unit.id)  # display_unit del tag remoto ahora
```

`TagValue.unit` en PostgreSQL es FK a `Units` **por muestra**, pero el valor de esa FK se elige en el **drenaje**, no en el muestreo.

---

## 2. Hallazgos

| ID | Sev. | Capa | Hallazgo | Riesgo operativo |
|---|---|---|---|---|
| **TU-F1** | **Alta** | SAF | Journal sin símbolo de unidad; mapper usa `display_unit` live | Si el operador (o un upsert de bootstrap) cambia `display_unit` con journal PENDING, las muestras drenan con **número viejo + unidad nueva** (p. ej. 200000 etiquetado `bar` en vez de `Pa`) |
| **TU-F2** | **Alta** | Historiador / catálogo | `set_tag` / `persist_tag_to_local` hacen upsert de unidades en cada bootstrap y en `reconcile_runtime_tag_catalog` | Si el CVT no está hidratado, el código **pisa** la BD. El reconcile de arranque refuerza lo que haya en memoria, no un “no tocar si el operador editó” |
| **TU-F3** | Media | Contrato runtime | CVT y algoritmos no usan la misma convención | DAQ convierte a `display_unit`. La SM, al suscribir, hace `change_unit(process_type.tag.display_unit)`, **no** `ProcessType.unit`. Un motor que asume `Pa` recibe `bar` si el operador cambió display |
| **TU-F4** | Media | Catálogo Pressure | Default de `Pressure` en `variables/__init__.py` es **`bar`**, no `Pa` | Tags creados por HMI/`create_tag(..., variable="Pressure")` sin `unit` caen en `bar`. iDetectFugas pide `Pa` en `ProcessType` |
| **TU-F5** | Media | Alias | No existe `kg/s` en `VARIABLES`; el símbolo canónico es `kg/sec` | UI de producto muestra `kg/s`. `Units.read_by_unit("kg/s")` → `None` → `Tags.create` falla con “unit not exist” |
| **TU-F6** | Media | Upgrade | No hay migración “código SI vs fila existente” | Al actualizar iDetectFugas, si el código cambia `Pa` y la fila ya es `bar`, **gana la BD**. El motor no se realinea |
| **TU-F7** | Baja | `Tags.create` | Rama “name already exists” hace `put` de unidades y devuelve mensaje de data type | Código muerto/engañoso; el `put` sí se ejecuta |
| **TU-F8** | Baja | Seed historiador | `__init_default_variables_schema` comprueba `Units.name_exist(unit)` con el **símbolo** contra la columna **name** (`kg_sec` vs `kg/sec`) | En BD vacía suele funcionar porque `Pa`==`Pa`; en MassFlow el nombre interno es `kg_sec` |
| **TU-F9** | Info | `.f` | `filtered_tags` copia `unit`/`display_unit` del source | Correcto; hereda el mismo desfase display vs SI |

### Escenarios

| Escenario | Qué ocurre hoy | ¿Consistente? |
|---|---|---|
| A. Primera instalación, PG vacío | Tags de campo y de motor con unidad del `ProcessType` (`Pa`, `kg/sec`) | Sí |
| B. Restart, PG up, sin edición manual | Hydrate → duplicado CVT → mismas unidades | Sí |
| C. Restart, operador cambió `display_unit` a `bar` | Hydrate carga `bar` → create no recrea | Sí (display) / **No** para motores que asumen SI (TU-F3) |
| D. Restart, PG caído, `catalog.db` íntegro | Hydrate local → mismo que B/C | Sí en catálogo |
| E. Restart, CVT vacío y hydrate omitido (scope, error) | `create_tag` escribe defaults de código y **PUT** a PG/catálogo | **Pisa** ediciones (TU-F2) |
| F. Journal PENDING + cambio de `display_unit` | Drain etiqueta con unidad nueva | **Corrupción de historial** (TU-F1) |
| G. Upgrade de app, mismo tag, nueva unidad en código | Gana la fila existente | No hay “adoptar SI del producto” |

---

## 3. Pros y contras del diseño actual

### Pros

| # | Qué funciona | Por qué conviene |
|---|---|---|
| P1 | Dos capas `unit` / `display_unit` | El operador puede ver `bar` sin reentrenar el símbolo nativo del tag |
| P2 | Hydrate **antes** de `Machine.start` | Restart nominal no recrea el CVT desde código |
| P3 | `skip_validation` + duplicados | Tags `Manufacturer.Segment.Engine.leak` y `PI_01` no chocan con reglas HMI Site.Area |
| P4 | Seed de tabla `units` no pisa filas existentes | Evita colisiones `variable_id` en upgrades del catálogo de símbolos |
| P5 | `TagValue.unit` es FK por muestra | El esquema **permite** historial mixto; el agujero es el mapper, no la tabla |
| P6 | `_tag_put_fields` no borra FKs con `""` | Un set_tag incompleto no deja el tag sin unidad |
| P7 | Tags `.f` sincronizan unidad con el source | El filtrado wavelet no inventa otra magnitud |
| P8 | `resolve_units_for_variable` en `update_tag` | Cambio de variable en HMI no deja unidades ilegales |

### Contras

| # | Qué duele | Coste |
|---|---|---|
| C1 | SAF sin unidad en payload | Historial silencioso incorrecto tras editar display (TU-F1) |
| C2 | Upsert de unidades en bootstrap/reconcile | Viola el requisito “solo cambia si el operador lo pidió” cuando el hydrate falla (TU-F2) |
| C3 | Valor en CVT = display, motores leen display, código declara SI | Falsas alarmas / TKEO/CUSUM fuera de escala si display ≠ `ProcessType.unit` (TU-F3) |
| C4 | Default Pressure = `bar` | Asimetría con iDetectFugas (`Pa`) |
| C5 | Sin bit “unidad tocada por operador” | Imposible migrar SI en upgrade sin pisar planta |
| C6 | Tres copias (CVT, `catalog.db`, PG) con políticas distintas | Catálogo preserva OPC pero no unidades; PG hace PUT; SAF no lleva unidad |
| C7 | Alias `kg/s` vs `kg/sec` | Fallo al crear tag / schema UI (TU-F5) |

---

## 4. Dónde NO tocar (iDetectFugas)

No duplicar esta lógica en `app/`. El producto debe:

- Declarar SI en `ProcessType` (`Pa`, `kg/sec`, `kg/m3`, `m`, `%`, `adim`).
- Tras el fix de framework, **consumir `ProcessType.unit`** (o convertir explícitamente a SI) en el path de muestreo.

Cualquier parche en `venv/site-packages/automation` se pierde al reinstalar el wheel.

---

## 5. Recomendaciones (solo PyAutomation)

Prioridad P0 = rompe integridad de datos; P1 = contrato operativo; P2 = higiene.

| Pri | Cambio | Efecto |
|---|---|---|
| **P0** | Incluir `unit` (símbolo) en `PersistableRecord.tag_sample` y usarlo en `_lookup_unit` | SAF y TagValue coinciden con la unidad del instante |
| **P0** | `DataLogger.set_tag` / `persist_tag_to_local`: **no** actualizar `unit`/`display_unit` si la fila existe, salvo `update_tag` explícito | Restart no pisa al operador |
| **P1** | Suscripción SM: convertir a `ProcessType.unit` (SI del motor), no a `tag.display_unit` | NPW/PPA siempre ven Pa |
| **P1** | Convención documentada: `tag.unit` = nativo OPC / SI de almacenamiento; `display_unit` = HMI; historiador almacena **una** de las dos de forma explícita (preferible `tag.unit`) | Deja de mezclar display en TagValue |
| **P1** | Alias `kg/s` → `kg/sec` (y similares) en `VARIABLES` o en `read_by_unit` | UI producto y BD |
| **P2** | Flag `units_locked_by_operator` o comparar contra default de código solo en migración versionada | Upgrades de SI controlados |
| **P2** | Corregir rama `Tags.create` (mensaje / put) | Menos trampas |
| **P2** | Test de regresión: cold start Pa; restart preserva bar; journal PENDING + cambio display no reetiqueta | Cierra TU-F1/F2 |

### Política propuesta (fuente de verdad)

| Superficie | Quién gana |
|---|---|
| Primera inserción (no existe fila) | Código / `ProcessType.unit` |
| Fila existente, sin `update_tag` | BD / catálogo (operador) |
| `PUT /api/tags` | Operador |
| Muestra SAF | Unidad **congelada en el payload** |
| Motor de detección | Siempre SI del `ProcessType`, con conversión explícita |

---

## 6. Pruebas que faltan

No hay suite que cubra este contrato. Mínimo a añadir en `automation/tests/`:

1. Cold start: `create_tag_internal_process_type` + `Units.read_by_unit("Pa")` en `PI_01`.
2. Restart: hidratar tag con `display_unit=bar`, volver a bootstrap, assert `bar`.
3. SAF: encolar sample con tag en `Pa`, cambiar display a `bar`, drenar, assert `TagValue.unit == Pa` (tras P0).
4. `set_tag` sobre fila existente no cambia unidad.
5. `read_by_unit("kg/s")` (tras alias).

---

## 7. Veredicto

El framework **sí** puede crear tags en `Pa` al levantar la BD de cero, y **en el camino feliz** un restart no inventa otra unidad. Eso no equivale a “garantizado”:

1. SAF puede **re-etiquetar** valores si cambia `display_unit` con journal pendiente.
2. Bootstrap/reconcile **puede pisar** unidades si el CVT no viene de hydrate.
3. Display y SI del motor **no están atados**; un cambio manual de unidades rompe NPW/PPA aunque la fila sea “estable”.

Corregir TU-F1 y TU-F2 en PyAutomation **antes** de endurecer iDetectFugas. El inventario SI del producto está en la auditoría hermana 18.
