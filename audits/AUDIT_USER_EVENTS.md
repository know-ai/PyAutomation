# Auditoría de eventos de usuario — tabla `Events`

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/Events.tsx`) |
| **Alcance** | Qué se persiste en la tabla `Events`, qué acciones de operador quedan trazadas (quién / qué / cuándo) y cómo se registran login / logout |
| **Fuera de alcance** | Bitácora operacional (`Logs` / `operational-logs`), histórico de alarmas (`AlarmSummary`), datalogger de tags, logs de aplicación (`pyautomation` logger) |
| **Fecha** | 2026-08-16 |
| **Clasificación** | Auditoría de trazabilidad de acciones · confidencialidad interna |
| **Metodología** | Revisión de código de `@set_event`, `persist_system_event`, recursos HTTP y HMI. Tests unitarios del helper de sesión |
| **Complementa** | `audits/AUDIT_LOGGING.md`, `audits/STORE_AND_FORWARD.md`, `audits/PERSISTENCE_FLOW.md` |
| **Veredicto** | **C+** respecto a un trail de auditoría industrial. Login / logout / identidad quedan en `Events`. Acciones de alarma, tag y transiciones de máquina desde la HMI quedan atadas al usuario de la sesión. Siguen huecos: escritura de valor de tag, alta de alarma en reload, cierre de pestaña sin logout, e intervalo/`on_delay` sin evento propio |

---

## 1. Respuesta directa

**Antes de este cambio no había eventos de login ni de logout.** La tabla `Events` existía y el HMI `/events` las mostraba, pero `POST /api/users/login` y `POST /api/users/logout` no escribían nada.

**Ahora sí.** Cada inicio de sesión, cada fallo de credenciales y cada cierre de sesión (explícito o por toma de sesión) se persiste en `Events` con `classification = "User"`.

Filtrar en la página Eventos:

- clasificación **User**
- mensaje `User logged in` / `User logged out` / `User login failed`

---

## 2. Modelo: qué es un evento

Tabla Peewee `Events` (`automation/dbmodels/events.py`):

| Columna | Tipo | Rol de auditoría |
|---|---|---|
| `timestamp` | UTC | Cuándo |
| `user` | FK → `Users` **obligatoria** | Quién (o `system` si el actor no es un usuario de sesión) |
| `message` | varchar(256) | Qué ocurrió (texto corto, estable) |
| `description` | varchar(256), nullable | Detalle (nombre de tag/alarma, `username=…`, `actor=…`) |
| `classification` | varchar(128) | Familia: `User`, `Alarm`, `Tag`, `State Machine`, `OPC UA`, `Database` |
| `priority` | int | 1–5 según el emisor (valores fijos en código, no ISA-18.2) |
| `criticity` | int | 1–5 según el emisor |

Reglas duras:

- `Events.create` exige un objeto `modules.users.users.User`. Sin usuario no hay fila.
- `message` y `description` se recortan a **256** caracteres en la vía `persist_system_event`. `@set_event` **no** recorta: un `description` más largo puede fallar al insertar.
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

### 4.1 Identidad y sesión — `classification = "User"`

Helper: `automation/utils/user_session_audit.py`  
Cableado: `automation/modules/users/resources/users.py` y toma de sesión en `Users._revoke_other_sessions`.

| Acción | `message` | FK `user` | `description` (patrón) | P | C | Disparo |
|---|---|---|---|---|---|---|
| Login OK | `User logged in` | el autenticado | `username=<login>` | 2 | 2 | `POST /users/login` 200 |
| Login fallido | `User login failed` | **`system`** | `username=<reclamado> reason=invalid_credentials` | 3 | 4 | `POST /users/login` 403 de credenciales |
| Logout explícito | `User logged out` | el de la sesión | `username=<login>` | 2 | 2 | `POST /users/logout` (sidebar HMI) |
| Toma de sesión | `User logged out` | el mismo usuario | `username=<login> reason=session_superseded` | 2 | 2 | segundo login (una sesión activa) |
| Alta de cuenta | `User account created` | el nuevo usuario | `username=<login>` | 2 | 2 | `POST /users/signup` 200 |
| Cambio de clave | `User password changed` | el **objetivo** | `username=<objetivo> actor=<quien>` si difieren | 3 | 4 | `POST /users/change_password` 200 |
| Reset de clave | `User password reset` | el **objetivo** | igual, con `actor=` | 4 | 5 | `POST /users/reset_password` 200 |
| Cambio de rol | `User role updated` | el **objetivo** | `username=… actor=… role=<nuevo>` | 4 | 5 | `POST /users/update_role` 200 |

Notas de seguridad:

- Login fallido **no** revela si el usuario existe: la FK es `system` y el nombre reclamado va solo en `description`.
- 503 de base de datos en login **no** genera `LOGIN_FAILED` (no es un rechazo de identidad).
- Cerrar la pestaña o un 401 `SESSION_INVALID` en el interceptor Axios **no** llama a `/users/logout`. No hay fila `LOGOUT` en esos casos. La toma de sesión sí deja `reason=session_superseded`.

### 4.2 Alarmas — `classification = "Alarm"`

Métodos con `@set_event` en `automation/alarms/__init__.py` y `managers/alarms.py`. La API pasa `user=Api.get_current_user()`.

| `message` | Acción de usuario (HMI / API) | `description` típica |
|---|---|---|
| `Created` | Alta de alarma (`POST /alarms/add`) | nombre de la alarma |
| `Updated` | Edición de alarma (`POST /alarms/update`) | mensaje interno del `put` |
| `Deleted` | Borrado (`DELETE /alarms/delete/<id>`) | id / nombre según retorno |
| `Acknowledged` | Ack / ack-all | nombre del tag |
| `Shelved` | Shelve con duración | nombre del tag |
| `Unshelved` | Unshelve **manual** (si se pasa `user=`) | nombre del tag |
| `Designed suppression` | Supresión por diseño | nombre del tag |
| `Designed unsuppression` | Quitar supresión por diseño | nombre del tag |
| `Removed from service` | Fuera de servicio | nombre del tag |
| `Returned to service` | Volver a servicio | nombre del tag |

Huecos:

- Unshelve **automático** por vencimiento de tiempo (`alarm_manager` watchdog) llama `unshelve` **sin** `user=` → no hay evento.
- Transiciones de alarma por proceso (UNACK, RTN, etc.) van al **resumen de alarmas**, no a `Events`.

### 4.3 Tags — `classification = "Tag"`

`CVT.set_tag` / `update_tag` / `delete_tag` tienen `@set_event`. La API HMI ahora pasa el usuario de sesión.

| `message` | Acción | P | C |
|---|---|---|---|
| `Created` | Alta de tag | 1 | 1 |
| `Updated` | Edición de definición | 1 | 3 |
| `Updated` | Borrado de tag (mismo message que update) | 1 | 5 |

`description` = último elemento de la tupla de retorno (p. ej. `Tag: <nombre>`).

**No** se audita en `Events`:

- `POST /tags/write_value` (escritura de valor de proceso). Sería un flood, no un trail de configuración.
- Cambios de valor por OPC UA / DAS.

### 4.4 Máquinas de estado — `classification = "State Machine"`

| `message` | Acción de usuario | Notas |
|---|---|---|
| `Switched` | `PUT /machines/<name>/transition` con `user=` | transiciones de operador (start / wait / restart / …) |
| `Switched` | cambio de `buffer_size` (restart + wait inducidos por la API) | el usuario queda en ambas transiciones |
| `Attribute updated` | cambio de `threshold` vía `set_value(..., user=)` | `description` tipo `threshold To: <valor>` |

Huecos:

- `set_interval` acepta `user=` pero **no** tiene `@set_event` y retorna `None` → **no** hay evento de intervalo.
- `on_delay` se asigna al atributo sin `set_value` → **no** hay evento.
- Transiciones internas del motor (ciclo de detección, `to="restart"` desde código de planta **sin** `user=`) no quedan atadas a un operador. Es correcto: no son acciones de usuario.

### 4.5 Sistema (no son acciones de operador)

FK casi siempre `system`. Sirven de contexto de planta, no de “quién pulsó qué”.

| Clasificación | Helper | Ejemplos de `message` |
|---|---|---|
| `System` | `system_lifecycle_audit.record_system_started` | `System started` — un evento por proceso al arrancar (reinicio manual, orquestador o corte eléctrico: no se distinguen) |
| `OPC UA` | `opcua_audit.record_opcua_connection_event` | `OPC UA client connected` / `… disconnected` / reconnect |
| `Database` | `db_audit.DatabaseConnectionAuditor` | **Solo en caliente:** `Database disconnected` y `Database reconnected`. El attach inicial al boot **no** genera `Database connected` |

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
2. Filtro por **clasificación** `User` → solo identidad/sesión. Los login fallidos aparecen bajo usuario **`system`**; buscar el login reclamado en **descripción** (`username=`).
3. Filtro por **mensaje** (`Acknowledged`, `Created`, `Switched`, `User logged in`, …).
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
| Escritura de valor de tag | No | datalogger / CVT |
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
| Persistencia fail-safe | `automation/utils/system_event_audit.py` |
| Sesión / identidad | `automation/utils/user_session_audit.py` |
| HTTP usuarios | `automation/modules/users/resources/users.py` |
| HTTP tags / alarmas / máquinas | `modules/{tags,alarms,machines}/resources/` |
| OPC UA / DB / boot | `automation/utils/opcua_audit.py`, `db_audit.py`, `system_lifecycle_audit.py` |
| Tests | `automation/tests/test_user_session_audit.py`, `test_db_connection_audit.py`, `test_system_lifecycle_audit.py` |

---

## 9. Residual / backlog

1. `set_interval` y `on_delay`: cambio de operador sin fila en `Events`.
2. Message de borrado de tag es `Updated` (crítico 5) — confunde filtros por mensaje; convendría `Deleted`.
3. `@set_event` no recorta a 256 caracteres.
4. Logout por cierre de navegador / `SESSION_INVALID` sin round-trip a `/users/logout`.
5. Alta de alarma no usa `@set_event` en `append_alarm` (evita falsos `Created` en reload); el recurso HTTP persiste `Created` solo si el mensaje es `Alarm creation successful`.
6. Escritura de tag (`write_value`) deliberadamente fuera del trail; si un procedimiento de planta exige “quién forzó el setpoint”, hay que añadir un evento acotado (no por cada sample OPC).

---

## 10. Cómo verificar en planta

1. Entrar al HMI con un operador → Eventos, clasificación `User`, mensaje `User logged in`, columna usuario = ese login.
2. Credencial incorrecta → misma clasificación, mensaje `User login failed`, usuario `system`, descripción con el nombre tecleado.
3. Logout en el sidebar → `User logged out`.
4. Login en un segundo navegador → `User logged out` con `reason=session_superseded` y un `User logged in` nuevo.
5. Ack de una alarma → clasificación `Alarm`, mensaje `Acknowledged`, usuario = operador.
6. Crear o editar un tag desde Definiciones → clasificación `Tag`, usuario = operador.
7. Transición manual de máquina → clasificación `State Machine`, mensaje `Switched`.
8. Reiniciar el servicio → clasificación `System`, mensaje `System started`. **No** debe aparecer `Database connected` por ese boot.
9. Tirar el historiador con la app viva y levantarlo → `Database disconnected` y luego `Database reconnected`, sin un segundo `System started`.
