# Feature: catálogo local SQLite (espejo de configuración)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO |
| **Spec** | [11-CATALOG-SQLITE-LOCAL.md](../specs/11-CATALOG-SQLITE-LOCAL.md) |
| **Auditoría** | [AUDIT_CATALOG_SQLITE_LOCAL.md](../audits/AUDIT_CATALOG_SQLITE_LOCAL.md) |
| **Runbook operativo** | [catalog-sqlite-runbook.md](./catalog-sqlite-runbook.md) |
| **Audiencia** | Arquitectura · desarrollo · integración |
| **Estado** | Implementado en código (2026-08-21); soak 24 h pendiente |

---

## 1. Qué problema resuelve

Sin este feature, el catálogo (tags, alarmas, usuarios, OPC, máquinas, …) vivía **solo** en el historiador Peewee (PostgreSQL/MySQL o, antes, SQLite `app.db`). Si el remoto caía:

- Arranque con **CVT vacío**
- Login **bloqueado** (503 / error de BD)
- Cambios de configuración **imposibles** en el edge

El feature introduce un **espejo SQLite local** (`./db/catalog.db`) que permite operar, alarmar y autenticar en aislamiento, y sincronizar de forma asíncrona cuando el central vuelve.

---

## 2. Qué no es

| No confundir con | Archivo / componente | Rol |
|---|---|---|
| Historiador de series | Peewee `proxy` → PG/MySQL | `TagValue`, Events, Logs |
| Journal SAF | `./db/saf/<node_id>/journal.db` | Store-and-forward de históricos |
| Antiguo «SQLite como BD central» | `app.db` vía HMI | **Eliminado** de la configuración de historiador |

El espejo **no** guarda series temporales. Solo configuración.

---

## 3. Arquitectura

```
CRUD HMI / REST / DBManager
        │
        ▼
  ICatalogProvider (get_active)
   ├── RemoteCatalogProvider ──► Peewee proxy ──► PostgreSQL / MySQL
   └── LocalCatalogProvider  ──► catalog_proxy ──► ./db/catalog.db

CatalogReplicatorWorker (hilo OS, 30 s)
   push (edge→central) → pull (central→edge) → conflictos → Events / ALM.CATALOG.*
```

**Invariante:** el `proxy` Peewee del historiador **nunca** se rebindéa a SQLite. El espejo usa un segundo `SqliteDatabase` (`catalog_proxy`).

### Componentes (`automation/catalog/`)

| Módulo | Responsabilidad |
|---|---|
| `schema.py` | Orden FK; 18 tablas replicadas; `hmi_sessions` solo esquema |
| `local_db.py` / `models.py` | Apertura WAL+FK; clones Peewee |
| `versions.py` | Sidecar `catalog_versions` (local + historiador) |
| `provider.py` | Selección active = remoto si `is_db_connected()` |
| `conflict.py` | Timestamp gana; empate → remoto |
| `replicator.py` | Sync periódica fail-safe |
| `hydrate.py` / `auth.py` | Carga runtime + login local |
| `alarms.py` / `metrics.py` | ISA-18.2 + health O(1) |

---

## 4. Ciclo de vida

### Arranque

1. `bootstrap_local_catalog()` crea/abre `./db/catalog.db` y tablas.
2. `connect_to_db()` intenta el historiador (PG/MySQL).
3. Si falla (o aún no hay remota configurada): `seed_local_catalog_defaults()` siembra en el espejo lo mismo que el historiador en frío (variables, units, datatypes, roles, alarm types/states, usuario `system`), luego hidrata CVT (`load_db_to_*` / tags / alarmas / OPC) y asegura alarmas de sistema (`ALM.DB.*`, performance).
4. `create_system_user()` también opera contra el espejo cuando el historiador está caído.
5. `start_catalog_replicator()` arranca en hilo daemon; al conectar la remota más tarde, push/pull sincroniza el catálogo local hacia producción.

### Escritura

| Remoto vivo | Remoto caído |
|---|---|
| Persiste en historiador + espejo + `catalog_versions` | Solo espejo (`node_id=edge`, `version=now_ms()`), incl. `create_tag` / `create_alarm` / signup / roles |

Funnel principal: `DBManager` / loggers (`set_tag`, alarmas, machines, OPC, users/roles) + `mirror_historian_row` / `write_catalog_row` / `catalog.seed.persist_*`.

### Sync

Cada ~30 s, si hay remoto:

1. Push filas locales pendientes (orden padres → hijos, batch ≤ 100)
2. Pull filas remotas
3. Resolver conflictos (`conflict.resolve`)
4. Event resumen; alarmas si fallos/conflictos/local-only > 1 h

**Cold start:** un edge que arranca sin PG puede crear configuración operativa en `catalog.db` (defaults PyAutomation + máquinas/tags/alarmas de aplicación via `append_machine` / `create_alarm`); la primera vez que el historiador acepta conexión, el replicador empuja ese catálogo al central.

---

## 5. Autenticación degradada

- `core.login`: si el historiador está vivo, autentica contra PostgreSQL (Read-Through) y rellena el espejo local. Si el historiador está caído → `catalog.auth.login_local` (werkzeug `check_password_hash` sobre filas del espejo; rellena CVT users/roles).
- `core.signup` offline: usuario en memoria + fila en espejo (se push-ea al reconectar).

No se cambia el algoritmo de hash.

---

## 6. Observabilidad

### Health (`GET /api/health/system`)

| Clave | Significado |
|---|---|
| `CATALOG_SOURCE` | `local` \| `remote` |
| `CATALOG_SYNC_LAST_SUCCESS_UTC` | Último ciclo OK |
| `CATALOG_SYNC_PENDING_ROWS` | Pendientes de push |
| `CATALOG_SYNC_CONFLICT_COUNT` | Conflictos |
| `CATALOG_TABLES_COUNT` | Tablas replicadas (≥ 17) |

### Alarmas

| Tag / alarma | Condición |
|---|---|
| `ALM.CATALOG.SyncFailed` | ≥ 3 ciclos fallidos |
| `ALM.CATALOG.Conflict` | Conflictos activos |
| `ALM.CATALOG.LocalOnly` | Local-only > 1 h |

### HMI

Banner de modo degradado (historiador down): texto i18n indica **catálogo local, cambios no sincronizados**. Settings solo ofrece PostgreSQL/MySQL.

**Resiliencia ante outage:** si el historiador remoto cae, `CatalogReplicatorWorker` deja de leer/escribir el remoto, usa solo `catalog.db`, aplica backoff en reintentos y suprime `ALM.CATALOG.SyncFailed` durante los primeros 5 minutos. Al recuperarse la BD, sincroniza filas pendientes (push → pull) con resolución por timestamp.

---

## 7. Configuración

| Variable / archivo | Uso |
|---|---|
| `AUTOMATION_DB_TYPE` | Default `postgresql` (`sqlite` ya no bootea historiador) |
| `db/db_config.json` | Solo PG/MySQL para el central |
| `./db/catalog.db` | Automático; no configurable en HMI |
| `AUTOMATION_NODE_ID` | Fallback de `node_id` en versiones si el scope no está listo |

---

## 8. Tests

```bash
./venv/bin/python3 -m unittest automation.tests.test_catalog_sqlite -v
```

Cubre: orden FK, conflictos, upsert+versión, login local, rechazo API sqlite, HMI sin opción sqlite, existencia del runbook. Soak 24 h / multi-edge: skip + procedimiento en el runbook.

---

## 9. Límites conocidos

1. Primer arranque sin espejo ni remoto → CVT vacío hasta el primer pull.
2. Escrituras Peewee fuera del funnel pueden retrasar el espejo hasta el catch-up del replicator.
3. `hmi_sessions` no se replica (sesiones volátiles).
4. A+ de planta requiere soak CA-CATALOG-07…09 y 14.
