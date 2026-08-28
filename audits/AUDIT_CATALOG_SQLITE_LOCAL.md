# Auditoría: catálogo local SQLite — verificación post-spec 11

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Verificación de [specs/11-CATALOG-SQLITE-LOCAL.md](../specs/11-CATALOG-SQLITE-LOCAL.md) v1.3 + **paridad CRUD offline** + **integridad P0 units/tags al reinicio** (2026-08-21) |
| **Fecha** | 2026-08-21 (rev. integridad P0) · **aislamiento Bulkhead 2026-08-25** (sync por fila, sin rollback de tabla) · **controles `/performance` 2026-08-25** · **planta 2-edge 2026-08-25** ([AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md](./AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.md)) |
| **Evidencia** | Revisión estática + `automation.tests.test_catalog_sqlite` — **31 OK / 2 skipped** (soak planta) · PR [#16](https://github.com/know-ai/PyAutomation/pull/16) |
| **Baseline** | Spec 11 «propuesta»; historiador Peewee único; sin espejo de catálogo; SQLite configurable como motor central en HMI |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md](./AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md), [docs/catalog-sqlite.md](../docs/catalog-sqlite.md), [docs/catalog-sqlite-runbook.md](../docs/catalog-sqlite-runbook.md) |
| **Normas de referencia** | ISA-95 · ISA-18.2 · IEC 61508 (SIL-ready, sin certificación) · IEC 62443 |
| **Veredicto vigente** | **A autonomía de catálogo (CRUD offline)** · **A separación SAF/historiador** · **A integridad units/tags al reinicio (código)** · **A aislamiento de filas (Bulkhead, código)** · **A prevención binds cruzados (CA-CODE-01…05)** · **A DAQ por área (CA-DAQ-01)** · **A opcuaserver push-only (CA-OPC-PUSH-01)** · **C datos de partición tagsmachines en planta** (CA-CODE-06 pendiente de wipe+redeploy) · **A− sync planta** · **A HMI/API (sin SQLite central)** |
| **Clasificación** | Auditoría de verificación · catálogo edge · modo degradado · sync bidireccional · paridad offline · no-regresión de metadatos |

---

## 0. Respuesta directa

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

## Roles de las bases de datos SQLite (G-DISK-06)

| Base de datos | Propósito | `synchronous` | `temp_store` | Durabilidad |
|---|---|---|---|---|
| `journal.db` (`./db/saf/<node_id>/`) | Outbox SAF de muestras, alarmas, eventos, logs | **FULL** | MEMORY | Crítica (Plan A local) |
| `catalog.db` (`./db/catalog.db`) | Espejo de configuración, usuarios, OPC, máquinas | **NORMAL** (1) | MEMORY | No crítica; se reconstruye desde el historiador o seed |

El historiador remoto (PostgreSQL) **nunca** se sustituye por SQLite. Ver [AUDIT_DISK_DURABILITY.md](./AUDIT_DISK_DURABILITY.md).

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

## 2. Inventario de código (evidencia)

### 2.1 Paquete `automation/catalog/`

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

### 2.2 Enganches de producto (CRUD offline)

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

### 2.3 Tres SQLite — separación obligatoria

| Archivo | Motor | Propósito | ¿En HMI? |
|---|---|---|---|
| `./db/catalog.db` | Peewee `catalog_proxy` | Espejo de configuración | No |
| `./db/saf/<node>/journal.db` | `sqlite3` nativo SAF | Históricos store-and-forward | No |
| Historiador central | Peewee `proxy` → PG/MySQL | TagValue, Events, Logs, catálogo remoto | Sí |

**Invariante auditada:** el handle Peewee del historiador **no** se rebindéa a SQLite en runtime (rompe SAF / LoggerWorker). El espejo es un segundo database.

### 2.4 Superficie HMI correctamente gated (no catálogo)

| Ruta / feature | Comportamiento sin PG |
|---|---|
| Trends / datalogger / alarm summary / events / operational logs | Overlay `REMOTE_DB_DEPENDENT_PATHS` — **correcto** (series temporales) |
| Tags config, users, OPC clients, machines | **Operables** offline vía espejo |
| User management | Fuera de `dbDependentRoutes`; listado hidrata desde local |

---

## 3. Hallazgos

### Fortalezas

1. Arquitectura alineada con AUDIT_DB: segundo proxy, no rebind.
2. Fall-safe: mirror/write/mutations nunca levantan excepciones al hot path de adquisición.
3. Política de conflictos industrial: **remoto SoT** salvo dirty offline; auditable vía Events.
4. Superficie HMI limpia: SQLite ya no se presenta como historiador.
5. **Paridad CRUD offline** centralizada en `catalog/mutations.py` + seed helpers.
6. Cobertura unitaria: cold-start, OPC mapping, role_id, mutaciones, **seed no-overwrite**, **FK unit**, **grace**, dirty conflict.
7. Seed frío: edge vacío sin PG arranca con roles/units/datatypes/system user; edge poblado **no** se re-siembra.

### Defectos corregidos

| ID | Defecto | Causa raíz | Fix | Fecha |
|---|---|---|---|---|
| **CAT-BUG-01** | Rol de usuario (p. ej. GUEST→ADMIN) no sobrevivía reinicio offline | `apply_raw` prefería campo Peewee `role` (stale) sobre columna `role_id` | `rows._pick_raw_value` prioriza `column_name`; `update_user_role` escribe ambos | 2026-08-21 |
| **CAT-BUG-02** | Mapeo OPC de tags (p. ej. PI_02) se perdía al reiniciar | `update_tag` offline no persistía; re-seed de máquina podía vaciar OPC | `persist_tag_to_local` en update + merge OPC si payload vacío | 2026-08-21 |
| **CAT-BUG-03** | Cliente OPC no quedaba en tabla `opcua` sin PG | Persist solo si `logger.get_db()` | `_persist_opcua_client_local` siempre | 2026-08-21 |
| **CAT-BUG-04** | Upsert de filas con `timestamp` ISO fallaba en silencio | `TimestampField` no acepta `str` | coerce ISO→`datetime` en `rows._coerce` | 2026-08-21 |
| **CAT-BUG-05** | Deletes/updates de alarmas/tags/máquinas/LRS no tocaban espejo | Gates `is_db_connected` sin rama local | `mutations.py` + enganches | 2026-08-21 |
| **CAT-BUG-06** | **P0:** `unit_id` / metadatos de tags mutaban a defaults al reiniciar (bar→None / planta limpia) | **A+C+D:** seed podía upsert maestros; conflicto newest-wins empujaba espejo limpio; upsert aceptaba `unit` NULL/0 o string sin resolver | Seed vacío-only; `local_dirty` en `conflict.resolve`; `_resolve_tag_unit_fks` + no blank FK; grace 15 s | 2026-08-21 P0 |

### Investigación forense CAT-BUG-06 (hipótesis)

| Hipótesis | Veredicto | Evidencia / remedio |
|---|---|---|
| **A — Seed intrusivo** | **Confirmada (riesgo)** | `seed_variables_and_units` / datatypes / roles ahora **return 0** si la tabla tiene filas; alarmtypes/states siguen upsert seguros |
| **B — Provider/hydrate race** | **Mitigada** | `startup_grace_s=15` en bucle de fondo; connect/reconnect `cycle(force=True)` tras DB live |
| **C — Timestamp / clock skew** | **Confirmada** | Espejo limpio (`conflict_resolved=True` o no dirty) **siempre cede al remoto**; solo dirty+versión mayor gana local |
| **D — FK unit string→id** | **Confirmada** | `_resolve_tag_unit_fks` + `ensure_unit_symbol`; `_update_instance` ignora NULL/0 en FK de tags; no reasigna `variable_id` de units |

### Gaps / riesgos residuales

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

## 4. Matriz de paridad offline (tablas §4.1)

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

## 5. Veredicto

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

## 6. Cómo reproducir evidencia

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

### Checklist CA planta (integridad P0)

1. **Offline bar→baz:** apagar PG; cambiar unidad de un tag a `baz`; reiniciar servicio sin remoto → tag sigue en `baz`.
2. **Online estable:** PG con `baz`; reiniciar → sin mutación; logs sin merges anómalos.
3. **Conflicto dirty:** offline `alfa` vs remoto `beta` → gana dirty/timestamp; otras filas intactas.
4. **Idempotencia:** 10 reinicios con/sin remoto → dump de `tags` idéntico.

Documentación de producto: [docs/catalog-sqlite.md](../docs/catalog-sqlite.md).  
Operación: [docs/catalog-sqlite-runbook.md](../docs/catalog-sqlite-runbook.md).  
Controles en caliente (forzar sync / limpiar huérfanos): [docs/node-performance-runbook.md](../docs/node-performance-runbook.md) y vista `/performance`.  
PR: [know-ai/PyAutomation#16](https://github.com/know-ai/PyAutomation/pull/16).
