# Auditoría: Operación Conexión Eterna

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Cierre explícito de sockets PostgreSQL; `application_name`; censo `pg_stat_activity`; arranque sin idle huérfanos |
| **Evidencia de planta** | 8 conexiones `idle` abiertas en el boot que no se cerraban |
| **Fecha** | 2026-08-17 |
| **Complementa** | `AUDIT_DB_CONNECTIONS.md`, `AUDIT_NETWORK_TIMEOUT.md`, BE-H4 |
| **Veredicto** | Las 8 idle eran la ráfaga de hidratación (CVT, alarmas, roles, users, OPC, system user, audit boot) en el greenlet principal, **sin `close()` al terminar**. No era un segundo `PostgresqlDatabase`. Política: contexto Peewee en hidratar, `release_ephemeral_historian()` al final de `run()`, teardown HTTP, LoggerWorker conserva 1 y cierra al `stop`, `application_name=PyAutomationIO`, `DB_ACTIVE_CONNECTIONS` desde PostgreSQL |
| **Clasificación** | Auditoría de arquitectura · conexiones · Confidencialidad interna |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Por qué 8 idle tras el arranque? | `connect_to_db` + `init_database` + `_hydrate_runtime_from_db` + `load_db_tags_to_machine` + `create_system_user` + `record_system_started` abrían **un socket en el greenlet de boot** y lo dejaban. Otros greenlets (LoggerWorker, SM, OPC) abrían los suyos. Nadie devolvía el del boot |
| ¿Objetivo idle 1 worker? | **1** (LoggerWorker). Picos 2–3 con un request in-flight. Techo esperado `(workers×2)+5` = **7**. Alerta si **> 10** |
| ¿`gevent.Timeout` en `set_db`? | **No implementado.** No corta libpq. Sigue `connect_timeout=5` + ping throwaway sin `set_db` en outage |
| ¿Cómo se ven en PG? | `application_name = 'PyAutomationIO'` |

---

## 1. Diagnóstico de apertura (Fase 0)

| Momento | Greenlet | Antes | Ahora |
|---|---|---|---|
| `set_db` / `connect()` | boot o watchdog | Socket abierto, no se cierra | Boot: se cierra al terminar la ráfaga. Watchdog (LoggerWorker): se conserva |
| `init_database` + hydrate (OPC, CVT, alarmas, roles, users) | boot | Mismo socket idle eterno | `connection_context()` cierra al salir de hydrate |
| `load_db_tags_to_machine` / `create_system_user` / `record_system_started` | boot | Reutiliza o reabre, idle eterno | `release_ephemeral_historian()` al final de `run()` |
| LoggerWorker | `LoggerWorker` | 1 socket de vida larga | Igual; `close()` en este greenlet al `stop_event` |
| HTTP / REST | request | Teardown appcontext | También `teardown_request` |
| `persist_system_event` (auditores) | quien llame | Podía dejar socket en hilos OPC | `close` si el hilo **no** es LoggerWorker |
| Ping / health | threadpool OS | Throwaway ya cerraba | Sigue throwaway; ahora con `application_name` |
| `_try_get_database_connection_error` | ad-hoc | Segundo `PostgresqlDatabase` | Ping throwaway |

`_close_existing_db` / fallo de `connect`: se cierra el candidato y se restaura `previous`. `close_all` del handle sustituido limpia el censo.

No se reintroduce `PooledPostgresqlDatabase` (BE-H4).

---

## 2. Política de cierre explícito

Regla: **quien abre, cierra**, salvo el LoggerWorker.

```python
# Hidratación de arranque (no el watchdog)
with db.connection_context():
    load_opcua / CVT / alarmas / roles / users

# Final de PyAutomation.run()
self.release_ephemeral_historian()

# Flask
@app.teardown_request
@app.teardown_appcontext
# → db.close() del greenlet del request

# LoggerWorker.run, al stop
close_current_greenlet_connection(self.logger.logger.get_db())
```

`gevent.Timeout` alrededor de `connect()` se rechaza: el C de libpq no cede. El watchdog **no** llama `set_db` si el ping throwaway falla (`AUDIT_NETWORK_TIMEOUT.md`).

---

## 3. Identificación

`apply_remote_db_kwargs` pone `application_name='PyAutomationIO'` (no pisa un valor explícito).

```sql
SELECT pid, state, application_name, backend_start
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid();
```

Tras el deploy, las de la app deben decir `PyAutomationIO`.

---

## 4. Métricas (`GET /api/health/system`)

| Clave | Fuente |
|---|---|
| `DB_CONNECTIONS_COUNT` | Censo cliente (`TrackedPostgresqlDatabase`) |
| `DB_ACTIVE_CONNECTIONS` | `count(*)` en `pg_stat_activity` (`datname = current_database()`, `backend_type = client backend`, sin el pid del probe). Si PG no responde: se usa el censo cliente |
| `DB_NAMED_CONNECTIONS` | Mismo censo filtrado por `application_name = PyAutomationIO` |
| `DB_CONNECTIONS_EXPECTED_MAX` | `(AUTOMATION_GUNICORN_WORKERS \| WEB_CONCURRENCY \| 1) × 2 + 5` |
| `DB_CONNECTIONS_ALERT_THRESHOLD` | default **10** (`AUTOMATION_DB_CONNECTIONS_ALERT`) |
| `DB_CONNECTIONS_ALERT` | `DB_ACTIVE_CONNECTIONS > threshold` |
| `DB_APPLICATION_NAME` | `PyAutomationIO` |
| `DB_INSTANCE_ID` | `id()` del handle Peewee |

El probe de censo es throwaway (abre, cuenta, cierra) y se excluye con `pid <> pg_backend_pid()`.

---

## 5. Criterios CA-DB-ETERNAL

| ID | Criterio | Verificación |
|---|---|---|
| **CA-DB-ET-1** | Tras arranque y 5 min idle, 1 conexión estable (LoggerWorker) | `pg_stat_activity` + `DB_ACTIVE_CONNECTIONS` ≈ 1 |
| **CA-DB-ET-2** | 50 HTTP no dejan pendiente | Count vuelve al idle al terminar |
| **CA-DB-ET-3** | `application_name = PyAutomationIO` | Query §3 |
| **CA-DB-ET-4** | `DB_ACTIVE_CONNECTIONS` en `/api/health/system` alineado con PG | Comparar JSON vs SQL (tolerancia ±1 por in-flight) |
| **CA-DB-ET-5** | Host inalcanzable ≤ 5 s | `connect_timeout`; no `set_db` si el ping falla |
| **CA-DB-ET-6** | Soak 24 h sin pendiente | Muestrear cada hora; idle 2–3 / worker |

Unitario:

```bash
python -m unittest automation.tests.test_db_io automation.tests.test_database_health automation.tests.test_connection_alarms -v
```

Staging: arranque → 5 min → 50 REST → cortar red 10 min → restaurar → soak 24 h.

---

## 6. Runbook

1. `/api/health/system` → `DB_ACTIVE_CONNECTIONS`, `DB_NAMED_CONNECTIONS`, `DB_CONNECTIONS_ALERT`.
2. Alerta (> 10): SQL §3. Si hay `idle` sin `PyAutomationIO`, son clientes ajenos o un binario viejo.
3. Si `DB_NAMED_CONNECTIONS` << `DB_ACTIVE_CONNECTIONS`, hay backends sin etiquetar (versión < este patch o otra app en el mismo `datname`).
4. No reactivar el pool Peewee.
5. Tras outage, el count debe volver al idle de arranque (1 LoggerWorker).

---

## 7. Residual

| ID | Nota |
|---|---|
| ET-R1 | `StateMachineWorker` no debe hacer Peewee en el tick; si un motor escribe SQL directo, volverá a aparecer un idle. Cazar por `application_name` + `query` |
| ET-R2 | `gevent.Timeout` + libpq sigue siendo inútil |
| ET-R3 | El probe de `DB_ACTIVE_CONNECTIONS` es una conexión de milisegundos; no cuenta (pid excluido) |

**Cierre:** el día 1 y el día 1000 deben mostrar el mismo número de backends `PyAutomationIO` en idle. Eso es la Conexión Eterna.
