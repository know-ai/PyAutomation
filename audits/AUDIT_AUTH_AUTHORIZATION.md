# AUDIT_AUTH_AUTHORIZATION — Autenticación y autorización

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Login, sesión, token, roles, ACL REST/HMI, guards HMI, Swagger, roles dinámicos |
| **Fecha** | 2026-09-03 · **reimpl. ACL 2026-09-03** · **bus invalidación ACL 2026-09-03** · **roles dinámicos + docs 2026-09-03** |
| **Evidencia** | Código del árbol + `automation/tests/test_authz.py` + `test_authz_invalidate.py` + `test_authz_app_hooks.py` + `test_docs_auth.py` |
| **Complementa** | [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md), [AUDIT_CATALOG_SQLITE_LOCAL.md](./AUDIT_CATALOG_SQLITE_LOCAL.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) |
| **Veredicto autenticación** | **A−** — TPT con `exp`+rol y principal sintético; database config/connect y `reconnect_db` autenticados; signup público y sesión sin TTL siguen abiertos |
| **Veredicto autorización** | **A−** — ACL persistido fail-closed; panel HMI; semilla por rol built-in; roles dinámicos heredan `guest`; bootstrap con hooks de producto; Swagger con sesión aparte. Socket.IO aún no filtra por vista |
| **Clasificación** | Auditoría de seguridad de aplicación · planificación y seguimiento post-implementación |

---

## Índice

1. [Respuesta directa](#1-respuesta-directa)
2. [Autenticación](#2-autenticación)
3. [Autorización (ACL implementado)](#3-autorización-acl-implementado)
4. [Inventario REST](#4-inventario-rest)
5. [Inventario HMI](#5-inventario-hmi)
6. [Hallazgos](#6-hallazgos)
7. [Modelo objetivo y matriz semilla](#7-modelo-objetivo-y-matriz-semilla)
8. [Estrategia por fases](#8-estrategia-por-fases)
9. [Criterios de aceptación](#9-criterios-de-aceptación)
10. [Fuera de alcance](#10-fuera-de-alcance)
11. [Caché ACL, Redis y multi-edge](#11-caché-acl-redis-y-multi-edge)

---

## 1. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Hay login de verdad? | **Sí.** Usuario + contraseña (hash Werkzeug), token de sesión opaco, cabecera `X-API-KEY` o `Authorization: Token …` |
| ¿La autenticación sirve para planta? | **Aceptable.** Una sesión por usuario, restore offline, Socket.IO fail-closed, usuario `system` acotado en HTTP |
| ¿Hay autorización de verdad? | **Sí.** Tabla `authz_grants`, motor fail-closed, middleware REST (`before_request`), HMI vía `GET /api/authz/me` |
| ¿Se puede dar a un operador solo Tags y no Máquinas? | **Sí**, en **Administración de accesos** (rol o usuario), sin tocar código |
| ¿Se puede excepcionar a un usuario concreto? | **Sí.** Override por usuario: deny usuario > allow usuario > deny rol > allow rol > deny |
| ¿Un rol nuevo (p. ej. `plant_engineer`) sirve de algo? | **Sí.** Al crearlo hereda la línea base **`guest`** (menor privilegio entre roles built-in); luego se edita en el panel ACL |
| ¿GET y PUT se distinguen? | **Sí.** GET/HEAD → acción `view`; POST/PUT/PATCH/DELETE → acción `use` |
| ¿Hay UI para definir accesos? | **Sí.** `hmi/src/pages/AccessControl.tsx`: pestañas **Vistas HMI** y **Endpoints REST**, selector Rol/Usuario, Permitir/Denegar |
| ¿Vistas HMI y REST están acoplados? | **No.** Son recursos independientes en el catálogo. Ocultar una vista no bloquea automáticamente sus endpoints REST (y viceversa) |

**Lo que sigue abierto:** signup público (AUTH-M1), sesión sin TTL (AUTH-M3), Socket.IO sin filtro por vista (AUTHZ-M2). Ver §6.

### Estado de remediaciones

| ID | Estado | Notas |
|---|---|---|
| AUTH-H1 | **Cerrado** | TPT exige `exp`+`role`; principal sintético; secreto único `AUTOMATION_APP_SECRET_KEY` |
| AUTH-H2 | **Cerrado** | `GET /api/database/config` y `POST /api/database/connect` con token + ACL |
| AUTH-M1 | Abierto | Signup público (default `guest`) |
| AUTH-M2 | **Cerrado** | Emisión/verificación TPT unificada en `AUTOMATION_APP_SECRET_KEY` |
| AUTH-M3 | Abierto | Sesión opaca sin TTL propio |
| AUTH-L1 | **Cerrado** | `POST /api/system/reconnect_db` autenticado |
| AUTHZ-C1 | **Cerrado** | Grants persistidos; panel ACL; rol dinámico con baseline `guest` |
| AUTHZ-C2 | **Cerrado** | Middleware: GET=`view`, mutación=`use`; fail-closed |
| AUTHZ-H1 | **Cerrado** | Override por usuario |
| AUTHZ-H2 | **Cerrado** | Sidebar/rutas leen `/api/authz/me` |
| AUTHZ-H3 | Mitigado | `level` protege escalada en user mgmt; ACL es autoridad REST |
| AUTHZ-M1 | **Cerrado** | `auth_roles` delega al motor ACL |
| AUTHZ-M2 | Abierto | Socket.IO no filtra por vista |
| AUTHZ-M3 | **Cerrado** | Bus híbrido Redis + `pg_notify`; heartbeat 300 s |
| AUTHZ-L1 | **Cerrado** | Swagger protegido por sesión Flask-Login (`docs_auth.py`), no allowlist JWT |
| AUTHZ-L2 | Aceptado (diseño) | Caché ACL = RAM; Redis = bus de invalidación |
| AUTHZ-L3 | **Cerrado** | Rol creado en HMI → `seed_grants_for_new_role()` clona `guest` + gap-fill matriz |

Roles built-in: `integrator` (level 0, all-allow seed), `sudo` (solo `system`), `admin`, `supervisor`, `operator`, `auditor`, `guest` (level 256, baseline para roles custom). `integrator` en `CONTROL_ROLES` / `DESTRUCTIVE_ROLES` (`ops_controls.py`).

---

## 2. Autenticación

### 2.1 Identidad y credenciales

| Pieza | Dónde | Comportamiento |
|---|---|---|
| Usuario | `dbmodels/users.py` + CVT `modules/users/users.py` | `username` único, `email` opcional, password hasheado, FK a rol |
| Contraseña | Werkzeug `generate_password_hash` / `check_password_hash` | Hash en disco y en memoria |
| Roles semilla | `Roles.__defaults__` | `integrator` 0, `sudo` 0, `admin` 1, `supervisor` 2, `operator` 10, `auditor` 100, `guest` 256. Nivel **más bajo = más privilegio** |
| Signup | `POST /api/users/signup` **público** | Rol por defecto `guest`. La HMI tiene `/signup` |
| Login | `POST /api/users/login` **público** | Devuelve `apiKey`, `username`, `role`, `role_level` |
| Logout | `POST /api/users/logout` | Invalida token (memoria + store + revoked set) |

### 2.2 Sesión

Token opaco (no JWT). Resolución (`Api._resolve_session_user`):

1. Memoria (`active_users`).
2. Revocado → `401 SESSION_SUPERSEDED`.
3. Historiador: `user_api_sessions` o `Users.token`.
4. Historiador caído: restore offline; si no hay sesión → `503 AUTH_BACKEND_UNAVAILABLE`.
5. JWT TPT válido (`decode_tpt` con `exp`+`role`) → principal sintético `tpt:<rol>`.

Política: un login nuevo revoca sesiones previas del mismo usuario. HMI persiste `{ token, user }` en `localStorage`.

### 2.3 Canal Socket.IO

`hmi_socket_audit.resolve_connect_user`: mismo token, fail-closed. **No aplica ACL por vista:** token válido → snapshot completo. Ver [AUDIT_HMI_SOCKET_TRACEABILITY.md](./AUDIT_HMI_SOCKET_TRACEABILITY.md).

### 2.4 Usuario `system`

Bootstrap interno (`sudo`). HTTP acotado a `/api/users/*`, `/api/health/*`, `/api/system/*`, `/api/authz/*`. Bloqueado `POST /api/users/create_tpt`. HMI: User Management + ACL.

### 2.5 Third Party Token (TPT)

`POST /api/users/create_tpt` (system o integrator). JWT HS256 con `exp` (8 h por defecto), `role`, `created_on`. `Api.decode_tpt` exige `exp` y `role`. El middleware ACL evalúa al principal sintético con la matriz del rol embebido.

### 2.6 Swagger (`/api/docs`)

Canal **separado** del JWT de API:

- Rutas: `/api/docs`, `/api/swagger`, `/api/swagger.json`, `/api/swaggerui`.
- Excluidas del middleware ACL JWT (`authz/middleware.py` + `docs_auth.is_docs_path`).
- Protegidas por **Flask-Login** (`extensions/docs_auth.py`): login `GET/POST /login-docs`, logout `/logout-docs`.
- Acceso: usuario `system` (password `DOCS_SYSTEM_PASSWORD` o `AUTOMATION_SUPERUSER_PASSWORD`) o usuario BD con rol **integrator**.
- Rate limit en POST login (`DOCS_RATE_LIMIT`, default `5 per minute`). Tests: `test_docs_auth.py`.

### 2.7 Pendientes de autenticación

| ID | Tema |
|---|---|
| AUTH-M1 | Signup público; posible elusión de `guest` si se llama `app.signup` con `role_name` |
| AUTH-M3 | Token de sesión sin expiración (solo revocación por logout / login nuevo) |

---

## 3. Autorización (ACL implementado)

### 3.1 Persistencia y motor

| Pieza | Ubicación | Comportamiento |
|---|---|---|
| Tabla | `authz_grants` (PG + espejo `catalog.db`) | `subject_type` (`role`\|`user`), `subject_id`, `resource_key`, `action`, `effect` (`allow`\|`deny`) |
| Caché hot path | `authz/store.py` | Dict RAM O(1); **sin SELECT por request** |
| Evaluación | `authz/engine.py` `evaluate()` | deny usuario > allow usuario > deny rol > allow rol > **deny** (fail-closed) |
| API admin | `modules/authz/resources/authz.py` | `GET /api/authz/me`, `catalog`, `preview`, `PUT /api/authz/grants` |
| Invalidación | `authz/invalidate.py` + `UserInvalidateWorker` | `pg_notify` cross-edge + Redis `pya:authz:invalidate` intra-edge |

### 3.2 Catálogo de recursos y bundles vista→REST

- **HMI:** claves `hmi:view.<view_id>`. Acciones: `view`, `use`.
- **REST:** claves `rest:<METHOD> <path_template>`.
- **Bundles** (`authz/view_bundles.py`): conceder **`view`** en una pantalla HMI implica automáticamente los endpoints de **lectura** que la pantalla usa (GET/HEAD y POST de filtrado/consulta como `filter_by`, `query_trends`, `get_tabular_data`, listados auxiliares de usuarios/áreas). Conceder **`use`** en la vista implica los endpoints de **escritura** del bundle.
- Los grants REST explícitos en el panel siguen valiendo; un **deny** REST gana sobre la implicación de la vista.
- Extensiones de producto: hooks `authz/app_hooks.py`.

### 3.3 Middleware REST

`authz/middleware.py` `enforce_api_authz()` registrado en blueprint `/api`:

1. OPTIONS → pasa.
2. Rutas Swagger → pasa (protegidas por `docs_auth`).
3. Allowlist pública exacta (login, signup, health probes, timezone).
4. Token + resolución de usuario (o TPT).
5. Usuario `system` → allowlist de paths.
6. Rutas siempre autenticadas sin ACL extra: logout, change_password, `authz/me`, credentials_are_valid.
7. Resto: `rest_key_from_request` + `default_action(method)` → `evaluate(user, key, action)`; sin grant → **403**.

Los decoradores `@Api.auth_roles` y `@Api.authorize` delegan al mismo motor; el enforcement uniforme es el `before_request`.

### 3.4 Matriz semilla (`authz/seed.py`)

`default_allows(role, resource_key, action)` — jerarquía por herencia:

| Rol | HMI (`view` only) | REST (resumen) |
|---|---|---|
| `guest` | real-time-trends, machines/summary, machines/detailed | GET machines, tags, history, hmi |
| `auditor` | + alarms/summary, events, operational-logs | + GET alarms, events, logs |
| `operator` | + alarms/definitions, tags/* | + ACK/shelve alarmas |
| `supervisor` | + communications/*, performance | + OPC UA, lectura performance/admin |
| `admin` | + settings | + settings (sin users/authz/database) |
| `integrator` | all-allow | all-allow |
| `sudo` | all-deny en semilla | all-deny |

`seed_default_grants()` inserta filas `allow` faltantes de forma **idempotente** (no sobrescribe grants existentes).

### 3.5 Roles dinámicos (baseline `guest`)

Al crear un rol con `POST /api/users/roles/add` → `PyAutomation.set_role()`:

1. Persiste rol en CVT + historiador.
2. Llama `seed_grants_for_new_role(name, identifier, flask_app)`:
   - **Clona** grants ACL actuales del rol `guest` (si fueron personalizados en el panel).
   - **Rellena huecos** con la matriz usando plantilla `guest` (`template_role=BASELINE_ROLE`).
   - Recarga caché si `persist=True`.

Roles cuyo nombre **no** está en `BUILTIN_SEED_ROLES` delegan en `default_allows("guest", …)` para gap-fill futuro.

Constantes: `BASELINE_ROLE = "guest"`, `BUILTIN_SEED_ROLES` en `authz/seed.py`. Tests: `TestAuthzNewRoleSeed`, `test_custom_role_inherits_guest_matrix` en `test_authz.py`.

### 3.6 HMI

| Pieza | Comportamiento |
|---|---|
| `authzSlice` + `useAuthz()` | Hidrata `/api/authz/me` tras login |
| `VIEW_IDS` (`utils/access.ts`) | Identificadores estables alineados con `hmi:view.*` |
| `Sidebar.tsx` | Ítems visibles solo si `canView(view_id)` |
| `AccessControl.tsx` | Edición de grants por rol/usuario; preview vía `previewAuthz`; tabs HMI y REST |
| Menú Administración | Grupo colapsable: Gestión de usuarios + Administración de accesos |

`access.ts` ya **no** es autoridad de permisos; solo constantes y helpers sobre datos de `/authz/me`.

### 3.7 Jerarquía `level` (user management)

`change_password`, `reset_password`, `update_role`: no se puede tocar a alguien con `level` menor (más privilegiado). **No sustituye al ACL** en endpoints de proceso.

---

## 4. Inventario REST

Prefijo `/api`. Clasificación por **middleware + ACL** actual.

### 4.1 Público (sin token)

| Método | Ruta | Nota |
|---|---|---|
| POST | `/users/login`, `/users/signup` | Auth |
| GET | `/health/ping`, `/liveness`, `/readiness`, `/db`, `/saf`, `/system` | Probes |
| GET | `/system/timezone` | Presentación |

### 4.2 Autenticado, sin evaluación ACL adicional

| Método | Ruta |
|---|---|
| POST | `/users/logout`, `/users/change_password` |
| GET | `/authz/me`, `/users/credentials_are_valid` |

### 4.3 Protegido por token + ACL

Todo el resto de `/api/*` no listado arriba, incluyendo tags, machines, alarms, OPC, database config/connect, settings, users admin, authz catalog/grants/preview, system/reconnect_db, extensiones de producto.

Acción derivada del verbo HTTP: GET/HEAD → `view`; mutadores → `use`.

### 4.4 Swagger (sesión aparte)

| Ruta | Guardia |
|---|---|
| `/api/docs`, `/api/swagger*`, `/api/swagger.json` | Flask-Login (`docs_auth`); integrator o `system` |
| `/login-docs`, `/logout-docs` | Formulario de acceso a documentación |

### 4.5 Usuario `system`

Solo paths permitidos por `system_user_path_allowed()`; incluye administración de usuarios y ACL, no operación de tags/máquinas.

---

## 5. Inventario HMI

Rutas bajo `ProtectedLayout`. Visibilidad de menú y navegación según `canView(VIEW_IDS.*)` → `/api/authz/me`.

| Vista (ruta) | `view_id` (prefijo `hmi:view.`) | Backend típico |
|---|---|---|
| Communications / clients | `communications.clients` | `/api/opcua/clients/*` |
| Communications / server | `communications.server` | `/api/opcua/server/*` |
| Database | `database` | `/api/database/*` |
| Tags definitions / datalogger / trends | `tags.*` | `/api/tags/*`, history |
| Real-time trends | `real-time-trends` | socket + workspace |
| Alarms definitions / summary | `alarms.*` | `/api/alarms/*` |
| Machines summary / detailed | `machines.*` | `/api/machines/*`, domain-config |
| Events / operational logs | `events`, `operational-logs` | `/api/events/*`, `/api/logs/*` |
| Performance | `performance` | `/api/settings/performance`, `/api/admin/*` |
| User management | `user-management` | `/api/users/*`, roles |
| **Administración de accesos** | `authz` | `/api/authz/*` |
| Settings | `settings` | `/api/settings/*` |
| Extensiones producto (p. ej. LDS) | registradas por la app | APIs de producto |

**Importante:** ocultar una fila en la pestaña HMI del panel ACL no revoca automáticamente los endpoints REST del mismo dominio; hay que configurar ambas pestañas si se quiere coherencia total.

---

## 6. Hallazgos

### 6.1 Autenticación

| ID | Sev | Estado | Hallazgo | Evidencia |
|---|---|---|---|---|
| **AUTH-H1** | Alto | **Cerrado** | TPT sin `exp`/rol ignorado | `api.py` `decode_tpt`, `create_tpt` con `exp` |
| **AUTH-H2** | Alto | **Cerrado** | Database config/connect anónimos | `middleware.py`; tests `test_authz.py` |
| **AUTH-M1** | Medio | Abierto | Signup público | `SignUpResource`, `PyAutomation.signup` |
| **AUTH-M2** | Medio | **Cerrado** | Dos secretos TPT | `AUTOMATION_APP_SECRET_KEY` unificado |
| **AUTH-M3** | Medio | Abierto | Sesión sin TTL | `Users.login`, store |
| **AUTH-L1** | Bajo | **Cerrado** | `reconnect_db` público | `system.py` `@Api.token_required` |

### 6.2 Autorización

| ID | Sev | Estado | Hallazgo | Evidencia |
|---|---|---|---|---|
| **AUTHZ-C1** | Crítico | **Cerrado** | Rol UI sin efecto en ACL | `authz_grants`, `AccessControl.tsx`, `seed_grants_for_new_role` |
| **AUTHZ-C2** | Crítico | **Cerrado** | “Cualquier autenticado” en proceso | `middleware.py` fail-closed |
| **AUTHZ-H1** | Alto | **Cerrado** | Sin override por usuario | `engine.py` precedencia |
| **AUTHZ-H2** | Alto | **Cerrado** | HMI y API divergentes | `authz/me`, Sidebar |
| **AUTHZ-H3** | Alto | Mitigado | `level` vs ACL | user handlers + ACL |
| **AUTHZ-M1** | Medio | **Cerrado** | Allowlists inconsistentes | delegación a motor |
| **AUTHZ-M2** | Medio | Abierto | Socket sin filtro por vista | `hmi_socket_audit` |
| **AUTHZ-M3** | Medio | **Cerrado** | Multi-worker / multi-edge ACL | `invalidate.py`, `user_invalidate.py` |
| **AUTHZ-L1** | Bajo | **Cerrado** | Swagger público | `docs_auth.py`, `test_docs_auth.py` |
| **AUTHZ-L2** | Info | Aceptado | ACL solo en RAM | `store.py` |
| **AUTHZ-L3** | Bajo | **Cerrado** | Rol nuevo sin grants iniciales | `seed_grants_for_new_role`, baseline `guest` |

---

## 7. Modelo objetivo y matriz semilla

### 7.1 Principios (implementados)

1. **Una fuente de verdad en backend.** HMI consume `/authz/me` y catálogo.
2. **Fail-closed.** Recurso sin grant → denegado (salvo allowlist pública explícita).
3. **Sujeto = rol ∪ override usuario.** Precedencia documentada en §3.1.
4. **Recursos direccionables:** REST `rest:METHOD path`, HMI `hmi:view.<id>`.
5. **Verbos:** `view` (GET/HEAD, ver menú) y `use` (mutación).
6. **Catálogo auto-descubierto** al bootstrap (+ hooks de producto).
7. **Semilla idempotente** para roles built-in; roles custom heredan `guest`.

### 7.2 Persistencia (implementada)

Ver §3.1. Espejo `catalog.db` vía replicator; LOOKUP sin partición de área.

### 7.3 Matriz semilla de referencia

Implementada en `default_allows()` (`authz/seed.py`). Jerarquía por herencia.

**Vistas HMI** (semilla solo con acción `view`; acciones de botones → REST):

| Rol | Vistas |
|---|---|
| **guest** | real-time-trends, machines/summary, machines/detailed |
| **auditor** | guest + alarms/summary, events, operational-logs |
| **operator** | auditor + alarms/definitions, tags/* |
| **supervisor** | operator + communications/*, performance |
| **admin** | supervisor + settings |
| **integrator** | todas |

**REST** (resumen; refinable en panel):

| Rol | Alcance |
|---|---|
| **guest** | GET machines, tags, history, hmi |
| **auditor** | guest + GET alarms, events, logs |
| **operator** | auditor + ACK/shelve alarmas |
| **supervisor** | operator + OPC UA + lectura performance/admin |
| **admin** | supervisor + settings (sin users/authz/database) |
| **integrator** | all-allow |

Rol **custom** al crear: hereda **guest** (vistas + REST). Sin vista → no menú. Sin REST → 403 en API aunque la vista sea visible.

### 7.4 Panel de administración (implementado)

`AccessControl.tsx`:

1. Selector **Rol** o **Usuario** + sujeto.
2. Pestañas **Vistas HMI** y **Endpoints REST** (con buscador en REST).
3. Por fila: Permitir / Denegar (`view` y `use` donde aplica).
4. Preview implícito al cargar sujeto (`previewAuthz` → borrador de efectivos).
5. Guardar → `PUT /api/authz/grants` + invalidación de caché.

---

## 8. Estrategia por fases

| Fase | Objetivo | Estado |
|---|---|---|
| **0** | Cerrar huecos auth (DB, TPT, reconnect) | **Hecho** (signup abierto) |
| **1** | Catálogo + motor + middleware | **Hecho** |
| **2** | Semilla + UI ACL + HMI `/authz/me` | **Hecho** |
| **3** | REST uniforme + distinguir view/use | **Hecho** (Socket pendiente) |
| **4** | Productos (iDetectFugas hooks) | **Hecho** (`app_hooks.py`) |
| **5** | Roles dinámicos baseline `guest` | **Hecho** (2026-09-03) |
| **6** | Protección Swagger | **Hecho** (`docs_auth.py`) |

**Pendiente explícito:** filtro Socket.IO por vista (AUTHZ-M2); cierre signup (AUTH-M1); TTL sesión (AUTH-M3).

---

## 9. Criterios de aceptación

| ID | Criterio | Estado |
|---|---|---|
| **CA-AUTHZ-01** | Rol `plant_engineer` con solo tags vía UI, sin redeploy | PASS |
| **CA-AUTHZ-02** | Override usuario deny máquinas | PASS |
| **CA-AUTHZ-03** | Guest no escribe; auditor view-only | PASS |
| **CA-AUTHZ-04** | Menú ⊆ `/authz/me` | PASS |
| **CA-AUTHZ-05** | Recurso sin grant → 403 | PASS |
| **CA-AUTHZ-06** | TPT con rol y matriz ACL | PASS |
| **CA-AUTHZ-07** | Database config/connect autenticados + grant | PASS |
| **CA-AUTHZ-08** | Tests `test_authz.py` | PASS |
| **CA-AUTHZ-09** | `system` acotado; integrator administra ACL | PASS |
| **CA-AUTHZ-10** | Rol nuevo hereda permisos de `guest` al crear | PASS (`TestAuthzNewRoleSeed`) |
| **CA-DOCS-01** | `/api/docs` exige sesión integrator/system | PASS (`test_docs_auth.py`) |
| **CA-REDIS-01…06** | Invalidación multi-edge / hot path | PASS (ver §11) |

---

## 10. Fuera de alcance

- SSO / LDAP / OIDC.
- Autorización OPC UA server (usuarios UA ≠ Users HTTP).
- Cifrado en reposo del historiador.
- Certificación ISA-62443 / IEC 62443.
- Grants dentro de Redis como fuente de verdad.
- Redis de planta compartido entre edges (cross-edge = `pg_notify`).

---

## 11. Caché ACL, Redis y multi-edge

Implementado 2026-09-03. Principio: autorización de **planta**; Redis **no** guarda la matriz.

### 11.1 Redis sidecar vs dict RAM (un Edge)

| Pregunta | Respuesta |
|---|---|
| ¿ACL consulta PG en cada request? | **No.** `evaluate()` → `store.lookup` O(1). |
| ¿Redis para autorización? | **Solo bus.** Canal `pya:authz:invalidate`, payload `{version, origin}`. |
| ¿N workers gunicorn? | Cada proceso: dict propio; Pub/Sub local + `reload_cache`. |

### 11.2 Compartición entre edges

| Plano | Dónde | ¿Compartido? |
|---|---|---|
| Persistencia | PG `authz_grants` LOOKUP | **Sí** |
| Espejo offline | `catalog.db` | **Sí**, replicator |
| Enforcement | Dict RAM + versión | **Sí**, segundos vía notify |

Flujo PUT grants: escribe PG → `reload_cache` local → `notify_authz_invalidated` → workers Redis (mismo edge) + `LISTEN` PG (cross-edge) → `reload_cache` si `version` mayor.

Degradación: Redis caído → PG notify; PG caído → Redis intra-edge + heartbeat 300 s; caché vacía → fail-closed.

**Evidencia:** `authz/store.py`, `invalidate.py`, `user_invalidate.py`, `test_authz_invalidate.py`.

---

## Apéndice A — Mapa rápido de archivos

| Archivo | Rol |
|---|---|
| `automation/extensions/api.py` | Token, TPT (`exp`+rol), `@Api.authorize`, resolución sesión |
| `automation/extensions/docs_auth.py` | Sesión Flask-Login para Swagger; rate limit login |
| `automation/authz/middleware.py` | `before_request` ACL REST; exclusión rutas docs |
| `automation/authz/bootstrap.py` | `bootstrap_authz()`, `resolve_flask_app()` |
| `automation/authz/app_hooks.py` | Hooks pre-seed para apps host (iDetectFugas, …) |
| `automation/authz/seed.py` | Matriz `default_allows`, `seed_default_grants`, `seed_grants_for_new_role`, `BASELINE_ROLE` |
| `automation/authz/store.py` | Dict RAM + `reload_cache` |
| `automation/authz/engine.py` | `evaluate()`, precedencia |
| `automation/authz/invalidate.py` | `pg_notify` + Redis publish |
| `automation/workers/user_invalidate.py` | LISTEN + SUB + heartbeat |
| `automation/core.py` | `set_role()` → `seed_grants_for_new_role` |
| `automation/dbmodels/authz.py` | Peewee `AuthzGrant` |
| `automation/modules/authz/resources/authz.py` | `/api/authz/me\|catalog\|grants\|preview` |
| `automation/utils/ops_controls.py` | `integrator` en CONTROL/DESTRUCTIVE roles |
| `automation/utils/system_user.py` | Alcance HTTP de `system` |
| `hmi/src/pages/AccessControl.tsx` | Panel ACL (HMI + REST) |
| `hmi/src/hooks/useAuthz.ts` | Consumo de `/authz/me` |
| `hmi/src/layouts/Sidebar.tsx` | Menú filtrado por `canView` |

---

## Apéndice B — Decisiones de diseño (estado)

| # | Pregunta | Decisión |
|---|---|---|
| 1 | ¿Fail-closed desde semilla? | **Sí**, tras `seed_default_grants` |
| 2 | ¿Grants en PG + espejo? | **Sí**; invalidación híbrida (AUTHZ-M3 cerrado) |
| 3 | ¿TPT? | **Rediseñado:** `exp` + `role` + ACL; no eliminado |
| 4 | ¿Signup? | **Abierto** (AUTH-M1 pendiente) |
| 5 | ¿Socket por vista? | **Pendiente** (AUTHZ-M2) |
| 6 | ¿Baseline rol custom? | **`guest`** — menor privilegio built-in; clon al crear rol |
| 7 | ¿Swagger? | **Sesión aparte** (integrator/system); fuera del JWT API |

---

## Apéndice C — Antes de la reimpl. ACL (histórico)

Entre 2025 y la reimpl. de 2026-09-03, la autorización dependía de:

- `@Api.auth_roles([...])` con nombres de rol hardcoded.
- `hmi/src/utils/access.ts` con listas `OPS_ADMIN_ROLES`.
- Roles creados en UI sin efecto en API.
- `guest` autenticado con acceso de escritura en tags/máquinas/alarmas.

Ese modelo fue sustituido por el descrito en §3. Se conserva este apéndice solo como referencia de auditoría histórica.
