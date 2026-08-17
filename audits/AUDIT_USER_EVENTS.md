# Auditoría de eventos de usuario — tabla `Events`

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/Events.tsx`) |
| **Alcance** | Qué se persiste en la tabla `Events`, qué acciones de operador quedan trazadas (quién / qué / cuándo) y cómo se registran login / logout |
| **Fuera de alcance** | Bitácora operacional (`Logs` / `operational-logs`), histórico de alarmas (`AlarmSummary`), datalogger de tags, logs de aplicación (`pyautomation` logger) |
| **Fecha** | 2026-08-16 (Operación «Trazabilidad Eterna») |
| **Clasificación** | Auditoría de trazabilidad de acciones · confidencialidad interna |
| **Metodología** | Revisión de código de `@set_event`, `persist_system_event`, `audit_metrics`, recursos HTTP y HMI. Tests: `test_user_session_audit`, `test_db_connection_audit`, `test_system_lifecycle_audit`, `test_audit_metrics` |
| **Complementa** | `audits/AUDIT_LOGGING.md`, `audits/AUDIT_OPERATIONAL_LOGS.md`, `audits/STORE_AND_FORWARD.md`, `audits/PERSISTENCE_FLOW.md` |
| **Veredicto** | **A-** respecto a caja negra industrial. Login/logout, forzar tag, CRUD de tags/alarmas, intervalo/on_delay/threshold, transiciones de máquina, arranque/parada limpia, DB en caliente, OPC UA, SAF backpressure y settings quedan en `Events`. Residual: no hay endpoint de borrado de usuario; no hay idle-timeout → `SESSION_INVALID` no ata un usuario; UNACK/RTN siguen en `AlarmSummary` (anti-spam) |

---

## 1. Respuesta directa

**Antes de este cambio no había eventos de login ni de logout.** La tabla `Events` existía y el HMI `/events` las mostraba, pero `POST /api/users/login` y `POST /api/users/logout` no escribían nada.

**Ahora sí.** Identidad usa `classification = "Security"`. Filtrar:

- `User logged in` / `User logged out` / `User login failed`
- `origin=` (IP) y `method=password` en login; `reason=user-initiated` o `reason=session_superseded` en logout

---

## 2. Modelo: qué es un evento

Tabla Peewee `Events` (`automation/dbmodels/events.py`):

| Columna | Tipo | Rol de auditoría |
|---|---|---|
| `timestamp` | UTC | Cuándo |
| `user` | FK → `Users` **obligatoria** | Quién (o `system` si el actor no es un usuario de sesión) |
| `message` | varchar(256) | Qué ocurrió (texto corto, estable) |
| `description` | varchar(256), nullable | Detalle (nombre de tag/alarma, `username=…`, `actor=…`) |
| `classification` | varchar(128) | Familia: `Security`, `Configuration`, `Control`, `System`, `Database`, `OPC UA` |
| `priority` | int | 1–5 según el emisor (valores fijos en código, no ISA-18.2) |
| `criticity` | int | 1–5 según el emisor |

Reglas duras:

- `Events.create` exige un objeto `modules.users.users.User`. Sin usuario no hay fila.
- `message` y `description` se recortan a **256** caracteres en `persist_system_event` y en `@set_event`.
- **Nunca** se persisten contraseñas, tokens ni cuerpos crudos de request.
- Persistencia: journal SAF (`journal_then_remote`) + emit Socket.IO `on.event` para refrescar el HMI.
- Comentarios sobre un evento **no** van a `Events`: van a `Logs` con FK `event` (anotación humana, no acción automática).

---

## 3. Cómo se escribe un evento

Hay **tres** caminos. Solo el 1 y el 2 aplican a acciones de operador.

```
  Acción HTTP (HMI / API)
        │
        ├─► @set_event  ──► EventsLoggerEngine.create
        │     Solo si la función devolvió truthy
        │     Y kwargs contiene user= <User>
        │
        ├─► persist_system_event / record_user_session_event
        │     Fail-safe (nunca levanta al caller)
        │     user= sesión o fallback `system`
        │
        └─► (sin user=)  ──► no hay fila
```

`@set_event` (`automation/utils/decorators.py`): si el método termina bien pero **no** recibe `user=` como `User`, **no se crea evento**. Ese era el hueco de CRUD de tags y transiciones de máquina desde la HMI.

---

## 4. Inventario: qué queda registrado

### 4.1 Identidad y sesión — `classification = "Security"`

Helper: `automation/utils/user_session_audit.py`  
Cableado: `automation/modules/users/resources/users.py` y toma de sesión en `Users._revoke_other_sessions`.

| Acción | `message` | FK `user` | `description` (patrón) | P | C | Disparo |
|---|---|---|---|---|---|---|
| Login OK | `User logged in` | el autenticado | `username=<login> method=password origin=<ip>` | 2 | 2 | `POST /users/login` 200 |
| Login fallido | `User login failed` | **`system`** | `username=<reclamado> reason=invalid_credentials origin=<ip>` | 3 | 4 | `POST /users/login` 403 de credenciales |
| Logout explícito | `User logged out` | el de la sesión | `username=<login> reason=user-initiated origin=<ip>` | 2 | 2 | `POST /users/logout` (sidebar HMI) |
| Toma de sesión | `User logged out` | el mismo usuario | `username=<login> reason=session_superseded` | 2 | 2 | segundo login (una sesión activa) |
| Alta de cuenta | `User account created` | el nuevo usuario | `username=<login>` | 2 | 2 | `POST /users/signup` 200 |
| Cambio de clave | `User password changed` | el **objetivo** | `username=<objetivo> actor=<quien>` si difieren | 3 | 4 | `POST /users/change_password` 200 |
| Reset de clave | `User password reset` | el **objetivo** | igual, con `actor=` | 4 | 5 | `POST /users/reset_password` 200 |
| Cambio de rol | `User role updated` | el **objetivo** | `username=… actor=… role=<nuevo>` | 4 | 5 | `POST /users/update_role` 200 |

Notas de seguridad:

- Login fallido **no** revela si el usuario existe: la FK es `system` y el nombre reclamado va solo en `description`.
- 503 de base de datos en login **no** genera `LOGIN_FAILED` (no es un rechazo de identidad).
- Cerrar la pestaña o un 401 `SESSION_INVALID` **no** genera `User session expired`: no hay idle-timeout ni usuario resoluble cuando el token ya no está en memoria ni en BD. La toma de sesión sí deja `reason=session_superseded`.
- No hay API de borrado de cuenta → no hay `User account deleted`.

### 4.2 Configuración — `classification = "Configuration"`

| `message` | Acción | `description` |
|---|---|---|
| `Tag created` / `Tag updated` / `Tag deleted` | CRUD de definición de tag | `Tag: <nombre>` |
| `Alarm created` / `Alarm updated` / `Alarm deleted` | CRUD de alarma | nombre / tag |
| `Machine interval updated` | `set_interval` con `user=` | `machine=<n> from=… to=… s` |
| `Machine on_delay updated` | atributo on_delay HMI | `machine=<n> from=… to=…` |
| `Machine attribute updated` | threshold vía `set_value(..., user=)` | `threshold To: <valor>` |
| `System settings updated` | `PUT /settings/update` | `keys=logger_period,…` (sin secretos) |

### 4.3 Control de operador — `classification = "Control"`

| `message` | Acción | `description` |
|---|---|---|
| `Tag value forced` | `POST /tags/write_value` | `tag=<n> from=<prev> to=<nuevo>` — **no** es datalogger |
| `Alarm acknowledged` | ack / ack-all | nombre del tag |
| `Alarm shelved` | shelve con duración | nombre del tag |
| `Alarm unshelved` | unshelve **manual** (`user=`) | nombre del tag |
| `Alarm suppressed` / `Alarm unsuppressed` | supresión por diseño | nombre del tag |
| `Alarm removed from service` / `Alarm returned to service` | OOS / RTS | nombre del tag |
| `Machine switched` | transición HMI | `[<máquina>] from: <a> to: <b>` |

Unshelve automático (watchdog, sin `user=`): `Alarm unshelved automatically`, clasificación **`System`**, FK `system`. Una vez por vencimiento, no por tick.

Transiciones UNACK/RTN por proceso: **`AlarmSummary`**, no `Events` (anti-spam).

Cambios de valor por OPC UA / DAS: **datalogger**, no `Events`.

### 4.4 Sistema, Database, OPC UA, SAF

FK casi siempre `system`. Sirven de contexto de planta, no de “quién pulsó qué”.

| Clasificación | Helper | Ejemplos de `message` |
|---|---|---|
| `System` | `system_lifecycle_audit` | `System started` (boot), `System stopped` (parada limpia / `safe_stop`), `SAF backpressure triggered` / `SAF disk full` (cooldown 60 s), `Alarm unshelved automatically` |
| `OPC UA` | `opcua_audit` | connected / disconnected / reconnect; cooldown de fallos **60 s** |
| `Database` | `db_audit` | **Solo en caliente:** `Database disconnected` y `Database reconnected`. Boot **no** genera `Database connected`. Reconexión HMI: `Database reconnection attempted` |

Anti-spam: un `DISCONNECTED` por outage; fallos de reconnect resumidos en `RECONNECTED`; OPC UA 60 s; SAF 60 s. Acciones de operador **sin** debounce.

Arranque frente a caída de red (el proceso **sigue vivo**):

| Qué ocurrió | Evento |
|---|---|
| Reinicio del contenedor / `systemctl` / corte eléctrico y vuelta | `System started` (clasificación `System`). Un evento por proceso. No se distingue causa. |
| Primera conexión al historiador en ese boot | *silencio* (no es un outage) |
| El historiador se cae con la app ya corriendo | `Database disconnected` |
| El historiador vuelve sin reiniciar PyAutomation | `Database reconnected` (intentos fallidos resumidos en la descripción) |
| Desconexión pedida desde la UI y reconexión posterior | `Database disconnected` + `Database reconnected` |

---

## 5. Trazabilidad: cómo reconstruir “quién hizo qué”

En HMI **Eventos** (`/events`):

1. Filtro por **usuario** → todas las filas cuya FK es ese login (alarmas ack, tags, transiciones, login/logout propios).
2. Filtro por **clasificación** `Security` → identidad/sesión. Login fallido: usuario **`system`**, buscar el login en **descripción**.
3. Filtro por **mensaje** (`Tag value forced`, `Alarm acknowledged`, `Machine switched`, `User logged in`, `System started`, …).
4. Rango de fechas + timezone de planta.

Campo `description` es el vínculo al objeto:

- Alarmas: nombre de tag o de alarma
- Tags: `Tag: <nombre>`
- Máquinas: estado / `threshold To: …`
- Usuario: `username=` y, si aplica, `actor=` (admin que cambia la clave o el rol de otro)

Prioridad y criticidad **no** son el ranking ISA de la alarma; son constantes del emisor. No usarlas como severidad de proceso.

---

## 6. Qué **no** queda en `Events` (y dónde sí, si aplica)

| Acción / dato | ¿En `Events`? | Dónde está |
|---|---|---|
| Lectura de pantallas, filtros, export CSV | No | no se audita (consulta) |
| Escritura de valor de tag (OPC/DAS) | No | datalogger / CVT |
| Forzar valor desde HMI | Sí | `Tag value forced` (`Control`) |
| Estado de alarma por proceso (UNACK, RTN) | No | `AlarmSummary` + página Alarmas |
| Comentario de operador sobre un evento | No como evento nuevo | `Logs` con FK `event` |
| Bitácora operacional libre | No | tabla `Logs` / página Operational Logs |
| Healthcheck, SSL handshake | No | log de proceso |
| Listar usuarios (`GET /users/`) | No | consulta |
| Verificar credenciales sin login | No | `POST /users/credentials_are_valid` |
| Cierre de pestaña / token inválido sin `/logout` | No | sesión queda hasta expiry o toma de sesión |

---

## 7. Mecanismo de login / logout (detalle)

```
  HMI Login.tsx  →  POST /users/login
                         │
                         ├─ 200 + User  →  record LOGIN  (FK = usuario)
                         ├─ 403 creds   →  record LOGIN_FAILED (FK = system)
                         └─ 503 DB      →  sin evento de identidad

  HMI Sidebar logout  →  POST /users/logout
                         1) resolver User por token (memoria o fila DB)
                         2) invalidar token
                         3) record LOGOUT

  Segundo login (misma cuenta)
                         1) _revoke_other_sessions
                         2) record LOGOUT reason=session_superseded
                         3) record LOGIN
                         4) el HMI viejo recibe 401 SESSION_SUPERSEDED
                            (no llama /logout; el evento ya existe)
```

El usuario se resuelve **antes** de borrar el token. Si solo se invalidara primero, `Events.create` no tendría `User` y el logout se perdería.

---

## 8. Código de referencia

| Pieza | Archivo |
|---|---|
| Tabla | `automation/dbmodels/events.py` |
| Motor + SAF | `automation/logger/events.py`, `automation/persistence/outbox.py` |
| Decorador | `automation/utils/decorators.py` → `set_event` |
| Persistencia fail-safe | `automation/utils/system_event_audit.py` (`persist_system_event` = único writer) |
| Tasa / cooldown | `automation/utils/audit_metrics.py` → `GET /api/health/system` (`EVENTS_RATE_PER_MIN`, umbral 30/min) |
| Sesión / identidad | `automation/utils/user_session_audit.py` (`Security`) |
| HTTP usuarios | `automation/modules/users/resources/users.py` |
| HTTP tags / alarmas / máquinas | `modules/{tags,alarms,machines}/resources/` |
| OPC UA / DB / boot / SAF | `opcua_audit.py`, `db_audit.py`, `system_lifecycle_audit.py`, `persistence/journal.py` |
| Tests | `test_user_session_audit.py`, `test_db_connection_audit.py`, `test_system_lifecycle_audit.py`, `test_audit_metrics.py` |

---

## 9. Residual / backlog

1. No hay idle-timeout de sesión ni `User session expired` atable a un usuario en `SESSION_INVALID`.
2. No hay API de borrado de cuenta → no hay `User account deleted`.
3. UNACK/RTN de proceso no van a `Events` (política anti-spam; viven en `AlarmSummary`).
4. `EventFactory` / `IUserEvent` no se introdujeron: el contrato único es `persist_system_event` + `@set_event` + helpers por dominio (SRP sin capas vacías).
5. `System stopped` solo en parada limpia (`safe_stop`); un kill -9 / corte eléctrico no deja ese evento, sí el siguiente `System started`.

---

## 10. Cómo verificar en planta

1. Login operador → `Security` / `User logged in` / `origin=` / `method=password`.
2. Credencial incorrecta → `User login failed`, usuario `system`.
3. Logout sidebar → `reason=user-initiated`.
4. Segundo navegador → `reason=session_superseded` + `User logged in`.
5. Ack de alarma → `Control` / `Alarm acknowledged`.
6. Crear/editar/borrar tag → `Configuration` / `Tag created|updated|deleted`.
7. Forzar valor de tag → `Control` / `Tag value forced` con `from=` y `to=`.
8. Cambiar intervalo u on_delay → `Machine interval updated` / `Machine on_delay updated`.
9. Transición de máquina → `Control` / `Machine switched` con `from:` / `to:`.
10. Reinicio de servicio → `System started`. **No** `Database connected`.
11. Caída de historiador en caliente → `Database disconnected` luego `Database reconnected`.
12. `GET /api/health/system` incluye `EVENTS_RATE_PER_MIN` y `EVENTS_RATE_ALERT`.
