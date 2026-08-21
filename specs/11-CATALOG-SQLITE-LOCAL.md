# Documento 11: Catálogo local espejo (SQLite edge + sincronización bidireccional)

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 2026-08-21 |
| **Producto** | PyAutomationIO (`automation/` + HMI React) |
| **Estado** | **Propuesta** — diseño A+; implementación pendiente |
| **Complementa** | [01-MULTI-EDGE-ARCHITECTURE.md](./01-MULTI-EDGE-ARCHITECTURE.md), [09-OPC-QUALITY-AND-DEGRADED-STARTUP.md](./09-OPC-QUALITY-AND-DEGRADED-STARTUP.md), [AUDIT_DB.md](../audits/AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](../audits/AUDIT_STORE_AND_FORWARD.md) |
| **Normas** | ISA-95 (Nivel 2 ↔ 3) · IEC 61508 (SIL-ready, no certificación) · ISA-18.2 · IEC 62443 |
| **Audiencia** | Arquitectura de software · ingeniería de procesos · operaciones OT |
| **Filosofía** | El edge debe ser autónomo por diseño: opera, alarme y autentique aunque el mundo exterior se desvanezca. La sincronización con el central es un proceso de fondo, nunca una dependencia. |

---

## Índice

| § | Sección |
|---|---|
| 1 | [Objetivo](#objetivo) |
| 2 | [Principios](#principios) |
| 3 | [Arquitectura](#arquitectura) |
| 4 | [Modelo de datos](#modelo) |
| 5 | [Estrategia de sincronización](#sincronizacion) |
| 6 | [Autenticación y seguridad](#seguridad) |
| 7 | [Performance y no bloqueo](#performance) |
| 8 | [Monitoreo y alarmas](#monitoreo) |
| 9 | [Criterios de aceptación](#criterios) |
| 10 | [Plan de implementación](#plan) |
| 11 | [Veredicto objetivo](#veredicto) |

---

## 1. Objetivo

<a id="objetivo"></a>

Dotar a PyAutomationIO de un **catálogo local espejo en SQLite** en cada edge, con sincronización bidireccional asíncrona hacia PostgreSQL central, de modo que el nodo pueda **arrancar, adquirir, alarmar y autenticar** sin depender del historiador/catálogo remoto.

**Dentro de alcance**

1. Abstracción `ICatalogProvider` (local SQLite / remoto PostgreSQL).
2. Worker de replicación bidireccional con resolución de conflictos.
3. Hidratación de CVT, alarmas, OPC, máquinas y usuarios desde el espejo local.
4. Autenticación con fallback local en modo degradado.
5. Métricas, alarmas `ALM.CATALOG.*` y banner HMI.

**Fuera de alcance:** rediseño del SAF de históricos; certificación SIL formal; dump completo periódico del catálogo (solo diferencial).

---

## 2. Principios

<a id="principios"></a>

| Principio | Aplicación |
|---|---|
| **Autonomía del edge** | Arranque, adquisición, alarmas y login sin PostgreSQL; el espejo local es fuente de verdad en aislamiento |
| **Sincronización asíncrona** | Replicación en hilo OS dedicado; no interfiere con el hot path (1 Hz – 100 Hz) |
| **Consistencia eventual** | En partición ambos lados pueden divergir; al reconectar, timestamps + prioridad de nodo → estado coherente + auditoría de conflictos |
| **Seguridad por diseño** | Hashes bcrypt/argon2 en local y central; login valida contra el espejo si el central no está |
| **Fallback transparente** | `ICatalogProvider` abstrae el origen; el resto del sistema no distingue SQLite vs PostgreSQL (SRP + DIP) |
| **S / O / L / I / D** | Un adaptador por fuente; worker y resolver extensibles; interfaz acotada al catálogo |

---

## 3. Arquitectura

<a id="arquitectura"></a>

### 3.1. Vista de alto nivel

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Edge Device (PyAutomationIO)                                               │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ICatalogProvider                                                   │   │
│  │    ├── LocalCatalogProvider (SQLite)                                │   │
│  │    └── RemoteCatalogProvider (PostgreSQL)                           │   │
│  └──────────────────────────────────┬──────────────────────────────────┘   │
│                                     │                                       │
│  ┌──────────────────────────────────▼──────────────────────────────────┐   │
│  │  CatalogReplicatorWorker (hilo OS dedicado)                         │   │
│  │  • Push / pull · conflictos · Events · heartbeat / versiones        │   │
│  └──────────────────────────────────┬──────────────────────────────────┘   │
│                                     │                                       │
│  ┌──────────────────────────────────▼──────────────────────────────────┐   │
│  │  CVT (memoria) · SAF (históricos) · Alarmas · OPC · HMI             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SQLite local (catálogo espejo)                                     │   │
│  │  tags · alarms · users · roles · opcua · machines · segment         │   │
│  │  + catalog_versions                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Replicación (TCP/IP)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Central (Historiador + Catálogo Maestro)                        │
│  tags · alarms · users · roles · opcua · machines · segment                 │
│  + catalog_versions                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2. Componentes

| Componente | Responsabilidad | SOLID |
|---|---|---|
| `ICatalogProvider` | CRUD unificado sobre catálogo (tags, alarmas, users, roles, OPC, machines) | D, I |
| `LocalCatalogProvider` | SQLite local (Peewee → `file:///db/catalog.db`) | L, S |
| `RemoteCatalogProvider` | PostgreSQL existente envuelto en la interfaz | L, S |
| `CatalogReplicatorWorker` | Sync bidireccional, conflictos y versionado | S, O |
| `CatalogVersionManager` | Timestamps de modificación (`catalog_version` por fila) | S |
| `ConflictResolver` | Política timestamp + prioridad de nodo | S, O |
| `DegradedModeCoordinator` | Banner degradado + fallback de autenticación | S, D |

---

## 4. Modelo de datos

<a id="modelo"></a>

### 4.1. Tabla `catalog_versions` (local y remoto)

```sql
CREATE TABLE catalog_versions (
    table_name VARCHAR(64) NOT NULL,
    row_id INTEGER NOT NULL,          -- PK de la fila correspondiente
    version BIGINT NOT NULL,          -- timestamp UNIX (ms) de última modificación
    node_id VARCHAR(64),              -- quién hizo el cambio (edge o central)
    conflict_resolved BOOLEAN DEFAULT false,
    PRIMARY KEY (table_name, row_id)
);
```

Cada fila modificada en tablas de catálogo debe tener entrada en `catalog_versions` con la última `version` y el `node_id` autor.

### 4.2. Tablas versionadas

`tags`, `alarms`, `users`, `roles`, `opcua`, `machines`, `segment`, etc.

Cada una lleva columna `version` (BIGINT) actualizada en INSERT/UPDATE a `now_ms()` (trigger SQLite/PostgreSQL o ORM).

---

## 5. Estrategia de sincronización

<a id="sincronizacion"></a>

### 5.1. Arranque sin remoto

1. `connect_to_db` falla → `LocalCatalogProvider` pasa a activo.
2. Hidratar CVT, alarmas, OPC, máquinas y usuarios desde SQLite (`load_cvt_from_local`, …).
3. Permitir login (autenticación local).
4. Banner HMI: «Modo degradado: operando con catálogo local. Cambios no sincronizados.»
5. `CatalogReplicatorWorker` en modo espera (polling cada 30 s).

### 5.2. Remoto disponible (ciclo periódico)

| Fase | Acción |
|---|---|
| **Detección** | `is_db_connected() == True` |
| **Push** (local → remoto) | Filas locales con `node_id == edge_id` más recientes o ausentes en remoto; marcar `conflict_resolved` |
| **Pull** (remoto → local) | Filas remotas con `version > local_version` no originadas por el mismo edge |
| **Conflictos** | Gana timestamp más reciente; empate → gana remoto; Event de conflicto con detalle |
| **Auditoría** | Event resumen por ciclo (p. ej. «5 pushed, 12 pulled, 1 conflict») |

### 5.3. Modificaciones offline

| Caso | Comportamiento |
|---|---|
| Crear/editar tag o alarma | Persistir en SQLite con `node_id = edge_id`, `version = now_ms()`; push al reconectar |
| Cambio de contraseña / usuarios | Hash local; réplica al remoto; conflicto por nombre → política de timestamp |

---

## 6. Autenticación y seguridad

<a id="seguridad"></a>

| Tema | Regla |
|---|---|
| Almacenamiento | bcrypt/argon2 en local y central; parámetros de hash compartidos vía configuración/env |
| Login | Intentar proveedor activo; si remoto caído → autenticar contra local |
| Réplica de usuarios/roles | Misma vía `version` que el resto del catálogo |
| Rotación | Cambio de hash en central se refleja en local en el siguiente pull |

---

## 7. Performance y no bloqueo

<a id="performance"></a>

| Requisito | Diseño |
|---|---|
| Hot path | Worker en hilo OS nativo (no greenlet); no bloquea hub gevent |
| SQL local | O(1) por PK o índices; hidratación solo en arranque/reconexión |
| Incremental | Solo filas modificadas (diferencial); sin dump completo |
| Batch | Hasta 100 filas por lote |
| Rate limit | Máximo cada `sync_interval` (default **30 s**); idle si no hay cambios |

---

## 8. Monitoreo y alarmas

<a id="monitoreo"></a>

### 8.1. Métricas (`/api/health/system`)

| Métrica | Significado |
|---|---|
| `CATALOG_SOURCE` | `local` \| `remote` |
| `CATALOG_SYNC_LAST_SUCCESS_UTC` | Último ciclo OK |
| `CATALOG_SYNC_PENDING_ROWS` | Filas locales pendientes de push |
| `CATALOG_SYNC_CONFLICT_COUNT` | Conflictos pendientes |

### 8.2. Alarmas ISA-18.2

| Alarma | Condición |
|---|---|
| `ALM.CATALOG.SyncFailed` | 3 fallos consecutivos de sync |
| `ALM.CATALOG.Conflict` | Conflictos sin resolver tras 3 ciclos |
| `ALM.CATALOG.LocalOnly` | Modo degradado activo > 1 h |

Cada transición de estado de sync se registra en Events.

---

## 9. Criterios de aceptación

<a id="criterios"></a>

| ID | Criterio |
|---|---|
| CA-CATALOG-01 | El edge arranca y opera sin PostgreSQL (catálogo local) |
| CA-CATALOG-02 | Cambios en modo degradado (tag, alarma, password) se replican al reconectar |
| CA-CATALOG-03 | Cambios en el central mientras el edge estaba offline llegan al edge al reconectar |
| CA-CATALOG-04 | Conflictos se resuelven por timestamp más reciente y se registran en Events |
| CA-CATALOG-05 | Banner de modo degradado en HMI cuando la fuente activa es local |
| CA-CATALOG-06 | Autenticación local funciona en modo degradado |
| CA-CATALOG-07 | Sync no degrada p95 de `set_value` (soak 24 h con sync activa) |
| CA-CATALOG-08 | SQLite local ≤ 500 MB con catálogo típico |
| CA-CATALOG-09 | Rollback a remoto-only posible sin pérdida de datos |
| CA-CATALOG-10 | Alarmas y eventos ante fallos de sincronización |

Tests previstos: unitarios (conflictos, versionado), integración push/pull, soak 24 h, revisión HMI del banner.

---

## 10. Plan de implementación

<a id="plan"></a>

| Fase | Entregable | Prioridad | Estimación | Estado |
|---|---|---|---|---|
| 1 | Modelo `catalog_versions` + migración SQL (ambos lados) | P0 | 1 d | Pendiente |
| 2 | `ICatalogProvider` + adaptadores local/remoto | P0 | 1.5 d | Pendiente |
| 3 | `CatalogReplicatorWorker` (push/pull, conflictos) | P0 | 2 d | Pendiente |
| 4 | Arranque / hidratación local + modo degradado | P0 | 1 d | Pendiente |
| 5 | Autenticación local (login con fallback) | P1 | 0.5 d | Pendiente |
| 6 | HMI: banner, métricas, alarmas | P1 | 1 d | Pendiente |
| 7 | Tests unitarios e integración | P0 | 1.5 d | Pendiente |
| 8 | Soak 24 h planta (CA-CATALOG-01…10) | P0 validación | 1 d | Pendiente |
| 9 | Documentación y runbook | P2 | 0.5 d | Pendiente |

---

## 11. Veredicto objetivo

<a id="veredicto"></a>

| Dimensión | Hoy | Meta post-impl |
|---|---|---|
| Autonomía del edge (catálogo / login sin PG) | Dependiente del remoto para catálogo completo | **A− / A** |
| Disponibilidad adquisición + SAF | **A−** (ya robusta) | Mantener (sync fuera del hot path) |
| Consistencia catálogo multi-nodo | Unidireccional / central | Consistencia eventual + auditoría de conflictos |
| Operabilidad HMI en partición | Banner BD historiador (spec 09/10) | Banner + fuente `local` + métricas `CATALOG_*` |

**Conclusión:** esta especificación posiciona el edge como nodo autónomo con réplica de catálogo de grado industrial. El hot path de adquisición permanece intacto; la sync es proceso de fondo con trazabilidad ISA-18.2.
