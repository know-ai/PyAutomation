# Auditoría: conexiones BD ↔ memoria RAM del proceso

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) — core + Peewee + historiador remoto |
| **Pregunta** | ¿La forma de gestionar las conexiones entre el core y PostgreSQL/SQLite puede hacer crecer la RAM con el tiempo (p. ej. +300 MB en 24 h)? |
| **Alcance** | Ciclo de vida Peewee (`set_db` / `connect` / `reconnect` / `close`), gevent/gunicorn, métricas de pool, contraste con otros consumidores de RSS |
| **Fecha** | 2026-08-14 |
| **Clasificación** | Auditoría de arquitectura · memoria / conexiones |
| **Veredicto** | **La conexión BD, tal como está hoy, no es un motor típico de fuga monotónica de +300 MB/día.** El handle Peewee es **uno** (sin pool). El coste RAM de TCP/psycopg2 se acota por **concurrencia** (greenlets/hilos que tocaron la BD), no por “días levantada”. Un salto de **~300 MB en un día** casi nunca se explica solo con conexiones: hay que mirar SAF, buffers CVT/DAS, alarmas, logs y fragmentación. **Sí hay riesgos residuales** (conexiones colgadas por greenlet, reconnects, confusión métrica `POOL_CONNECTIONS_USED`). |

---

## 1. Respuesta directa

| Pregunta | Respuesta corta |
|---|---|
| ¿Gestionar conexiones puede subir la RAM? | **Sí, un poco**, por cada socket abierto + buffers de libpq/psycopg2. |
| ¿Eso crece sin límite mientras la app está up? | **No por diseño actual**, si el número de greenlets/hilos que usan la BD se estabiliza. |
| ¿+300 MB en 24 h “por la conexión”? | **Muy improbable** como causa única. Una conexión cliente PG suele ser del orden de **cientos de KB a pocos MB**, no decenas de MB. Harían falta **decenas/cientos** de conexiones huérfanas o un bug distinto. |
| ¿La conexión “no tiene nada que ver” con la memoria? | **Tiene que ver, pero poco** en régimen estable 1-worker. El RSS grande suele venir de **otros** paths (datos en proceso, no del socket SQL). |

---

## 2. Cómo se gestiona la conexión hoy

### 2.1 Modelo actual (post incidente BE-H4)

```
  gunicorn GeventWebSocketWorker (típicamente 1 worker)
           │
           ▼
  PyAutomation.set_db(...)
    · PostgresqlDatabase(...)   ← SIN PooledPostgresqlDatabase
    · candidate.connect(reuse_if_open=True)
    · si OK: cierra el handle previous
    · proxy.initialize(candidate)
           │
           ▼
  db_manager / logger / Peewee models
    · connection() bajo demanda (contexto local al greenlet/hilo)
```

Evidencia en código (`automation/core.py`):

- Comentario explícito: **no** usar `PooledPostgresqlDatabase` porque gevent no devolvía conexiones al pool → signup/login 503 @ ~30 s.
- `kwargs.pop("max_connections" | "stale_timeout" | "timeout")` al crear PG.
- Tras connect OK se cierra el handle **anterior**; si connect falla se **restaura** `previous` (no se deja el proceso sin enlace vivo a propósito).

### 2.2 Qué significa “sin pool” en Peewee

| Comportamiento | Implicación |
|---|---|
| Un objeto `Database` en el proceso | No hay cola `_in_use` de pool (métrica `POOL_CONNECTIONS_USED` ≈ 0 / N/A). |
| `connection()` abre o reutiliza conexión **local al greenlet/hilo** | Cada greenlet que toca Peewee puede tener **su propia** conexión TCP hasta `close()`. |
| No hay `db.close()` al final de cada request Flask | Las conexiones **persisten** mientras el greenlet viva. |
| `stop_db` / reconnect exitoso / `_close_existing_db` | Cierran el handle (o `close_all` si existiera). |

Esto es un **trade-off consciente**:

- **Pros:** signup/login no se cuelgan en checkout de pool.
- **Contras:** más sockets concurrentes hacia PG bajo carga; sin teardown por request.

### 2.3 Reconexión (watchdog)

`LoggerWorker` / `reconnect_to_db`:

1. Probe real (`_historian_is_live` → `SELECT 1`).
2. Si falla: alarma BD; **no** hidratar ni fingir conectado.
3. Si `set_db` del candidato falla: se conserva el handle previo (si existía).
4. Si el nuevo connect OK: se cierra el anterior.

Eso reduce un riesgo histórico: “cada reconnect fallido destruye el enlace y deja objetos muertos”, que **sí** podía contribuir a basura / estados inconsistentes (no necesariamente +300 MB/día, pero sí a churn).

---

## 3. ¿Cuánta RAM “cuesta” una conexión?

Orden de magnitud (cliente Python + libpq; no el servidor PG):

| Concepto | Orden típico |
|---|---|
| 1 conexión `psycopg2` / Peewee idle | ~0.5–3 MB RSS proceso (muy dependiente de versión/buffers) |
| 10 greenlets con BD abierta | ~5–30 MB (si no comparten) |
| 100 conexiones huérfanas | zona de **decenas–baja centena de MB** — ya sería **anomalía** de concurrencia, no “un día normal” |

**Conclusión cuantitativa:** un crecimiento de **+300 MB/día atribuido solo a conexiones** implicaría, en la práctica, **fuga o explosión de greenlets/hilos con `connection()` abierta**, o confundir ese número con otro consumidor (SAF, historiales, HMI). No encaja con “1 conexión estable del worker”.

En el **servidor** PostgreSQL cada backend también consume RAM; eso **no** aparece en el RSS del contenedor de la app (salvo que midas el host de PG).

---

## 4. Hallazgos (riesgos reales vs mitos)

### DB-MEM-1 — Conexiones acotadas por concurrencia, no por uptime

| | |
|---|---|
| **Severidad** | Informativo / diseño |
| **Hecho** | Sin pool, el número de sockets cliente ≈ greenlets/hilos que ya ejecutaron SQL. |
| **Régimen 1 worker, carga estable** | El conteo **se estabiliza**. No “suma 1 conexión por hora de vida”. |
| **Riesgo** | Si algo **crea greenlets/hilos sin reciclar** y cada uno hace Peewee → sockets y RAM **sí** pueden crecer. Eso es fuga de **concurrencia**, no del objeto `PostgresqlDatabase` en sí. |

### DB-MEM-2 — Ausencia de `db.close()` por request (gevent)

| | |
|---|---|
| **Severidad** | Media (escalado), baja (1 worker planta típico) |
| **Hecho** | El runtime no cierra la conexión al terminar cada API call. |
| **Impacto memoria** | Conexiones viven = greenlets vivos. Concurrencia alta ⇒ más RAM **estable**, no necesariamente monotónica 24/7. |
| **Impacto no-memoria** | Más backends en PG; riesgo de `max_connections` del servidor bajo tormenta de requests. |
| **Lección BE-H4** | Meter pool **sin** teardown empeoró latencia; no se debe reintroducir a ciegas. |

### DB-MEM-3 — Reconnect / `set_db` ya no debería “apilar” handles vivos

| | |
|---|---|
| **Severidad** | Baja tras el fix de preservar `previous` |
| **Antes** | Close prematuro + connect fallido → enlace perdido + posibles objetos huérfanos. |
| **Ahora** | Solo se cierra `previous` tras connect OK del candidato. |
| **RAM** | Evita churn de objetos Database; no es la causa típica de +300 MB/día. |

### DB-MEM-4 — `POOL_CONNECTIONS_USED` no mide fugas actuales

| | |
|---|---|
| **Severidad** | Baja (observabilidad) |
| **Hecho** | Health lee `db._in_use` (API de **pool**). Con `PostgresqlDatabase` suele ser **0 / N/A**. |
| **Trampa** | Ver `0` no prueba “cero conexiones TCP”. Prueba “no hay pool Peewee”. |
| **Qué mirar** | En PG: `pg_stat_activity` filtrado por usuario de la app. En app: `RSS_MB`, `THREAD_COUNT`, `PENDING_ROWS`. |

### DB-MEM-5 — Lo que SÍ puede subir ~cientos de MB (y no es “la conexión”)

| Consumidor | ¿Acotado? | ¿Puede +300 MB/día? |
|---|---|---|
| SAF ring RAM (`ring_maxsize=50_000`) | Sí (tope) | Solo si se llena y se mantiene bajo outage; no crece infinito |
| Journal SQLite en disco | Disco, no RSS (salvo page cache OS) | Influye en host, no tanto en heap Python |
| `Buffer` DAS / tags (por `scan_time`) | Por tamaño configurado | Mal config ⇒ buffers grandes **estables**, no “por día” |
| Alarmas / CVT / observers | Debe ser O(1) tras audits | Deriva si hay attach duplicado (otros hallazgos BE) |
| Logs en memoria / handlers | Rotación en disco | Flood ERROR ⇒ CPU/I/O más que 300 MB heap |
| HMI `tagHistory` | 720×64 acotado | Solo proceso navegador, no gunicorn |
| Fragmentación del allocator CPython | Sí con churn | Soak largo puede subir RSS **sin** fuga lógica clara |

Si el operador ve **+300 MB en el contenedor de la app en 24 h**, el checklist correcto **no** empieza por “ Peewee no cierra ”; empieza por `GET /api/health/system` + `GET /api/health/saf` + `pg_stat_activity`.

---

## 5. Escenarios hipotéticos donde la BD *sí* empuja la RAM

1. **Tormenta de greenlets** (bug de spawn, websocket handlers que no terminan) + cada uno hace SQL → N conexiones × ~MB.
2. **Reconnect en bucle** creando candidatos y fallando el GC de referencias (menos probable tras preservar `previous`; vigilar si alguien vuelve a `close` antes de connect).
3. **Reintroducir `PooledPostgresqlDatabase`** sin `db.close()` por request → no solo timeouts; el pool retiene hasta `max_connections` handles **más** espera; no arregla RSS y empeora UX (incidente documentado).
4. **SQLite local del journal + VACUUM INTO** → picos de RSS/page cache al archivar, no monotónicos de “conexión remota”.

Ninguno de esos es el camino feliz de planta (1 worker, PG estable, sin pool).

---

## 6. Relación causal (diagrama)

```
  Uptime 24 h
       │
       ├─► ¿Más greenlets/hilos cada hora? ──sí──► más connection() Peewee ──► +RAM (MB×N)
       │                                              │
       │                                              └─ raro en 1-worker estable
       │
       ├─► ¿SAF PENDING / ring lleno? ──sí──► +RAM acotada / presión disco
       │
       ├─► ¿Buffers CVT/DAS / alarmas creciendo? ──sí──► +RAM (otros audits)
       │
       └─► ¿Solo 1–pocas conexiones PG estables? ──sí──► contribución BD ≈ ruido
                                                         (+300 MB/día → otra causa)
```

---

## 7. Cómo certificarlo en planta (sin adivinar)

| Paso | Acción | Interpretación |
|---|---|---|
| 1 | Baseline: `RSS_MB` de `/api/health/system` al arranque + a las 24 h | Δ RSS |
| 2 | Misma ventana: `THREAD_COUNT`, `PENDING_ROWS`, `OPC_MONITORED_COUNT`, `ALARM_COUNT` | Si RSS↑ y estos planos → fragmentación u otro heap; si PENDING↑ → SAF |
| 3 | En PostgreSQL: `SELECT count(*) FROM pg_stat_activity WHERE usename = '<app>';` cada hora | Si count **plano** y RSS↑ → **no** es la conexión |
| 4 | Si count↑ monotónico → cazar greenlets/hilos / handlers WS | Fuga de concurrencia |
| 5 | No usar solo `POOL_CONNECTIONS_USED` | N/A sin pool |

Umbral runbook ya existente: alerta si `RSS_MB` **+20 % en 24 h** vs baseline (`PERFORMANCE_RUNBOOK.md`). Eso es el criterio operativo; no “300 MB fijos” (300 MB es ~20 % de un proceso de 1.5 GB, o ~60 % de uno de 500 MB).

---

## 8. Criterios de aceptación (memoria ↔ BD)

| ID | Criterio | Métrica |
|---|---|---|
| CA-DBMEM-1 | Con PG estable y 1 worker, el nº de backends de la app en `pg_stat_activity` se estabiliza tras el warm-up | Desviación acotada, sin pendiente clara vs horas |
| CA-DBMEM-2 | `POOL_CONNECTIONS_USED` permanece N/A/0 mientras no haya pool | Health |
| CA-DBMEM-3 | Un Δ RSS de cientos de MB **con** conexiones PG planas no se atribuye a “gestión de conexión” | Correlación RSS vs `pg_stat_activity` |
| CA-DBMEM-4 | Reconnect fallido no deja el proceso sin handle previo ni apila candidatos sin cerrar el OK | Prueba / logs watchdog |
| CA-DBMEM-5 | No reintroducir pool Peewee sin `connect`/`close` (o equivalente) por request/greenlet | Código + runbook §5.1 |

---

## 9. Recomendaciones (sin cambio de código en esta auditoría)

1. **No tratar la conexión remota como sospechoso nº 1** de +300 MB/día.
2. **Instrumentar** correlación: RSS app ↔ `pg_stat_activity` count (misma etiqueta de usuario).
3. **Mantener** la política “sin pool hasta teardown por request” (BE-H4).
4. Si algún día se necesita pool: middleware que haga `db.close()` al final de cada request **y** prueba de carga signup/login bajo gevent antes de merge.
5. Para cazar +300 MB reales: soak 24 h con `/api/health/system` + `/api/health/saf` (ver `AUDIT_BACKEND_PERFORMANCE.md`, `STORE_AND_FORWARD.md`).

---

## 10. Conclusión

La gestión actual de conexiones (**un `PostgresqlDatabase`, sin pool, close del handle previo solo tras connect OK, probe live en reconnect**) está pensada para **correctitud bajo gevent**, no para acumular RAM con el uptime.

- **¿Riesgo de degradación RAM “por la conexión”?** Residual y **acotado por concurrencia**.
- **¿Riesgo creíble de +300 MB/día solo por eso?** **No**, en operación normal.
- **¿La conexión “no tiene nada que ver”?** Tiene un peso **pequeño**; el peso grande del RSS 24/7 está en **datos y buffers del proceso** (SAF, CVT/DAS, alarmas, fragmentación), no en el socket SQL en sí.

Si en planta se observa +300 MB/día, esta auditoría recomienda **descartar primero** la hipótesis “Peewee no cierra” midiendo `pg_stat_activity`, y **seguir** el runbook de deriva RSS hacia SAF/OPC/buffers.

---

## 11. Archivos clave

| Área | Archivo |
|---|---|
| `set_db` / sin pool / close previous | `automation/core.py` |
| Probe live / reconnect | `automation/core.py` (`_historian_is_live`, `reconnect_to_db`) |
| Watchdog | `automation/workers/logger.py` |
| `stop_db` | `automation/logger/core.py` |
| Health RSS / pool metric | `automation/modules/health/resources/health.py` |
| Incidente pool gevent | `audits/AUDIT_BACKEND_PERFORMANCE.md` § BE-H4 |
| Runbook RSS | `audits/PERFORMANCE_RUNBOOK.md` §5.1 |
| Ring / pending acotados | `automation/persistence/config.py`, `journal.py` |
