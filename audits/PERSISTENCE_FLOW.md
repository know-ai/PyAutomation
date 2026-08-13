# Auditoría: Flujo activo de persistencia → PostgreSQL

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Cómo llegan TagValue / Alarmas / Eventos / Logs al historiador Postgres |
| **Clasificación** | Auditoría de flujo de datos · Implementación activa (post Store-and-Forward) |
| **Fecha** | 2026-08-13 |
| **Complementa** | `audits/STORE_AND_FORWARD.md` (durabilidad / exact-once) |
| **Veredicto** | La persistencia **no** depende del mapeo OPC UA. OPC UA es un **productor de valores** hacia el CVT; el historiador se dispara por **cualquier** `Tag.set_value` → `notify` → `TagObserver` cuando el tag tiene observer adjunto. |

---

## 0. Respuesta directa a la paradoja observada

> “En teoría el CVT mapea a cliente OPC UA y solo entonces debería persistir… pero con SAF veo registros sin mapear Tags al cliente OPC UA.”

**Correcto respecto a lo que ves; incorrecto respecto a la teoría antigua.**

| Creencia (legado mental) | Implementación activa |
|---|---|
| OPC UA subscription → CVT → cola → BD | **Cualquier** actualización del Tag en CVT → Observer → journal SAF → Postgres |
| Sin `opcua_address` / `node_namespace` no hay histórico | Sin OPC UA **no hay adquisición remota**, pero sí hay persistencia si algo llama `cvt.set_value` / `Tag.set_value` |
| El `LoggerWorker` “thread-safe” escribe TagValue desde `_tag_queue` | `_tag_queue` quedó **huérfana** para escritura. El worker solo llama `replicate_once()` sobre el journal |

El mapeo OPC UA controla **quién mete valores en el CVT**, no **quién habilita el historiador**.

La habilitación del historiador ocurre en `create_tag` / `load_db_to_cvt` cuando hay BD conectada:

```509:534:automation/core.py
            if self.is_db_connected():
                self.logger_engine.set_tag(tag=tag)
                self.db_manager.attach(tag_name=name)
            ...
            if resolved_opcua_address and node_namespace:
                ...
                    self.subscribe_opcua(...)
```

- `set_tag` → fila de configuración en tabla `Tags` (metadata).
- `db_manager.attach` → `TagObserver` en el tag (histórico TagValue).
- `subscribe_opcua` → **opcional**; solo si hay cliente/nodo.

Por eso un tag **sin** OPC UA puede generar filas en `TagValue` si, por ejemplo:

1. Alguien escribe por API (`POST /api/tags/write_value`).
2. Una state machine / modelo interno hace `cvt.set_value`.
3. `AlarmManager.attach` adjunta otro `TagObserver` al mismo tag.
4. Tests o scripts locales llaman `set_value`.

Y un tag **con** OPC UA sigue el mismo camino de persistencia: la subscription solo alimenta el CVT.

---

## 0.1 ¿Por qué sin mapear el Tag al cliente OPC UA igual se registra en la BD?

### Respuesta en una frase

Porque el historiador se enciende al **cargar/crear el tag con BD conectada** (`db_manager.attach`), no al suscribir el nodo OPC UA. En idetectfugas (y en cualquier app con state machines), los motores **escriben solos** al CVT (`leak`, `threshold`, `cusum_statistic`, etc.); eso basta para generar `TagValue` aunque `opcua_address` / `node_namespace` estén vacíos.

### Cadena causal (sin OPC UA)

```
1. Arranque / connect_to_db
2. load_db_to_cvt → create_tag(reload=True) para cada tag activo
3. is_db_connected() == True
       ├─ logger_engine.set_tag(tag)     → metadata en tabla Tags
       └─ db_manager.attach(tag_name)    → TagObserver en el Tag  ← AQUÍ nace el histórico
4. subscribe_opcua(...) se OMITTE si no hay address/node
5. Más tarde: LDS/PPA/NPW/API/script llama set_value sobre ese tag
6. Tag.notify() → TagObserver.enqueue → journal "tag" → Postgres TagValue
```

El paso 4 (mapeo OPC UA) **nunca entra** en esa cadena. Si 3 y 5 ocurren, hay registro en BD.

### Qué es “mapear al cliente OPC UA” vs qué es “habilitar histórico”

| Concepto | Campos / acción | Efecto |
|---|---|---|
| Mapear a OPC UA | `opcua_client_name`, `opcua_address`, `node_namespace` + `subscribe_opcua` | El PLC/servidor empuja valores al CVT vía `datachange_notification` |
| Habilitar histórico | `db_manager.attach` (si BD up) | Cualquier cambio del Tag notifica al SAF / Postgres |
| Metadata remota | `logger_engine.set_tag` | Asegura fila en tabla `Tags` (FK de `TagValue`) |

Sin mapeo OPC UA: **no hay datachange del PLC**, pero el Tag sigue vivo en memoria y con observer.

### Quién escribe el valor si no es OPC UA (caso planta idetectfugas)

En `gitlab/intelcon/idetectfugas`, los tags tipo `LDS.leak`, `PPA.threshold`, `NPW.cusum_statistic`, `Observer.leak_location_*`, etc. se actualizan desde las **state machines** con `attr.set_value(...)` / `ProcessType.set_value` → `cvt.set_value`, no desde una subscription OPC UA.

Evidencia de productores internos (muestra, no exhaustiva):

- `app/core.py` — LDS: `leak`, `leak_flow`, `leak_location_*`, `leak_volume`, …
- `app/modules/ppa/__init__.py` — `threshold`, `t_statistic`, `leak`, …
- `app/modules/sa/__init__.py`, NPW, PFM, RTTM, Observer — mismo patrón

Flujo interno típico:

```
StateMachine / ProcessType.set_value(...)
    → CVTEngine.set_value(id=tag.id, value=..., timestamp=...)
        → Tag.set_value → notify()
            → TagObserver → PersistenceGateway.enqueue(tag_sample)
                → journal → TagValue
```

También pueden escribir:

| Productor | Ruta |
|---|---|
| HMI / API | `POST /api/tags/write_value` → `app.cvt.set_value` |
| `automation/models.py` | `StringType`/`FloatType`/etc. con `tag` ligado → `cvt.set_value` |
| Tests / scripts | llamada directa a `set_value` |
| Segundo observer | `AlarmManager.attach` también pone un `TagObserver` |

### Por qué SAF hace más visible este comportamiento

Antes (cola RAM + `write_tags` solo con conectividad) el mismo attach + `set_value` ya podía historizar tags sin OPC UA, pero fallos de cola/BD ocultaban el efecto. Con Store-and-Forward:

1. El journal local **no descarta** la muestra cuando el remoto titubea.
2. El replicador **empuja** PENDING a Postgres de forma continua.
3. Tags calculados (alta tasa de escritura de motores) llenan `TagValue` aunque el PLC no esté mapeado.

SAF no “inventó” el registro sin OPC UA; **dejó de perderse** lo que las máquinas ya escribían al CVT.

### Criterio de verificación en planta

Para un tag concreto (ej. `LDS.leak`):

1. ¿Tiene `opcua_address` / `node_namespace`? → Si no, **no** viene del PLC.
2. ¿Existe fila reciente en journal `domain='tag'` / `entity_id='LDS.leak'`? → Sí ⇒ alguien llamó `set_value`.
3. ¿Quién? Buscar en la app `set_value(... name="leak")` o escritura al ProcessType ligado a ese tag (casi siempre LDS/PPA/…).

Si el negocio exige “solo historizar tags mapeados a OPC UA”, eso **no está implementado**: habría que condicionar `db_manager.attach` (o el `enqueue` del observer) a la presencia de mapeo OPC UA. Hoy el diseño es deliberadamente “historizar todo tag adjunto que cambie”.

---

## 1. Diagrama del flujo activo (TagValue)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTORES DE VALOR                             │
│  OPC UA datachange │ API write_value │ StateMachine │ Models │ scripts   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  CVTEngine.set_value (cola thread-safe)
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  CVT (Current Value Table)                                               │
│  Tag.set_value → deadband → value/timestamp → Tag.notify()               │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  Observadores adjuntos
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
         TagObserver     MachineObserver    (otros)
         (histórico)     (máquinas)
                │
                │  PersistableRecord.tag_sample(tag, value, timestamp)
                │  PersistenceGateway.enqueue()
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Journal local SQLite WAL  db/saf/journal.db                             │
│  domain = "tag" · status PENDING → SENT                                  │
│  Tags: ring RAM (~10 ms) → COMMIT WAL                                    │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  LoggerWorker.replicate_once()  (~period)
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PeeweeRemoteDB + TagValuePayloadMapper + IdempotentBatchInserter         │
│  Tags.read_by_name → INSERT TagValue ON CONFLICT DO NOTHING              │
│  ACK → mark_sent                                                         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
                         PostgreSQL TagValue
```

### Qué ya no es el camino activo

```
TagObserver → DBManager._tag_queue.put(...) → LoggerWorker.get_tags_from_queue
           → DataLogger.write_tags → TagValue.insert_many
```

Ese diseño (baseline pre-Fénix) aparece aún como cola residual (`TagObserver.__init__(tag_queue)`), pero **`update()` no escribe en `_tag_queue`**. La cola es código muerto para el hot path de histórico.

---

## 2. Capas y responsabilidades (SOLID)

| Capa | Componente | Responsabilidad única |
|---|---|---|
| Adquisición / memoria | `CVT` / `CVTEngine` | Valor actual thread-safe; **no** conoce Postgres |
| Notificación | `Tag.notify` + `TagObserver` | Empuja muestra al gateway SAF |
| Contrato de dato | `PersistableRecord.tag_sample` | JSON canónico: `tag`, `value`, `timestamp`, `sample_uuid` |
| Durabilidad local | `JournalWriter` | WAL SQLite; source of truth hasta ACK remoto |
| Replicación | `RemoteReplicator` + `LoggerWorker` | PENDING → remoto → SENT |
| Mapeo JSON→fila | `TagValuePayloadMapper` | Resuelve FK `Tags`/`Units`; omite value/timestamp inválidos |
| SQL exact-once | `IdempotentBatchInserter` | `INSERT … ON CONFLICT DO NOTHING` |
| Lectura HMI | `DataLogger.read_*` | Consulta Postgres (escala µs en `timestamp`) |

Inversión de dependencias: el CVT **no** importa `psycopg2` ni Peewee para el histórico. Solo `get_persistence_gateway().enqueue(...)`.

---

## 3. Cuándo se adjunta el TagObserver (gate de persistencia)

| Momento | Código | Condición |
|---|---|---|
| Crear / recargar tag | `PyAutomation.create_tag` → `db_manager.attach` | `is_db_connected()` |
| Carga masiva | `load_db_to_cvt` → `create_tag(..., reload=True)` | BD arriba |
| Variables internas de máquina | `state_machine` → `db_manager.attach` | Tras `set_tag` |
| Alarma | `AlarmManager.attach` | Adjunta **otro** `TagObserver` al tag de la alarma |

`DBManager.attach`:

```362:367:automation/managers/db.py
    def attach(self, tag_name:str):
        observer = TagObserver(self._tag_queue)
        self.engine.attach(name=tag_name, observer=observer)
```

**No** comprueba `opcua_address`, `opcua_client_name` ni subscription activa.

### Rol real de OPC UA

| Paso | Archivo | Efecto |
|---|---|---|
| Subscription datachange | `opcua/subscription.py` | `app.cvt.set_value(id=..., value=..., timestamp=...)` |
| Escritura a servidor OPC | `opcua/models.py` `write_value` | Escribe al PLC; **no** es el path del historiador |
| Health reconnect | `LoggerWorker.check_opcua_connection` | Mantiene sesión; no inserta TagValue |

Filtro de planta en la subscription (`MANUFACTURER` / `SEGMENT`): solo decide si el valor **entra al CVT**, no si el observer existe.

---

## 4. Hot path detallado (un TagValue)

### 4.1 Entrada al CVT (thread-safe)

Productores externos deben usar `CVTEngine.set_value` (cola request/response del engine), no mutar el dict interno a ciegas:

```1054:1066:automation/tags/cvt.py
    def set_value(self, id:str, value, timestamp:datetime):
        ...
        _query["action"] = "set_value"
        ...
        return self.__query(_query)
```

Dentro del CVT: deadband opcional → `Tag.set_value` → `notify()`.

### 4.2 Observer → journal

```647:664:automation/tags/tag.py
            result["value"] = self._subject.value.convert(self._subject.get_display_unit())
            ...
            record = PersistableRecord.tag_sample(...)
            get_persistence_gateway().enqueue(record)
```

Payload journal (dominio `tag`, **no** `TagValue`):

```json
{
  "tag": "FI_01",
  "value": 23.5,
  "timestamp": "2026-08-13T14:19:02.123456+00:00",
  "sample_uuid": "…"
}
```

- Tags: `is_critical=False` → ring RAM → flush flusher (~10 ms) → `PENDING` en SQLite.
- Crash antes del flush del ring: única pérdida aceptable documentada en SAF.

### 4.3 Replicación → Postgres

1. `LoggerWorker.run` → `get_persistence_gateway().replicate_once()`.
2. `RemoteReplicator` lee `PENDING`, agrupa por dominio.
3. Dominio `tag` → `batch_insert_with_dedupe` → `TagValuePayloadMapper.to_rows` → `Tags.read_by_name` + unit.
4. `IdempotentBatchInserter.insert_tag_values` → Peewee `insert_many(...).on_conflict_ignore()`.
5. Éxito → `mark_sent`; fallo → filas de ese dominio vuelven a `PENDING` (aislamiento por dominio).

Columnas remotas: `tag_id`, `unit_id`, `value`, `timestamp` (bigint µs, `TimestampField(resolution=6)`), `sample_uuid`.

---

## 5. Alarmas, Eventos y Logs (otro camino, mismo journal)

Estos **no** pasan por `TagObserver`. Usan `journal_then_remote` en los loggers:

| Dominio | Productor | Happy path con BD up |
|---|---|---|
| `event` | `EventsLogger.create` | Journal + write remoto inmediato + `mark_sent` |
| `alarm_summary` / update | `AlarmsLogger` | Igual |
| `log` | `LogsLogger.create` | Igual |

Si el remoto cae tras el journal, quedan `PENDING` y el `LoggerWorker` las reintenta.

Por eso en planta pueden “llegar alarmas/eventos” mientras TagValue fallaba por otro bug (p. ej. `sample_uuid` VARCHAR, o consultas del datalogger en segundos vs columna en µs): **caminos distintos**.

---

## 6. CVTEngine thread-safe vs persistencia

| Mecanismo | Qué protege | Qué no hace |
|---|---|---|
| Cola `__query` de `CVTEngine` / `DataLoggerEngine` / loggers | Serializa acceso al estado / Peewee desde varios hilos | No es Store-and-Forward |
| Journal SAF | Sobrevive caída de red/Postgres y reinicio de proceso | No sustituye la semántica del CVT |

Conclusión: el “mecanismo ThreadSafe” del CVT **sigue activo** para actualizar memoria compartida. La **persistencia** ya no es “el mismo engine escribe TagValue en el hilo del logger drenando `_tag_queue`”; es el **outbox local + replicador**.

---

## 7. Matriz “¿se registra en TagValue?”

| Escenario | Observer adjunto | Valor entra a `set_value` | Resultado esperado |
|---|---|---|---|
| Tag cargado de BD, BD up, **sin** OPC UA, nadie escribe | Sí | No | Sin filas nuevas |
| Tag sin OPC UA + `POST /write_value` | Sí | Sí | Filas en journal → Postgres |
| Tag sin OPC UA + state machine actualiza tag | Sí | Sí | Filas |
| Tag con OPC UA + datachange | Sí | Sí (si SEGMENT/MANUFACTURER ok) | Filas |
| Tag creado **antes** de conectar BD, sin `attach` posterior | No | Sí (CVT cambia) | **No** histórico hasta re-attach |
| BD down | Sí | Sí | Journal `PENDING`; replay al reconectar |
| Deadband bloquea cambio | Sí | Retorno temprano, sin `notify` | Sin nueva muestra |

Esto explica registros “sin mapear OPC UA”: el attach ya ocurrió al cargar/crear el tag con BD conectada; alguna otra fuente está llamando `set_value`.

---

## 8. Puntos de atención operativos (implementación activa)

1. **Doble observer**: `DBManager.attach` + `AlarmManager.attach` pueden poner dos `TagObserver` en el mismo tag → dos enqueues por `notify` (posible duplicado de intento; exact-once remoto mitiga por UNIQUE).
2. **`_tag_queue` residual**: confunde auditorías; no participa en el write path SAF.
3. **Resolución remota por nombre**: si el nombre del payload no existe en `Tags` de Postgres, el mapper omite la fila (`written=0` → dominio queda PENDING).
4. **Lectura HMI**: `DataLogger` debe filtrar en ticks de microsegundos (`_tagvalue_db_ts`); filtrar en unix-segundos deja el API “vacío” aunque la tabla crezca.
5. **Health**: `GET /api/health/saf` — profundidad de cola, lag, drops.

---

## 9. Código de referencia (implementación activa)

| Pieza | Ruta |
|---|---|
| Attach historiador | `automation/managers/db.py` → `attach` |
| Create tag + attach + OPC opcional | `automation/core.py` → `create_tag` |
| CVT thread-safe set | `automation/tags/cvt.py` → `CVTEngine.set_value` |
| Notify / TagObserver | `automation/tags/tag.py` |
| OPC → CVT | `automation/opcua/subscription.py` → `datachange_notification` |
| API write | `automation/modules/tags/resources/tags.py` → `/write_value` |
| Gateway / journal / replicator | `automation/persistence/{orchestrator,journal,replicator,remote,outbox}.py` |
| Worker | `automation/workers/logger.py` |
| Lectura tendencias | `automation/logger/datalogger.py` |

---

## 10. Criterio de aceptación para operadores

> Un TagValue en Postgres implica: (1) tag con `TagObserver` adjunto, (2) al menos un `set_value` que pasó deadband y `notify`, (3) COMMIT en journal dominio `tag`, (4) replicación exitosa con FK de `Tags`/`Units` resuelta por **nombre**.

> Un mapeo OPC UA exitoso implica solo el paso (2) vía subscription. **No es necesario ni suficiente** por sí solo: sin attach no hay histórico; con attach y otra fuente de valor, sí hay histórico sin OPC UA.

---

## 11. Resumen ejecutivo

La implementación activa desacopla tres preocupaciones que el modelo mental antiguo mezclaba:

1. **Adquisición** (OPC UA u otra) → CVT.
2. **Memoria actual** → CVTEngine thread-safe.
3. **Historiador durable** → Store-and-Forward (journal → Postgres).

Por eso “sin mapear al cliente OPC UA se registra”: el sistema ya no usa OPC UA como candado del historiador. Usa el observer adjunto al crear/cargar el tag con BD disponible. En planta (idetectfugas), los productores reales de muchos tags sin OPC son las **state machines** (`LDS`, `PPA`, `NPW`, …) vía `set_value` → CVT → SAF → Postgres. OPC UA es solo uno de varios productores que alimentan el mismo embudo. Detalle: **§0.1**.
