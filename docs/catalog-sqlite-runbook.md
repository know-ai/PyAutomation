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
4. Al reconectar, `CatalogReplicatorWorker` hace push/pull cada 30 s.

---

## 3. Conflictos

Gana el timestamp más reciente (`catalog_versions.version`). Empate → gana el central. Queda Event «Catalog conflict resolved» y, si persiste, `ALM.CATALOG.Conflict`.

---

## 4. Alarmas

| Alarma | Acción |
|---|---|
| `ALM.CATALOG.SyncFailed` | 3 ciclos fallidos — revisar red/PG |
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
