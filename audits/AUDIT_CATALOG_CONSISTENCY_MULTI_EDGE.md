# Auditoría de planta: consistencia de catálogo multi-edge

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/catalog`) + historiador PostgreSQL + `catalog.db` por edge |
| **Alcance** | Integridad referencial y partición de `tags`, `machines`, `tagsmachines`, `alarms`, `opcua`, `pending_rows` |
| **Fecha de ejecución** | 2026-08-25 19:15–19:20 UTC |
| **Entorno** | Planta Supe · 2 edges reales · historiador compartido `idetect_db` @ `192.168.1.95:5432` |
| **JSON crudo** | [AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.json](./AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.json) |
| **Complementa** | [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) |
| **Veredicto de esta corrida** | FK nulas/huérfanas **A** (0 filas). Partición `tagsmachines` **C**. Catálogo local Linea2 **B−**. **No es A+ de planta.** |
| **Clasificación** | Auditoría de datos · evidencia de planta · no es spec |

---

## 0. Respuesta directa

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

## 1. Dónde se midió

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

## 2. Conteos (AUD-05)

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

## 3. Hallazgos (prioridad ops)

### CAT-XAREA-01 — binds cruzados (crítico de partición)

En PostgreSQL **no hay FK rota**: `tag_id` y `machine_id` existen. El fallo es de **partición**: tres tags de Linea2 apuntan a la máquina **DAQ-1000**, que vive en **Linea1**.

| tagsmachines.id | Tag | Tag area / owner | Máquina | Machine area |
|---|---|---|---|---|
| 4 | `Supe.Linea2.FI_02` (id 104) | Linea2 / edge-linea2 | DAQ-1000 (id 12) | **Linea1** |
| 8 | `Supe.Linea2.PI_02` (id 122) | Linea2 / edge-linea2 | DAQ-1000 (id 12) | **Linea1** |
| 9 | `Supe.Linea2.DI_02` (id 106) | Linea2 / edge-linea2 | DAQ-1000 (id 12) | **Linea1** |

Los tres binds de Linea1 (`FI_02`/`PI_02`/`DI_02` → DAQ-1000) están bien: tag y máquina son Linea1. Están en el `catalog.db` de .80.

**Causa probable:** una sola fila `machines` DAQ-1000 (id=12, area=Linea1). No hay DAQ de Linea2. Quien enlazó los tags de Linea2 reutilizó la máquina de la otra línea.

### CAT-SCOPE-01 — fugas en catalog.db de Linea2

`machines` en .81:

| id | name | area |
|---|---|---|
| 7, 8, 9, 10, 11 | Supe.Linea2.{LDS,PPA,NPW,PFM,Observer} | Linea2 (correcto) |
| **12** | **DAQ-1000** | **Linea1** (fuga) |
| **6** | **OPCUAServer** | **Linea1** (fuga) |

El replicador arrastró padres Linea1 para resolver el bind cruzado. Linea1 (.80) **no** tiene máquinas Linea2.

### CAT-PENDING-01 — pending en Linea2

`pending_rows` (.81): una fila `tagsmachines` identity `104|12`, retries=1, first_seen `2026-08-25 19:15:22Z`, payload remoto id=4 (`FI_02`→DAQ-1000). Los binds 8 y 9 no están en pending ahora (pueden haberse descartado en ciclos previos).

`tagsmachines` local de Linea2 = **0**. El edge no puede aplicar el enlace sin romper la partición, o lo aplaza porque el padre no es de su área.

### CAT-VER-01 — sidecar `catalog_versions`

| Sitio | `catalog_versions` de tagsmachines |
|---|---|
| Remoto | Solo row_id **4, 8, 9** (Linea2). **Faltan 1, 2, 3** (Linea1, que sí existen en la tabla) |
| Local .80 | row_id **1, 2, 3** (alineado con las filas reales de Linea1) |
| Local .81 | row_id **1, 2, 3** con los **mismos version timestamps** que el remoto 4/8/9 — remap de PK incorrecto |

---

## 4. Qué está sano (no tocar)

- 0 `tag_id`/`machine_id` NULL o =0 en `tagsmachines`.
- 0 alarms huérfanas.
- 0 tags con `area` distinta del `nodes.area` de su `owner_node`.
- 0 `unit_id` huérfano; 0 `opcua.owner_node` huérfano.
- Tags 80/80 y alarms 25/24 por línea, espejo perfecto contra el remoto filtrado por área.
- Linea1: `tagsmachines` local ≡ remoto de esa línea.

---

## 5. Plan de corrección (ops, no ejecutado en esta corrida)

Orden sugerido. Hacer backup de PG y de ambos `catalog.db` antes.

1. **Decidir el modelo DAQ por línea.** Opciones: (A) crear `DAQ-1000` (u otro nombre) con `area=Linea2` y rebind 4/8/9 a esa máquina; (B) si Linea2 no debe historizar esos tres tags en DAQ, borrar 4/8/9.
2. **No** dejar tags Linea2 colgando de `machine_id=12`.
3. En edge-linea2: quitar máquinas `DAQ-1000` y `OPCUAServer` de area Linea1 (o forzar sync limpio tras el paso 1).
4. Reconstruir `catalog_versions` de `tagsmachines` para ids 1–3 en el remoto (hoy no existen).
5. Volver a correr esta auditoría. Criterio de cierre: 0 cross-area, pending_rows=0 en ambos edges, Δ tagsmachines=0 por área, versions 1:1 con la tabla.

No usar «Vaciar cola SAF» ni `drop_orphans` como atajo: aquí el problema es **catálogo mal particionado**, no journal.

---

## 6. CA de la auditoría (proceso, no de los datos)

| ID | Criterio | Evidencia |
|---|---|---|
| CA-AUDIT-01 | Tablas críticas | `tagsmachines`, `alarms`, `pending_rows` |
| CA-AUDIT-02 | tag_id NULL | 0 filas |
| CA-AUDIT-03 | FK inválida | 0 huérfanas; 3 cross-area documentadas |
| CA-AUDIT-04 | Remoto vs cada local | Tabla §2 |
| CA-AUDIT-05 | JSON | `AUDIT_CATALOG_CONSISTENCY_MULTI_EDGE.json` |
| CA-AUDIT-06 | &lt; 5 min | PG + SFTP WAL + SQLite ≈ 2 s de queries + copia |

---

## 7. Veredicto

**No A+.** El historiador no tiene filas huérfanas clásicas (AUD-01/02/03 numéricos en cero). Sí tiene **tres bindings que rompen el contrato multi-edge** (un tag de Linea2 escrito contra una máquina de Linea1). Eso explica el pending en .81 y las dos máquinas Linea1 filtradas hacia el catálogo de Linea2.

Cierre A de **datos** cuando CAT-XAREA-01, CAT-SCOPE-01, CAT-PENDING-01 y CAT-VER-01 estén en cero en una segunda corrida.

---

## 8. Corrección de raíz en código (2026-08-25, post-auditoría)

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

## 9. Recorrida 2026-08-25 19:50 UTC (logs del usuario)

Contraste de `docker logs idetectfugas` contra PG `idetect_db` y ambos `catalog.db` (WAL copiado).

### Qué cambió vs 19:15

| Check | 19:15 | 19:50 |
|---|---|---|
| Binds cruzados en PG | 3 (Linea2→DAQ Linea1) | **0** |
| tagsmachines PG | 6 | **3** (solo Linea1 FI/PI/DI_02→DAQ-1000) |
| tagsmachines .80 | 3 | 3, mismos tag_id 28/46/30 |
| tagsmachines .81 | 0 | 0 |
| Máquinas Linea1 en .81 | DAQ-1000 + OPCUAServer | **igual** |
| DAQ de Linea2 | no existe | **sigue sin existir** |
| opcuaserver PG | (no medido como problema) | **3999** nodos |

### Interpretación de los logs

1. **`.81` `Cannot bind … cross-area`** — la guarda de código **está activa y hace lo correcto**. El operador mapeó tags Linea2 a `DAQ-1000` (`area=Linea1`). HMI lo ofrece porque esa máquina **sigue en el catalog.db de Linea2**. En memoria `StateMachine.area` se pisa con `NODE_AREA`, por eso `subscribe_to` llega a `bind_tag`; Peewee lee `machines.area=Linea1` y rechaza. El texto `Remote historian unreachable during bind_tag` es **una etiqueta falsa** (`log_historian_link_issue` sobre `CrossAreaBindError`). PG está vivo (PLC81 conectó; hay writes).
2. **`.80` `IntegrityError … tag_id null` keys `28|12` `46|12` `30|12`** — esas tres filas **ya existen y están bien** en PG y en `.80`. `catalog_versions` local las tiene `conflict_resolved=0`; el remoto **no versiona** `tagsmachines`. Cada ciclo reintenta PUSH, remapea FKs a null e INSERT `(serial, null, …)`. No hay filas nulas persistidas (el INSERT falla).
3. **ambos `opcuaserver` skipped / cycle timeout 10 s** — la tabla no es “el servidor OPC”; es el **address space** (1937 nodos en `.80`, 2345 en `.81`, 3999 en PG). El cliente OPC (`opcua`: PLC80 / PLC81) está OK.

### Qué no hacer

No borrar las 3 filas de `tagsmachines` de Linea1. No truncar `tags`. No “arreglar” el bind de Linea2 apuntando otra vez a `DAQ-1000`.

### Qué sí hacer en planta

Crear una máquina DAQ **con `area=Linea2`**, bindear FI/PI/DI_02 a esa máquina, y quitar del `catalog.db` de `.81` las dos máquinas Linea1. El spam IntegrityError/timeout se cierra en código (no rebind).

---

## 10. Código 2026-08-25 — DAQ por nodo y opcuaserver push-only

Tras wipe limpio, el mapeo de tags **sí** crea el poller correcto **si** está este código:

| ID | Cambio | Evidencia |
|---|---|---|
| **CA-DAQ-01** | Nombre `{area}.DAQ-{ms}` (p. ej. `Linea1.DAQ-1000` ≠ `Linea2.DAQ-1000`). Unique global de `machines.name` se elimina en `ensure_schema`. Unique parcial `(area, name)` donde `area` no es nulo. Un scan time distinto en la misma línea sigue siendo otro poller (`Linea1.DAQ-200`). | `test_daq_node_scope.py` |
| **CA-OPC-PUSH-01** | `opcuaserver` ∈ `PUSH_ONLY_TABLES`: backup al PG, **cero pull** al `catalog.db` local (ni LWW remoto). Scope de nombre `{area}_…` si algún ciclo residual lee remoto. | `test_opcuaserver_is_push_only_never_pulled` |

Requiere **rebuild del wheel** en ambos edges. Un wipe con el 2.8.1 viejo **repite** la colisión `DAQ-1000`.

---

## 11. Corrida 2026-08-25 22:36 UTC — .80 vs .81 (rendimiento + CATALOG.*)

| Campo | Valor |
|---|---|
| **Imagen** | `idetectfugas/app:3.0.0` healthy en ambos (~35 min) |
| **PG** | `idetect_db` · 0 binds cruzados · `Linea1.DAQ-1000` (id 14) · `Linea2.DAQ-1000` (id 15) |
| **Canvas** | [node-perf-80-vs-81](/home/crivero/.cursor/projects/home-crivero-repo/canvases/node-perf-80-vs-81.canvas.tsx) |

### Plano A (proceso) — ambos bien

| | .80 | .81 |
|---|---:|---:|
| TagValue 15 min | 19 661 | 19 257 |
| ACQUISITION_READY | true | true |
| SAMPLE_LAG_MS | 0 | 0 |
| PLC | PLC80 22:01:44 | PLC81 22:14:23 |

### Plano B (sidecar) — .81 peor

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
