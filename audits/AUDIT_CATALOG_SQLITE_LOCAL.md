# Auditoría: catálogo local SQLite — verificación post-spec 11

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Verificación de [specs/11-CATALOG-SQLITE-LOCAL.md](../specs/11-CATALOG-SQLITE-LOCAL.md) v1.3 + **paridad CRUD offline** (2026-08-21) |
| **Fecha** | 2026-08-21 (rev. tarde: mutaciones offline + dual-write) |
| **Evidencia** | Revisión estática + `automation/tests/test_catalog_sqlite.py` — **18 OK / 2 skipped** (soak planta) |
| **Baseline** | Spec 11 «propuesta»; historiador Peewee único; sin espejo de catálogo; SQLite configurable como motor central en HMI |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md](./AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md), [docs/catalog-sqlite.md](../docs/catalog-sqlite.md), [docs/catalog-sqlite-runbook.md](../docs/catalog-sqlite-runbook.md) |
| **Normas de referencia** | ISA-95 · ISA-18.2 · IEC 61508 (SIL-ready, sin certificación) · IEC 62443 |
| **Veredicto vigente** | **A autonomía de catálogo (CRUD offline)** · **A separación SAF/historiador** · **A− sync** (A+ condicionado a soak 24 h / multi-edge planta) · **A HMI/API (sin SQLite central)** |
| **Clasificación** | Auditoría de verificación · catálogo edge · modo degradado · sync bidireccional · paridad offline |

---

## 0. Respuesta directa

| Escenario | ¿Qué hace PyAutomation **ahora** (2026-08-21 rev.)? | Spec | Grado |
|---|---|---|---|
| **Arranque sin PG/MySQL** | Abre siempre `./db/catalog.db`; seed frío (roles/units/datatypes/alarm meta/`system`); hidrata CVT/roles/users/OPC/alarmas/máquinas desde local | 11 | **A** |
| **CRUD de catálogo sin PG** | Crear/editar/borrar tags, alarmas, users/roles/password, OPC clients/server, máquinas + `tagsmachines`, LRS, nodes → `catalog.db` + versiones | 11 | **A** |
| **Historiador caído en runtime** | `CATALOG_SOURCE=local`; banner HMI; login/signup contra espejo; mutaciones locales; replicator espera 30 s | 11 | **A** |
| **Reconexión** | `CatalogReplicatorWorker` push→pull orden FK; conflictos por timestamp (empate → remoto); dual-write online mantiene espejo fresco | 11 | **A−** |
| **Operador elige SQLite como historiador** | **Rechazado** (HMI sin opción; API 400) | 11 CA-11 | **A** |
| **Journal SAF** | Intacta `./db/saf/.../journal.db`; **no** se mezcla con `catalog.db`; TagObservers se adjuntan sin PG | 11 + SAF | **A** |
| **Proxy Peewee historiador** | **No se rebindéa**; segundo `catalog_proxy` solo para el espejo | 11 + AUDIT_DB | **A** |

Cadena de arranque / sync:

```
__start_workers
  → bootstrap_local_catalog()          # siempre, WAL + FK
  → connect_to_db()                    # PG/MySQL; puede fallar
  → [si remoto down] seed_local_catalog_defaults + hydrate local
  → start_catalog_replicator()         # hilo OS, interval 30 s
       → si is_db_connected: push (padres→hijos) → pull → conflictos → Event
       → si no: sleep 30 s + ALM.CATALOG.LocalOnly (>1 h)
```

Mutaciones offline (capa única):

```
API / HMI / core / loggers
  → CVT / managers (memoria)
  → catalog.mutations.*  |  catalog.seed.persist_*_to_local  |  write_catalog_row
  → LocalCatalogProvider.upsert/delete + catalog_versions
  → [al reconectar] CatalogReplicatorWorker push
```

---

## 1. Matriz de criterios de aceptación (CA-CATALOG)

| ID | Criterio | Resultado | Evidencia primaria | Test |
|---|---|---|---|---|
| **CA-CATALOG-01** | Edge opera sin PG/MySQL (catálogo local) | **PASS** | Bootstrap + seed frío + hydrate + CRUD offline | `TestColdStartLocalSeed`, roundtrip |
| **CA-CATALOG-02** | Cambios degradados se push-ean al reconectar | **PASS** (diseño) | Dual-write + versiones locales + `CatalogReplicatorWorker._sync_table` push | Unitario parcial; planta pending |
| **CA-CATALOG-03** | Cambios central → edge en pull | **PASS** (diseño) | Pull en replicator; winner remoto en empate | Unitario conflictos |
| **CA-CATALOG-04** | Conflictos por timestamp + Events | **PASS** | `conflict.resolve`; `persist_system_event` | `TestConflictResolver` |
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
| **CA-CATALOG-15** *(nuevo)* | Paridad CRUD offline ≡ online (tablas de catálogo) | **PASS** (código) | `catalog/mutations.py` + enganches core/loggers | `test_offline_catalog_mutations_parity` + OPC/role |

**Suite:** `python3 -m unittest automation.tests.test_catalog_sqlite -v` — **20 tests: 18 OK, 2 skipped** (2026-08-21).

---

## 2. Inventario de código (evidencia)

### 2.1 Paquete `automation/catalog/`

| Módulo | Rol | Estado |
|---|---|---|
| `schema.py` | Registro ordenado 19 tablas; `REPLICATED_TABLES` (18); skip filas `hmi_sessions` | ✅ |
| `local_db.py` | `SqliteDatabase` + `catalog_proxy`; WAL; FK | ✅ |
| `models.py` | Clones Peewee; FK → columnas escalares; `CatalogVersionsLocal` | ✅ |
| `rows.py` | `row_to_raw` / `apply_raw` / `upsert_model`; **prioriza `column_name`** (`role_id` vs `role`); coerce ISO→datetime | ✅ |
| `versions.py` / `dbmodels/catalog_versions.py` | Sidecar local + historiador; `row_id VARCHAR(64)` | ✅ |
| `provider.py` | `get_active()` = remoto si `is_db_connected()` else local | ✅ |
| `local_provider.py` / `remote_provider.py` | CRUD dict por tabla | ✅ |
| `conflict.py` | Gana timestamp; empate → remoto | ✅ |
| `replicator.py` | `BaseWorker` OS thread; batch 100; interval 30 s | ✅ |
| `hydrate.py` / `auth.py` | Hidratación CVT/users/OPC/alarmas; login local; skip tags `active=False` y alarmas OOS | ✅ |
| `bootstrap.py` | `bootstrap_local_catalog`, `mirror_historian_row`, `write_catalog_row` | ✅ |
| `seed.py` | Seed frío + `persist_tag/alarm/machine/opcua_client_to_local` (merge OPC al re-sembrar) | ✅ |
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
3. Política de conflictos simple y auditable (timestamp + empate remoto).
4. Superficie HMI limpia: SQLite ya no se presenta como historiador.
5. **Paridad CRUD offline** centralizada en `catalog/mutations.py` + seed helpers.
6. Cobertura unitaria ampliada: cold-start seed, OPC mapping, role_id, mutaciones LRS/tagsmachines/OPC server.
7. Seed frío: edge vacío sin PG arranca con roles/units/datatypes/system user.

### Defectos corregidos en esta revisión (2026-08-21)

| ID | Defecto | Causa raíz | Fix |
|---|---|---|---|
| **CAT-BUG-01** | Rol de usuario (p. ej. GUEST→ADMIN) no sobrevivía reinicio offline | `apply_raw` prefería campo Peewee `role` (stale) sobre columna `role_id` | `rows._pick_raw_value` prioriza `column_name`; `update_user_role` escribe ambos |
| **CAT-BUG-02** | Mapeo OPC de tags (p. ej. PI_02) se perdía al reiniciar | `update_tag` offline no persistía; re-seed de máquina podía vaciar OPC | `persist_tag_to_local` en update + merge OPC si payload vacío |
| **CAT-BUG-03** | Cliente OPC no quedaba en tabla `opcua` sin PG | Persist solo si `logger.get_db()` | `_persist_opcua_client_local` siempre |
| **CAT-BUG-04** | Upsert de filas con `timestamp` ISO fallaba en silencio | `TimestampField` no acepta `str` | coerce ISO→`datetime` en `rows._coerce` |
| **CAT-BUG-05** | Deletes/updates de alarmas/tags/máquinas/LRS no tocaban espejo | Gates `is_db_connected` sin rama local | `mutations.py` + enganches |

### Gaps / riesgos residuales

| ID | Hallazgo | Severidad | Mitigación |
|---|---|---|---|
| **CAT-R1** | Recursos Peewee residuales fuera de funnels principales podrían atrasar espejo hasta el pull | Baja *(antes Media)* | Mutations + dual-write en funnels; inventario residual menor |
| **CAT-R2** | Soak 24 h / tamaño / multi-edge no ejecutados | Alta (para A+) | Runbook §5; tests `@skip` |
| **CAT-R3** | Banner usa `connected === false`, no lee `CATALOG_SOURCE` del health system | Baja | Texto i18n ya habla de catálogo local; mejora opcional |
| **CAT-R4** | Primer arranque frío: seed defaults + vacío de tags de proceso hasta que la app/plant los cree | Info | Esperado; seed + `persist_*` al crear máquinas/tags |
| **CAT-R5** | Históricos (TagValue / AlarmSummary / Events) **no** son catálogo — siguen requiriendo PG o SAF | Info | Fuera de alcance spec 11; no confundir con CRUD de configuración |

---

## 4. Matriz de paridad offline (tablas §4.1)

| Tabla | Create | Update | Delete / soft | Hydrate | Sync push |
|---|---|---|---|---|---|
| datatypes / variables / units / roles / alarmtypes / alarmstates | seed | — | — | sí | sí |
| manufacturer / segment / accesstype | ensure en mutaciones | — | — | vía FK | sí |
| users | signup offline | role / password | N/A producto | sí | sí |
| tags | sí | sí | soft `active=False` | skip inactive | sí |
| alarms | sí | sí | soft OOS | skip OOS | sí |
| opcua | sí | sí | hard local | sí | sí |
| opcuaserver | sí | access_type | — | vía logger/API | sí |
| nodes | register local | — | — | — | sí |
| machines | sí | attrs | — | payloads | sí |
| tagsmachines | bind | sample_override | unbind | (runtime) | sí |
| linearreferencinggeospatial | sí | sí | hard | list/interpolate | sí |
| hmi_sessions | local only | — | — | — | **no** (by design) |

---

## 5. Veredicto

| Dimensión | Nota | Condición A+ |
|---|---|---|
| Autonomía de catálogo (arranque + login + **CRUD offline**) | **A** | Soak CA-01 en planta con catálogo poblado y mutaciones reales |
| Sync bidireccional / conflictos | **A−** | Soak CA-02/03/04/14 |
| Separación SAF / historiador / espejo | **A** | — |
| HMI + API sin SQLite central | **A** | — |
| Observabilidad (`CATALOG_*`, `ALM.CATALOG.*`) | **A−** | Validar alarmas en soak |

**Veredicto global:** **A** en autonomía de configuración edge; **A−** global solo por soak de planta pendiente (CA-07…09, 14). El bloqueo funcional «no se puede configurar sin PG» queda **cerrado en código**.

---

## 6. Cómo reproducir evidencia

```bash
cd github/PyAutomation
PYTHONPATH=. python3 -m unittest automation.tests.test_catalog_sqlite -v
# Esperado: Ran 20 tests … OK (skipped=2)
```

Tests clave de esta revisión:

- `TestColdStartLocalSeed.test_seed_defaults_and_system_user`
- `TestColdStartLocalSeed.test_persist_opcua_client_and_preserve_tag_opc_mapping`
- `TestColdStartLocalSeed.test_user_role_update_prefers_role_id_column`
- `TestColdStartLocalSeed.test_offline_catalog_mutations_parity`
- `TestHmiCatalogSurfaces.test_user_management_not_remote_db_gated`

Documentación de producto: [docs/catalog-sqlite.md](../docs/catalog-sqlite.md).  
Operación: [docs/catalog-sqlite-runbook.md](../docs/catalog-sqlite-runbook.md).
