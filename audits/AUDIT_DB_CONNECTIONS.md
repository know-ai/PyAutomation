# Auditoría: Directiva de Conexiones Eternas

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Ciclo de vida de sockets PostgreSQL/MySQL bajo Gunicorn + gevent + Peewee |
| **Síntoma** | ~18 backends en `pg_stat_activity` con un solo worker; debería ser estable y predecible |
| **Fecha** | 2026-08-17 |
| **Complementa** | `AUDIT_DB_CONNECTION_MEMORY.md` (RAM), `AUDIT_NETWORK_TIMEOUT.md` (hub gevent), BE-H4 (pool) |
| **Veredicto** | Un objeto `Database` **sí** era singleton. Las 18 conexiones eran **sockets por greenlet/hilo** sin `close()`, agravadas por probes Peewee en el threadpool del hub. Política implantada: instancia única contabilizada, ping throwaway, teardown por request, reconnect solo si el host responde |
| **Clasificación** | Auditoría de arquitectura · conexiones · Confidencialidad interna |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Hacía falta un segundo `PostgresqlDatabase`? | **No.** Ya había un handle en `PyAutomation._db`. El fallo no era “demasiadas instancias Peewee” |
| ¿Por qué 18 sockets? | Peewee guarda el TCP en `threading.local` (= greenlet-local). Cada request HTTP, worker y **hilo del threadpool** que ejecutaba `connect()` / `execute_sql()` dejaba un backend abierto |
| ¿Cerrar a lo bruto? | No. El LoggerWorker **debe** conservar 1 conexión. Los greenlets HTTP deben cerrar al terminar el request |
| ¿Reintroducir `PooledPostgresqlDatabase`? | **Prohibido.** BE-H4: el pool bajo gevent no devolvía conexiones → signup/login 503 @ 30 s |
| ¿`gevent.Timeout` en `reconnect_to_db`? | **No.** No corta libpq. El watchdog **no llama** `set_db` si el ping throwaway falla |

Contrato A+:

```
1 instancia Peewee  ×  1 socket por greenlet de vida larga (LoggerWorker)
                  +  0 sockets HTTP al terminar el request
                  +  0 sockets en el threadpool del hub
```

En régimen 1 worker gunicorn, `DB_CONNECTIONS_COUNT` debe situarse en **1–3**, no 18.

---

## 1. Diagnóstico (Fase 0)

### A0.1 Instancias `PostgresqlDatabase`

| Sitio | Rol |
|---|---|
| `set_db` | **Única** fábrica de producción → ahora `TrackedPostgresqlDatabase` |
| `_try_get_database_connection_error` | Antes creaba un segundo `PostgresqlDatabase` para “probar”. Eliminado: ping throwaway |

No hay `PooledPostgresqlDatabase` (a propósito, BE-H4).

### A0.2 `connect()` / `close()`

| Quién | Antes | Ahora |
|---|---|---|
| `set_db` → `_connect_historian` | `connect()` en el **threadpool** del hub | `connect()` en el greenlet que usará el socket (`connect_timeout=5`) |
| `_historian_is_live` / `check_connectivity` / health | `execute_sql("SELECT 1")` en threadpool (Peewee local del hilo OS) | `ping_throwaway`: `psycopg2.connect` → `SELECT 1` → `close()` en `finally` |
| HTTP | sin teardown | `teardown_appcontext` → `db.close()` **solo** del greenlet del request |
| `stop_db` / recambio de handle | `close` / `close_all` | `Tracked*.close_all()` cierra el greenlet actual **y** el censo |

### A0.3 `_close_existing_db` / fallo de `connect`

Si `connect()` falla, el candidato se cierra y se restaura `previous`. No se destruye el enlace vivo a propósito (ya era así). `close_all` del handle sustituido limpia sockets de **otros** greenlets.

### A0.4 Timeout de red

Cubierto en `AUDIT_NETWORK_TIMEOUT.md`. `connect_timeout` libpq = 5 s. El watchdog **no** hace `set_db` mientras el ping throwaway falle, así que un cable tirado no vuelve a bloquear el hub 5 s cada ciclo.

### A0.5 Quién puede abrir un socket

| Actor | ¿Debe tener socket persistente? |
|---|---|
| LoggerWorker (1 greenlet de vida larga) | **Sí, 1** |
| Request Flask / REST | No: abrir al primer SQL, cerrar en teardown |
| Socket.IO `on.tag` | No toca PG (CVT + journal local) |
| Hub threadpool (probes) | **Nunca** Peewee; solo throwaway |
| Health `/api/health/db` | Throwaway (no incrementa `DB_CONNECTIONS_COUNT`) |

---

## 2. Por qué el threadpool del fix de red infló `pg_stat_activity`

`run_uncooperative_db_call(lambda: db.execute_sql("SELECT 1"))` ejecuta Peewee en un **hilo OS** del hub. Peewee asocia el socket a **ese** hilo. El LoggerWorker sigue en otro greenlet y abre el suyo. Los hilos del pool (varios) no hacen `close()`. Resultado típico: 1 worker + N hilos de probe + M requests HTTP = **decenas** de backends.

Eso no contradice el SAF A+ ni el unfreeze de la HMI; es un efecto secundario del probe. La Directiva lo separa: **I/O no cooperativo = cliente desechable**, **Peewee = greenlet dueño**.

---

## 3. Riesgos

| ID | Riesgo | Mitigación |
|---|---|---|
| DB-C1 | Greenlets HTTP sin `close` → `max_connections` en PG | `teardown_appcontext` |
| DB-C2 | Probe Peewee en threadpool → fuga | `ping_throwaway` |
| DB-C3 | Pool Peewee + gevent (BE-H4) | Sigue prohibido |
| DB-C4 | `set_db` en cada ciclo de outage bloquea el hub 5 s | Skip reconnect si ping falla; cerrar socket del worker |
| DB-C5 | Métrica `POOL_CONNECTIONS_USED` siempre 0 | Nueva `DB_CONNECTIONS_COUNT` |

---

## 4. Implementación

| Pieza | Ruta |
|---|---|
| Censo + `TrackedPostgresqlDatabase` + teardown + throwaway | `automation/utils/db_connections.py` |
| Timeouts libpq | `automation/utils/db_io.py` (`connect_timeout`, keepalives) |
| Fábrica única | `automation/core.py` `set_db` |
| Watchdog | `automation/workers/logger.py` |
| Probe logger / health | `automation/logger/core.py`, `automation/health/service.py` |
| Métricas | `GET /api/health/system` |
| Tests | `automation/tests/test_db_io.py` |
| Runbook | `audits/PERFORMANCE_RUNBOOK.md` |

Variables:

| Env | Default | Rol |
|---|---|---|
| `AUTOMATION_DB_CONNECT_TIMEOUT` | `5` | libpq `connect_timeout` |
| `AUTOMATION_DB_PROBE_TIMEOUT` | `2` | Tope del ping throwaway |
| `AUTOMATION_DB_CONNECTIONS_ALERT` | `8` | Umbral de `DB_CONNECTIONS_ALERT` |

---

## 5. Criterios de aceptación

| ID | Criterio | Cómo verificar |
|---|---|---|
| **CA-DB-1** | Una instancia Peewee | `DB_INSTANCE_ID` estable en `/api/health/system`; `id(app._db)` igual en logger y core |
| **CA-DB-2** | `pg_stat_activity` predecible | Idle 1 worker: ~1–3 backends de la app (no 18). Picos = requests in-flight |
| **CA-DB-3** | Connect a host inalcanzable ≤ 5 s | `connect_timeout`; no llamar `set_db` si el ping throwaway ya falló |
| **CA-DB-4** | LoggerWorker no se clava en outage | `replicate_once` sigue; HMI `on.tag` viva (`AUDIT_NETWORK_TIMEOUT.md`) |
| **CA-DB-5** | `DB_CONNECTIONS_COUNT` en `/api/health/system` | JSON: count, alert, threshold, instance id |
| **CA-DB-6** | Soak 24 h sin pendiente | Count plano vs horas; correlacionar con `pg_stat_activity` |

SQL de planta:

```sql
SELECT pid, state, application_name, backend_start, state_change
FROM pg_stat_activity
WHERE datname = current_database()
  AND usename = '<app_user>'
  AND pid <> pg_backend_pid();
```

---

## 6. Pruebas

```bash
python -m unittest automation.tests.test_db_io automation.tests.test_database_health automation.tests.test_connection_alarms -v
```

Staging:

1. Arranque en caliente → `DB_CONNECTIONS_COUNT` 1–3; misma cifra ±1 en `pg_stat_activity`.
2. Navegar HMI 5 min (REST + tendencias) → el count **no** debe subir con cada pantalla; si sube y no baja, el teardown no está registrado.
3. Cable / `iptables DROP` 5432 → HMI viva; **no** debe aparecer un `set_db`/`connect` por ciclo; al restaurar, **un** reconnect y el count vuelve al régimen.
4. Soak 24 h: `DB_CONNECTIONS_COUNT` y `pg_stat_activity` sin pendiente (`CA-DB-6`).

---

## 7. Runbook (operación)

1. `GET /api/health/system` → `DB_CONNECTIONS_COUNT`, `DB_CONNECTIONS_ALERT`.
2. Si alerta: `pg_stat_activity` (query §5). Si PG >> métrica app, hay clientes externos o throwaway in-flight (debe ser transitorio).
3. Si la métrica app crece sola: HTTP sin teardown o alguien volvió a poner Peewee en el threadpool.
4. **No** reactivar `PooledPostgresqlDatabase` para “bajar el 18”.
5. Outage: no vaciar el journal SAF; el count del worker debe caer a 0–1 (socket cerrado) y volver a 1 al reconectar.

---

## 8. Residual

| ID | Nota |
|---|---|
| DB-R1 | Handlers Socket.IO que hagan Peewee fuera de app context no pasan por teardown. Hoy el hot path `on.tag` no usa PG |
| DB-R2 | `ping_throwaway` puede verse 100–200 ms en `pg_stat_activity`; no entra en `DB_CONNECTIONS_COUNT` |
| DB-R3 | `gevent.Timeout` alrededor de `psycopg2.connect` sigue siendo inútil; no reintroducirlo como “cierre” |

**Cierre:** el circulatorio de PyAutomation es **un handle, sockets con dueño, probes desechables, censo en health**. Eso es el estándar A+ de la Directiva de Conexiones Eternas.
