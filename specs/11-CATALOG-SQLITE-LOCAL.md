# Documento 11: Catálogo local espejo (SQLite edge + sincronización bidireccional)

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 1.3 |
| **Fecha** | 2026-08-21 |
| **Producto** | PyAutomationIO (`automation/` + HMI React) |
| **Estado** | **Propuesta** — diseño A+; implementación pendiente |
| **Complementa** | [01-MULTI-EDGE-ARCHITECTURE.md](./01-MULTI-EDGE-ARCHITECTURE.md), [09-OPC-QUALITY-AND-DEGRADED-STARTUP.md](./09-OPC-QUALITY-AND-DEGRADED-STARTUP.md), [AUDIT_DB.md](../audits/AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](../audits/AUDIT_STORE_AND_FORWARD.md) |
| **Normas** | ISA-95 · IEC 61508 (SIL-ready, no certificación) · ISA-18.2 · IEC 62443 |
| **Audiencia** | Arquitectura de software · ingeniería de procesos · operaciones OT |
| **Filosofía** | El edge debe ser autónomo por diseño: opera, alarme y autentique aunque el mundo exterior se desvanezca. La sincronización con el central es un proceso de fondo, nunca una dependencia. |

---

## Aclaración crítica: SQLite en la HMI

<a id="aclaracion-sqlite"></a>

| Contexto | Situación actual | Cambio requerido |
|---|---|---|
| Configuración de BD en HMI | La pantalla permite elegir SQLite, PostgreSQL o MySQL como motor del **historiador central**. | **Eliminar SQLite** de esa selección. El central de producción debe ser PostgreSQL o MySQL. |
| Uso de SQLite local | No existe en el producto. | **Nuevo:** `./db/catalog.db` como espejo de catálogo (tags, alarmas, users, roles, OPC, machines, …). No configurable por el operador; se crea automáticamente. |
| Separación con SAF | SAF usa SQLite para el journal de históricos (`./db/saf/<node_id>/journal.db`). | El catálogo local es **otro archivo**. Ambos coexisten sin interferencia. |
| Sincronización | No existe. | Sync bidireccional entre el espejo local y el central (PostgreSQL/MySQL). En modo degradado el edge opera con el espejo. |

---

## Índice

| § | Sección |
|---|---|
| — | [Aclaración crítica: SQLite en la HMI](#aclaracion-sqlite) |
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

Dotar a PyAutomationIO de un **catálogo local espejo en SQLite** en cada edge, con sincronización bidireccional asíncrona hacia la base de datos central (PostgreSQL/MySQL), de modo que el nodo pueda **arrancar, adquirir, alarmar y autenticar** sin depender del historiador/catálogo remoto.

**Dentro de alcance**

1. Abstracción `ICatalogProvider` (local SQLite / remoto PostgreSQL o MySQL).
2. Worker de replicación bidireccional con resolución de conflictos.
3. Hidratación de CVT, alarmas, OPC, máquinas y usuarios desde el espejo local.
4. Autenticación con fallback local en modo degradado.
5. Métricas, alarmas `ALM.CATALOG.*` y banner HMI.
6. Eliminación de SQLite como opción en la HMI de configuración del historiador central (solo PostgreSQL/MySQL).
7. Replicación de **todas** las tablas de catálogo (no series temporales) con integridad referencial y orden de sincronización.
8. Consistencia multi-edge: el central coordina; los edges no se replican entre sí; la política de conflictos deja al central como fuente de verdad final.

**Fuera de alcance:** rediseño del SAF de históricos; certificación SIL formal; dump completo periódico del catálogo (solo diferencial); replicación directa entre edges (todo pasa por el central).

---

## 2. Principios

<a id="principios"></a>

| Principio | Aplicación |
|---|---|
| **Autonomía del edge** | Arranque, adquisición, alarmas y login sin PostgreSQL/MySQL; el espejo local es fuente de verdad en aislamiento |
| **Sincronización asíncrona** | Replicación en hilo OS dedicado; no interfiere con el hot path (1 Hz – 100 Hz) |
| **Consistencia eventual** | En partición ambos lados pueden divergir; al reconectar, timestamps + prioridad de nodo → estado coherente + auditoría de conflictos |
| **Seguridad por diseño** | Hashes bcrypt/argon2 en local y central; login valida contra el espejo si el central no está |
| **Fallback transparente** | `ICatalogProvider` abstrae el origen; el resto del sistema no distingue SQLite vs remoto (SRP + DIP) |
| **S / O / L / I / D** | Un adaptador por fuente; worker y resolver extensibles; interfaz acotada al catálogo |
| **Integridad referencial** | El orden de sincronización respeta dependencias (padres antes que hijos) |
| **Multi-edge consistente** | El central es árbitro único; los edges sincronizan solo con él. Si dos edges modifican la misma entidad offline, gana el timestamp más reciente y se propaga a todos en el siguiente pull |

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
│  │    └── RemoteCatalogProvider (PostgreSQL / MySQL)                   │   │
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
│  │  SQLite local (catálogo espejo)  →  ./db/catalog.db                 │   │
│  │  [Todas las tablas de catálogo] + catalog_versions                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Replicación (TCP/IP)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL / MySQL Central (Historiador + Catálogo Maestro)                │
│  [Todas las tablas de catálogo] + catalog_versions                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2. Componentes

| Componente | Responsabilidad | SOLID |
|---|---|---|
| `ICatalogProvider` | CRUD unificado sobre catálogo (todas las tablas) | D, I |
| `LocalCatalogProvider` | SQLite local (`./db/catalog.db`) | L, S |
| `RemoteCatalogProvider` | PostgreSQL/MySQL existente envuelto en la interfaz | L, S |
| `CatalogReplicatorWorker` | Sync bidireccional, conflictos y versionado | S, O |
| `CatalogVersionManager` | Timestamps de modificación (`catalog_version` por fila) | S |
| `ConflictResolver` | Política timestamp + prioridad de nodo | S, O |
| `DegradedModeCoordinator` | Banner degradado + fallback de autenticación | S, D |

### 3.3. Separación con SAF

| Almacén | Ruta | Rol |
|---|---|---|
| SAF (históricos) | `./db/saf/<node_id>/journal.db` | Durabilidad de series temporales, eventos, alarmas |
| Catálogo local | `./db/catalog.db` | Espejo de configuración |

Ambos archivos son independientes y coexisten sin interferencia.

---

## 4. Modelo de datos

<a id="modelo"></a>

### 4.1. Tablas de catálogo (replicadas en el espejo local)

Lista exhaustiva según el esquema actual de PyAutomation (excluye series temporales gestionadas por SAF). El espejo local mantiene estructura y datos con sync bidireccional.

| Tabla | Descripción | Dependencias (padre) |
|---|---|---|
| `users` | Usuarios del sistema | `roles` |
| `roles` | Roles de seguridad | — |
| `manufacturer` | Fabricantes / Sitios | — |
| `segment` | Segmentos / Áreas | `manufacturer` |
| `variables` | Variables de proceso (catálogo) | — |
| `units` | Unidades de medida | `variables` |
| `datatypes` | Tipos de datos (bool, int, float, …) | — |
| `tags` | Tags de proceso | `datatypes`, `units`, `segment` |
| `opcua` | Clientes OPC UA | `segment`, `tags` (opcional) |
| `accesstype` | Tipos de acceso OPC UA | — |
| `opcuaserver` | Servidor OPC UA embebido | `segment` |
| `nodes` | Nodos edge registrados | `segment` |
| `machines` | Máquinas de estado | `segment` |
| `tagsmachines` | Asociación tags ↔ máquinas | `tags`, `machines` |
| `linearreferencinggeospatial` | Georreferenciación lineal | `segment` |
| `hmisessions` | Sesiones HMI (conteo global) | `users`, `nodes` |
| `alarmtypes` | Tipos de alarmas | — |
| `alarmstates` | Estados de alarmas (ISA-18.2) | — |
| `alarms` | Definición de alarmas | `tags`, `alarmtypes`, `alarmstates` |

Si en el futuro se añaden tablas de catálogo (no series temporales), deben incluirse automáticamente en la replicación (extensible por configuración).

### 4.2. Tabla de versionado (`catalog_versions`)

Se crea en el espejo local y en el remoto:

```sql
CREATE TABLE catalog_versions (
    table_name VARCHAR(64) NOT NULL,
    row_id INTEGER NOT NULL,          -- PK de la fila (nombre si es textual)
    version BIGINT NOT NULL,          -- timestamp UNIX (ms) de última modificación
    node_id VARCHAR(64),              -- quién hizo el cambio (edge o central)
    conflict_resolved BOOLEAN DEFAULT false,
    PRIMARY KEY (table_name, row_id)
);
```

Cada fila modificada en cualquier tabla de catálogo debe tener entrada en `catalog_versions` con la última `version` y el `node_id` autor.

### 4.3. Orden de sincronización (integridad referencial)

El `CatalogReplicatorWorker` sincroniza padres antes que hijos (push y pull):

1. `datatypes`, `alarmtypes`, `alarmstates`, `roles`, `manufacturer`, `variables`, `accesstype`
2. `units`, `segment`
3. `users`, `tags`, `opcua`, `opcuaserver`, `nodes`, `machines`, `linearreferencinggeospatial`
4. `alarms`, `tagsmachines`, `hmisessions`

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
| **Push** (local → remoto) | Por cada tabla en orden de dependencias: filas con `node_id == edge_id` más recientes o ausentes en remoto; marcar `conflict_resolved` |
| **Pull** (remoto → local) | Por cada tabla en orden de dependencias: filas remotas con `version > local_version` no originadas por el mismo edge |
| **Conflictos** | Gana timestamp más reciente; empate → gana remoto; Event con detalle (tabla, `row_id`, versiones) |
| **Auditoría** | Event resumen por ciclo (p. ej. «5 pushed, 12 pulled, 1 conflict») |

### 5.3. Consistencia multi-edge

En una arquitectura con N edges, el servidor central es el único punto de coordinación. Cada edge sincroniza **solo** con el central, nunca con otros edges.

| Escenario | Comportamiento |
|---|---|
| Edge A y B modifican la misma entidad offline | Ambos registran `node_id` + timestamp. Al reconectar, el central aplica timestamp más reciente; el perdedor queda como conflicto resuelto en Events; ambos edges reciben la versión ganadora en el pull |
| A offline, B online | B escribe en el central. Al reconectar A, push + resolución por timestamp; A recibe la versión del central en el pull |
| Central recibe A y B en distinto orden | El orden de llegada no importa: manda el timestamp |
| Conflictos no auto-resueltos (raros) | Events + `ALM.CATALOG.Conflict`; resolución manual vía admin o BD central |

**Principio clave:** el central nunca descarta un cambio entrante sin evaluar; aplica la política de timestamp y registra el resultado. Los edges **aceptan** la versión del central en el pull aunque sobrescriba su versión local (deliberado para consistencia global).

### 5.4. Modificaciones offline

| Caso | Comportamiento |
|---|---|
| Crear/editar tag o alarma | Persistir en SQLite con `node_id = edge_id`, `version = now_ms()`; push al reconectar |
| Cambio de contraseña / usuarios | Hash local; réplica al remoto; conflicto por nombre → política de timestamp |
| Crear/editar máquinas, OPC, etc. | Misma mecánica; el orden de dependencias se respeta en el push |

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
| Índices | En SQLite local: índices en `catalog_versions` y en columnas `version` de cada tabla |

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
| `CATALOG_TABLES_COUNT` | Número de tablas replicadas (siempre ≥ 17) |

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
| CA-CATALOG-01 | El edge arranca y opera sin PostgreSQL/MySQL (catálogo local) |
| CA-CATALOG-02 | Cambios en modo degradado (tag, alarma, password, máquina, OPC, …) se replican al reconectar |
| CA-CATALOG-03 | Cambios en el central mientras el edge estaba offline llegan al edge al reconectar |
| CA-CATALOG-04 | Conflictos se resuelven por timestamp más reciente y se registran en Events |
| CA-CATALOG-05 | Banner de modo degradado en HMI cuando la fuente activa es local |
| CA-CATALOG-06 | Autenticación local funciona en modo degradado |
| CA-CATALOG-07 | Sync no degrada p95 de `set_value` (soak 24 h con sync activa) |
| CA-CATALOG-08 | SQLite local ≤ 500 MB con catálogo típico |
| CA-CATALOG-09 | Rollback a remoto-only posible sin pérdida de datos |
| CA-CATALOG-10 | Alarmas y eventos ante fallos de sincronización |
| CA-CATALOG-11 | SQLite eliminado de la HMI de configuración del historiador; solo PostgreSQL/MySQL |
| CA-CATALOG-12 | Todas las tablas de §4.1 se replican; se respeta el orden de dependencias |
| CA-CATALOG-13 | Integridad referencial intacta en local y remoto tras la sync |
| CA-CATALOG-14 | Multi-edge: dos edges modifican offline la misma entidad; el central resuelve por timestamp y ambos convergen |

Tests previstos: unitarios (conflictos, versionado, orden FK), integración push/pull multi-edge, soak 24 h, revisión HMI (banner + eliminación de SQLite en config).

---

## 10. Plan de implementación

<a id="plan"></a>

| Fase | Entregable | Prioridad | Estimación | Estado |
|---|---|---|---|---|
| 1 | Modelo `catalog_versions` + migración SQL (ambos lados) | P0 | 1 d | Pendiente |
| 2 | `ICatalogProvider` + adaptadores local/remoto (todas las tablas) | P0 | 2 d | Pendiente |
| 3 | `CatalogReplicatorWorker` (push/pull, conflictos, orden de dependencias) | P0 | 2.5 d | Pendiente |
| 4 | Arranque / hidratación local + modo degradado | P0 | 1 d | Pendiente |
| 5 | Autenticación local (login con fallback) | P1 | 0.5 d | Pendiente |
| 6 | HMI: banner, métricas, alarmas | P1 | 1 d | Pendiente |
| 7 | Eliminar SQLite de la HMI de configuración | P0 | 0.5 d | Pendiente |
| 8 | Tests unitarios e integración (incluye multi-edge) | P0 | 2.5 d | Pendiente |
| 9 | Soak 24 h planta (CA-CATALOG-01…14) | P0 validación | 1 d | Pendiente |
| 10 | Documentación y runbook | P2 | 0.5 d | Pendiente |

---

## 11. Veredicto objetivo

<a id="veredicto"></a>

| Dimensión | Hoy | Meta post-impl |
|---|---|---|
| Autonomía del edge (catálogo / login sin remoto) | Dependiente del remoto para catálogo completo | **A** |
| Disponibilidad adquisición + SAF | **A−** (ya robusta) | Mantener (sync fuera del hot path) |
| Consistencia catálogo multi-nodo | Unidireccional / central | Consistencia eventual + auditoría + orden de dependencias |
| Operabilidad HMI en partición | Banner BD historiador (spec 09/10) | Banner + fuente `local` + métricas `CATALOG_*` |
| Claridad de configuración | SQLite aparece como opción de historiador central | **Eliminado**; solo PostgreSQL/MySQL |
| Cobertura de catálogo | Solo algunas tablas conceptualizadas | Todas las tablas de catálogo con orden FK |
| Multi-edge consistente | No implementado | **A** — el central es árbitro; los edges convergen |

**Conclusión:** el edge queda como nodo autónomo con réplica completa de catálogo de grado industrial, hot path intacto y sync como proceso de fondo con trazabilidad ISA-18.2. La cobertura de todas las tablas, la eliminación de SQLite de la HMI de configuración y la política multi-edge aseguran robustez y consistencia en despliegues con N edges.
