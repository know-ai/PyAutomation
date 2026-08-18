# Auditoría: timeout de red vs Store-and-Forward (HMI congelada)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | LoggerWorker, `set_db` / `reconnect_to_db` / `_historian_is_live`, `check_connectivity`, emisión Socket.IO `on.tag` |
| **Síntoma en planta** | BD remota (otro host): al desconectar el cable, tendencias en tiempo real dejan de refrescar. Logs: `No route to host` + `Historian connectivity probe failed; reconnection not established` |
| **Contraste** | BD dockerizada en el mismo host, contenedor apagado: SAF acumula PENDING y replica al volver. HMI sigue viva |
| **Fecha** | 2026-08-17 |
| **Metodología** | Revisión estática del hot path, contraste gevent/libpq, corrección implementada |
| **Veredicto** | El SAF **A+ se sostiene** (journal local). El fallo es **resiliencia al timeout TCP**: `psycopg2`/`libpq` bloquea el hub de gevent. Corregido con `connect_timeout` + I/O en threadpool nativo |
| **Clasificación** | Auditoría de arquitectura · red / gevent · Confidencialidad interna |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Falló el Store-and-Forward? | **No.** El journal SQLite sigue siendo la fuente de verdad. Los samples se encolan en `TagObserver` sin tocar PostgreSQL |
| ¿Por qué la HMI se congela solo con BD remota? | `No route to host` / socket medio-abierto espera el timeout del **SO** (decenas de segundos a minutos). `Connection refused` local falla en milisegundos |
| ¿`on.tag` depende de la BD? | **No.** `CVTEngine.set_value` emite Socket.IO sin consultar el historiador |
| ¿Entonces por qué no llega `on.tag`? | `wsgi.py` hace `gevent.monkey.patch_all()`. `LoggerWorker` es un `Thread` **parcheado a greenlet**. `libpq` no cede el CPU: el **hub entero** (incluido Socket.IO) se queda parado |
| ¿`gevent.Timeout` alrededor de `connect()` sirve? | **No.** El timeout de gevent no interrumpe una llamada C de libpq. Hay que usar `connect_timeout` de libpq **y** ejecutar esa llamada en el threadpool del hub |

---

## 1. Evidencia en código (antes de la corrección)

### 1.1 Bucle del LoggerWorker — síncrono y bloqueante

`automation/workers/logger.py` `run()` (pre-fix):

1. `check_connectivity()` → `SELECT 1` en el handle Peewee actual
2. si falla → `reconnect_to_db()` → `set_db()` → `candidate.connect()`
3. `_historian_is_live()` → otro `SELECT 1`
4. **después** `replicate_once()`
5. `check_opcua_connection()`
6. `time.sleep(period)`

Si (1), (2) o (3) tardan 30–180 s, el ciclo no avanza. El journal local **sí** sigue recibiendo `enqueue` desde el hot path; lo que muere es el **hub**.

### 1.2 `set_db` sin `connect_timeout`

```python
# automation/core.py (antes)
kwargs.pop("timeout", None)   # timeout de *pool* Peewee, no de TCP
candidate = PostgresqlDatabase(db_name, **kwargs)
candidate.connect(reuse_if_open=True)
```

Peewee reenvía kwargs a `psycopg2.connect()`. **No** se pasaba `connect_timeout`. El presupuesto lo fija el kernel (`tcp_syn_retries`).

`timeout` se elimina a propósito (pool). Eso **no** instala un timeout de conexión TCP.

### 1.3 `logging_error_handler` traga el fallo de `set_db`

`set_db` está decorado con `@logging_error_handler`, que **no re-lanza**. Secuencia observada en planta:

1. `ERROR: connection to server at "192.168.1.95", port 5432 failed: No route to host` — libpq/psycopg2
2. el `raise` interno de `set_db` lo traga el decorador
3. `reconnect_to_db` continúa y llama `_historian_is_live()` sobre el handle **anterior** (socket medio-abierto)
4. `CRITICAL: Historian connectivity probe failed; reconnection not established`

Dos bloqueos encadenados: `connect()` largo + `SELECT 1` largo.

### 1.4 `check_connectivity` — peor que `connect()`

```python
self._db.execute_sql('SELECT 1;')
```

Con el contenedor local apagado: `ECONNRESET` / `connection refused` inmediato.

Con cable tirado sobre un socket **ya establecido**: el cliente espera retransmisiones TCP (`tcp_retries2`, a menudo **minutos**). Ese es el primer hang del watchdog, **antes** de `reconnect_to_db`.

`PeeweeRemoteDB.is_reachable()` llama al mismo `check_connectivity()`, así que `replicate_once()` también podía clavar el hub.

### 1.5 Socket.IO no consulta la BD

```627:668:automation/tags/cvt.py
    def set_value(self, id:str, value, timestamp:datetime):
        ...
        with tag._lock:
            tag.set_value(value=value, timestamp=timestamp)
            if self.sio:
                payload = tag.serialize_socket()
        if payload is not None and self.sio:
            self.sio.emit("on.tag", data=payload)
```

`TagObserver.update()` solo hace `get_persistence_gateway().enqueue()` (journal local). **No hay dependencia funcional de PostgreSQL.** El freeze es de **planificación del event loop**, no de un `if not db: return` en CVT.

### 1.6 Gevent + libpq

| Pieza | Hecho |
|---|---|
| `wsgi.py` | `gevent.monkey.patch_all()` **antes** de crear la app |
| Worker gunicorn | `GeventWebSocketWorker` |
| `BaseWorker` | `threading.Thread` → greenlet bajo el monkey-patch |
| `psycopg2` | libpq, sockets C, **no cooperativo** |
| Health previo | `with gevent.Timeout(2): db.execute_sql("SELECT 1")` — el timeout **no dispara** mientras libpq tiene el OS thread |

El health HMI ya documentaba el hang; su mitigación (`gevent.Timeout`) era insuficiente para libpq.

---

## 2. Por qué el SAF “funcionó” en un caso y no en el otro

| Escenario | Resultado de `connect()` / `SELECT 1` | Hub gevent | HMI | Journal SAF |
|---|---|---|---|---|
| Postgres Docker en el mismo host, `docker stop` | `Connection refused` (RST inmediato) | Casi no se bloquea | Tendencias vivas | PENDING → replica al volver |
| Postgres en otro host, cable de red | `No route to host` o socket medio-abierto (timeout largo del SO) | Hub congelado en libpq | `on.tag` no se drena | PENDING se acumula **pero nadie lo ve en vivo** |

Durabilidad: **ambos escenarios cumplen el contrato A+.** Disponibilidad de HMI: solo el primero.

---

## 3. Hipótesis vs evidencia

| # | Hipótesis | Veredicto |
|---|---|---|
| 1 | `set_db` bloquea 30–60 s por `No route to host` | **Confirmada.** Sin `connect_timeout`, el presupuesto es del kernel |
| 2 | `LoggerWorker.run` no avanza mientras `set_db` bloquea | **Confirmada.** Era síncrono y **antes** de `replicate_once` |
| 3 | `sio.emit` se retrasa porque el bucle de gevent está ocupado | **Confirmada.** No es un `if db`; es el hub único |
| 4 | `check_connectivity` también bloquea en `SELECT 1` | **Confirmada**, y en outage de cable es el hang **más largo** |

---

## 4. Corrección implementada

No se usa `with gevent.Timeout: connect()` como mecanismo principal: **no corta libpq.**

### 4.1 `automation/utils/db_io.py`

- `apply_remote_db_kwargs`: `connect_timeout=5` (libpq / MySQL), keepalives TCP agresivos. Env: `AUTOMATION_DB_CONNECT_TIMEOUT` (1–30 s)
- `run_uncooperative_db_call`: ejecuta `connect()` / `SELECT 1` en `gevent.get_hub().threadpool` (hilos OS reales). `.get(timeout=)` **sí cede** el hub → Socket.IO sigue
- Cooldown de probe muerto: evita apilar varios `SELECT 1` de 2 s en el mismo ciclo. Env: `AUTOMATION_DB_PROBE_TIMEOUT` (default 2 s)

### 4.2 `set_db` / `_connect_historian`

kwargs PostgreSQL/MySQL pasan por `apply_remote_db_kwargs`. El `connect()` remoto va al threadpool con presupuesto `connect_timeout + 1 s`.

### 4.3 `reconnect_to_db` / `connect_to_db`

Si `@logging_error_handler` tragó el fallo, `_db_live` queda `False` y **no** se lanza `_historian_is_live()` contra el socket zombi. Log con duración en segundos.

### 4.4 `check_connectivity` y `_historian_is_live`

`SELECT 1` acotado vía `run_uncooperative_db_call`.

### 4.5 `LoggerWorker.run`

1. `replicate_once()` primero (el journal no espera al TCP remoto)
2. watchdog de BD con log si el probe/reconnect ≥ 2 s
3. OPC UA
4. `sleep` solo el resto del periodo

### 4.6 Health HMI

`DatabaseHealthService` usa el mismo helper (el `gevent.Timeout` cooperativo se retira).

---

## 5. Código de referencia

| Pieza | Ruta |
|---|---|
| Timeouts y threadpool | `automation/utils/db_io.py` |
| Connect Peewee | `automation/core.py` → `_connect_historian`, `set_db` |
| Probe | `automation/core.py` → `_historian_is_live` |
| Watchdog | `automation/logger/core.py` → `check_connectivity` |
| Worker | `automation/workers/logger.py` → `run` |
| Health | `automation/health/service.py` |
| `on.tag` (sin BD) | `automation/tags/cvt.py` → `set_value` |
| Journal | `automation/tags/tag.py` → `TagObserver.update` |
| Tests | `automation/tests/test_db_io.py` |

---

## 6. Pruebas de staging (reproducir el incidente)

**A — control (debe seguir verde, SAF clásico)**

1. App y Postgres en el mismo host (compose).
2. HMI tendencias en tiempo real visibles.
3. `docker stop` del contenedor Postgres (no borrar volúmenes).
4. Esperado: HMI **sigue** refrescando; journal `PENDING` crece; logs `connection refused` en **&lt; 1 s** por intento.
5. `docker start` Postgres: replica sin pérdida.

**B — cable / ruta (el bug original)**

1. App en el edge; Postgres en `192.168.1.x` (otro host).
2. HMI tendencias vivas.
3. **No apagar Postgres.** Quitar cable, bajar el puerto del switch, o `iptables -A OUTPUT -p tcp --dport 5432 -j DROP` hacia el historiador (DROP simula silencio; REJECT se parece más a `No route to host`).
4. Esperado **después del fix**:
   - HMI **sigue** emitiendo `on.tag` (jitter ≤ `AUTOMATION_DB_PROBE_TIMEOUT`, default 2 s, no congelación de 30–180 s)
   - Log `Historian TCP connect failed; reconnection not established (N.Ns)` con N ≈ 5
   - `SAF_QUEUE_DEPTH` sube; al restaurar la red, replica
5. Esperado **antes del fix** (no repetir en planta): HMI congelada; hueco de decenas de segundos entre el `ERROR` de libpq y el `CRITICAL` del probe.

**C — unitario**

```bash
python -m unittest automation.tests.test_db_io automation.tests.test_database_health automation.tests.test_connection_alarms
```

---

## 7. Despliegue

El cambio vive en PyAutomationIO. Hay que publicar un patch (p. ej. `2.8.1`) e instalarlo en la imagen de borde (`requirements.prod.txt`). Variables opcionales:

| Variable | Default | Rol |
|---|---|---|
| `AUTOMATION_DB_CONNECT_TIMEOUT` | `5` | Segundos de `psycopg2.connect` / MySQL connect |
| `AUTOMATION_DB_PROBE_TIMEOUT` | `2` | Tope de `SELECT 1` |

No hace falta tocar el journal SAF ni vaciar PostgreSQL.

---

## 8. Residual

| ID | Riesgo | Mitigación |
|---|---|---|
| NT-R1 | Tras timeout, el hilo OS puede seguir dentro de libpq unos segundos | Aceptable; el hub ya no espera. El handle se sustituye en el siguiente `set_db` |
| NT-R2 | `statement_timeout` de PostgreSQL **no** ayuda si el cable está caído (es server-side) | No usarlo como mitigación de red |
| NT-R3 | OPC UA `reconnect()` en el mismo worker aún puede bloquear si el stack OPC no es cooperativo | Fuera de este incidente; no mezcla el historiador |

**Cierre:** el certificado A+ de SAF no se revoca. Se añade el contrato: **un historiador inalcanzable no puede detener el hub de gevent.**
