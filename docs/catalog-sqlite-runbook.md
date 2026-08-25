# Runbook: catálogo local SQLite y sincronización bidireccional

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO |
| **Spec** | [11-CATALOG-SQLITE-LOCAL.md](../specs/11-CATALOG-SQLITE-LOCAL.md) |
| **Audiencia** | Operador · ingeniero de procesos · soporte |

---

## 1. Qué es cada SQLite

| Archivo | Rol | ¿Configurable en HMI? |
|---|---|---|
| `./db/catalog.db` | Espejo de catálogo (tags, alarmas, users, OPC, …) | **No** — se crea solo |
| `./db/saf/<node>/journal.db` | Journal SAF de históricos | No (interno) |
| Historiador central | PostgreSQL o MySQL | Sí (Settings / Login) |

SQLite **ya no** es un motor de historiador central.

---

## 2. Modo degradado (catálogo local)

1. Si el LED de BD está en rojo, el edge opera con `catalog.db`.
2. Aviso flotante en la **parte superior del contenedor de la vista** (no empuja el layout). Se puede **arrastrar** por el asa (grip) si tapa un control; **no** se puede cerrar — desaparece solo al recuperar el historiador.
3. Login usa hashes del espejo local (CA-CATALOG-06).
4. Al reconectar, `CatalogReplicatorWorker` hace push/pull con catch-up cada 30 s y backoff progresivo (30→60→120→300 s) mientras el remoto sigue caído.
5. Durante outages **transitorios** (< 5 min) **no** debe aparecer `ALM.CATALOG.SyncFailed`; el catálogo local es la fuente de verdad y las operaciones CRUD siguen en el edge.
6. Logs esperados: `INFO Catalog sync skipped: remote historian unavailable` (una vez por outage), no `ERROR … connection already closed` en bucle.

---

## 3. Conflictos

Gana el timestamp más reciente (`catalog_versions.version`). Empate → gana el central. Queda Event «Catalog conflict resolved» y, si persiste, `ALM.CATALOG.Conflict`.

---

## 4. Alarmas

| Alarma | Acción |
|---|---|
| `ALM.CATALOG.SyncFailed` | Fallos **duros** (PG alcanzable) ≥ 5 min. El operador **reconoce** (ISA-18.2). Si el bit ya bajó, queda en RTN Unack hasta el ack; no se re-anuncia sola. |
| `ALM.CATALOG.OrphanRows` | **No** se enciende por reintentos de remap. Si alguna vez estuvo activa, el operador reconoce el RTN Unack. Cola restante: Rendimiento del nodo. |
| `ALM.CATALOG.Conflict` | Revisar Events; el central es la verdad |
| `ALM.CATALOG.LocalOnly` | Más de 1 h sin remoto — planificar reconexión |

Métricas: `GET /api/health/system` → `CATALOG_SOURCE`, `CATALOG_SYNC_*`.

---

## 5. Soak 24 h (CA-CATALOG-07…09, 14)

| ID | Procedimiento | Pasa si |
|---|---|---|
| **CA-CATALOG-07** | Sync activa 24 h; p95 `set_value` vs baseline | Sin degradación de hot path |
| **CA-CATALOG-08** | `catalog.db` con catálogo típico | Tamaño ≤ 500 MB |
| **CA-CATALOG-09** | Apagar espejo (solo remoto) y volver | Sin pérdida de catálogo |
| **CA-CATALOG-14** | Dos edges editan la misma entidad offline | Central resuelve por timestamp; ambos convergen |

Sin soak formal el veredicto de autonomía permanece **A−** (código verificado); **A+** pendiente de planta. Ver [AUDIT_CATALOG_SQLITE_LOCAL.md](../audits/AUDIT_CATALOG_SQLITE_LOCAL.md).

## 6. Controles desde Rendimiento del nodo

Si el sync se atasca o hay huérfanos de `tagsmachines`, no hace falta una vista de administración aparte:

| Síntoma | Acción en `/performance` | Notas |
|---|---|---|
| `CATALOG_LAST_SYNC` viejo / worker de catálogo caído | **Forzar sincronización** o **Reiniciar** CatalogReplicator | Admin/supervisor; cooldown 30 s en sync |
| `CATALOG_ORPHAN_ROWS > 0` sostenido | **Limpiar huérfanos** (edad 5/10/30/60 min) | Solo admin; pide checkbox. Puede borrar relaciones que aún se están resolviendo |

Detalle de roles, confirmación y Events: [node-performance-runbook.md](./node-performance-runbook.md).
