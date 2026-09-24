# Auditoría: cliente OPC UA de campo (DAQ / DAS) — V2

| Campo | Valor |
|---|---|
| **Documento** | `AUDIT_OPCUA_CLIENT.md` |
| **Revisión** | **V2** — cliente de campo en asyncua (2026-09-23). La V1, debajo, describe el motor anterior |
| **Producto** | PyAutomationIO 2.9.0 |
| **Código** | `automation/opcua/asyncua_client/`, `Client` en `models.py`, `DAS`, `OPCUAClientManager` |
| **Stack** | `asyncua>=2.0.1`. `opcua==0.98.13` ya no está en `requirements.txt` |
| **Hilo** | `opcua-asyncua-client`, distinto de `opcua-asyncua` del servidor embebido |
| **Veredicto** | El contrato del CVT no cambió. La red vive en un loop propio. El Read de 200 nodos y el de dos URL se midieron en esta máquina; no hay factor heredado de otro producto |

## Resultado V2

`Client` ya no hereda de `opcua.Client`. No hay `_io_lock`, ni `ThreadPoolExecutor`, ni `uaclient._uasocket`. DAS encola `Subscribe`. El callback del loop encola el `DataValue`. Un hilo de drenado lo aplica con `DAS.update_tag_value` (en el hub de gevent cuando el monkeypatch está activo). El periodo de la suscripción es `clamp(scan_time, 100, 1000)` ms. El Read del DAQ es `read_attributes`, y `None` sigue significando «en vuelo».

Dos desviaciones respecto al texto de SPEC-OPCUA-CLIENT-ASYNCUA, porque la API real de asyncua 2.0.1 no coincide:

- El estado público es `client.uaclient.state is UaClientState.CONNECTED`. `uaclient.protocol.state == "open"` no existe.
- No se usa `asyncua.sync.Client` como runtime. Su `ThreadLoop` hereda de `threading.Thread` importado al cargar el módulo, y bajo gevent ese hilo no es un hilo de sistema. `sync_adapter.py` espera con un `Event` sobre el `ClientRunner` propio.

Medición local, servidor asyncua en `127.0.0.1`, una serie:

| Bench | Qué se midió | p50 | p95 |
|---|---|---|---|
| `bench_read_batch.py` | 200 nodos, 20 repeticiones | 20.233 ms | 40.557 ms |
| `bench_parallel_plc.py` | 2 URL, 100 nodos cada una, pared del par, 15 repeticiones | 20.155 ms | 40.153 ms |
| `bench_tick_gevent.py` | extra sobre un `sleep` de 10 ms del hub mientras corre un Read | 0.492 ms | 0.870 ms |

El p95 de las dos URL (40.153 ms) queda al lado del p95 de un solo Read de 200 nodos (40.557 ms). En esta serie el segundo PLC no se sumó al primero. No se midió el cliente viejo en la misma corrida, así que no hay un factor de aceleración.

### Sesiones simultáneas y desconexión del operador (2026-09-23)

Varios clientes definidos conviven en el mismo hilo `opcua-asyncua-client`. Cada uno tiene su sesión en `LoopContext.sessions`, con la clave del nombre del cliente. Al arrancar, `load_opcua_clients_from_db` conecta todos los que están en el catálogo. Elegir otro nombre en la lista de la HMI solo cambia el árbol, el polling y el destino de Editar, Conectar, Desconectar y Eliminar. No cierra las demás sesiones.

`POST /api/opcua/clients/disconnect/<nombre>` cierra esa sesión y deja `manual_hold`. El vigilante de `LoggerWorker.check_opcua_connection` no la vuelve a abrir. El endpoint y la URL se conservan. `POST /api/opcua/clients/connect/<nombre>` quita la marca e intenta la sesión otra vez. Eliminar el cliente sigue siendo otra acción: borra la definición.

La lista `GET /api/opcua/clients/` devuelve `is_opened` y `manual_hold` por cliente. El LED junto a la lista usa esas dos marcas:

| Color | Cuándo |
|---|---|
| Rojo | El cliente seleccionado está caído, por desconexión manual o por pérdida de enlace |
| Amarillo | El seleccionado sigue conectado y al menos otro cliente, que no está en espera manual, está caído |
| Verde | El seleccionado está conectado y todos los que deben seguir en línea también lo están. Una espera manual de otro cliente no apaga el verde |

---

## Línea de base V1

La V1 no midió un PLC real. Los tiempos de esa sección son los del código (timeouts, colas, un worker). No se copia el 1.8× de un bench de terceros.

---

## 1. Qué hace el cliente

Hay dos adquisiciones. El corte está en `PyAutomation.subscribe_opcua` (`automation/core.py`, cerca de la línea 3740).

| Camino | Cuándo | Quién lee | Quién escribe el CVT |
|---|---|---|---|
| **DAS** | `scan_time` ausente o `<= 100` ms | Suscripción OPC. El servidor empuja | `DAS.datachange_notification` → `update_tag_value` → `cvt.set_value_fast` |
| **DAQ** | `scan_time` `> 100` ms | Máquina `DAQ-{ms}` hace un Read por ciclo | `DAQ._apply_daq_sample` → `cvt.set_value` |

`DAQ-1000` y `DAQ-500` no leen el catálogo entero. Cada una agrupa solo los tags suscritos a ese `scan_time`, por URL de PLC, y pide un Read (`state_machine.py`, `DAQ.while_running`).

El tag de campo guarda dos coordenadas:

- `opcua_address`: URL `opc.tcp://…` del PLC.
- `node_namespace`: NodeId en texto (`ns=2;s=…`).

`DAS.subscribe` indexa `cvt._cvt._namespace_index[node_id] = tag.id` para que la notificación encuentre el tag sin recorrer el catálogo.

---

## 2. Camino DAS (push)

`DAS` es un singleton (`automation/opcua/subscription.py`).

- Una suscripción por cliente: `get_or_create_subscription` llama `client.create_subscription(period, self)` con **periodo por defecto 1000 ms**. `subscribe_opcua` no pasa otro periodo. Un tag dado de alta con `scan_time` de 100 ms queda en una suscripción de 1 s.
- Cada nodo entra con `subscribe_data_change`. Si el NodeId ya estaba, se hace `unsubscribe` y se crea otro monitored item.
- La primera muestra es un `get_data_value()` síncrono dentro de `subscribe` (`_read_node_data_value`). Si falla, el tag espera la primera notificación.
- `datachange_notification` corre en el hilo de recepción de `opcua`. Ahí se convierten unidades y se llama `set_value_fast`. El docstring de la clase pide no hacer trabajo lento en ese hilo. La conversión y la escritura del CVT están en ese hilo.
- `resubscribe_all` vuelve a suscribir nodo a nodo después de una reconexión.

Calidad y tiempo: `StatusCode` pasa por `map_opc_status`. El timestamp es `SourceTimestamp`. El valor se convierte de la unidad del tag a la unidad de display antes de entrar al CVT.

---

## 3. Camino DAQ (poll)

`Client` (`automation/opcua/models.py`) hereda de `opcua.Client`.

Por cada PLC hay:

- `threading.Lock` (`_io_lock`).
- `ThreadPoolExecutor(max_workers=1)` con nombre `opc-io-{cliente}`.

`read_data_values_bounded` es el Read del ciclo:

1. Si ya hay un future vivo para ese cliente, devuelve `None`. El ciclo DAQ **no** lo trata como lectura vacía y no sube el contador de fallos.
2. Si el future anterior ya terminó, entrega ese resultado. Si la lista de NodeIds cambió, rellena solo los que coinciden y deja el resto en `None` en esa misma llamada, sin lanzar otro Read.
3. Si no hay future, lanza el Read en el único worker y espera como máximo `AUTOMATION_DAQ_READ_TIMEOUT_S` (0.05–5 s, default **0.5 s**).
4. Un `FuturesTimeout` deja el Read corriendo y devuelve `None`. No cancela el socket.
5. Una excepción o un cliente caído devuelve `{namespace: None}` por cada nodo. Eso sí cuenta como miss.

`_read_data_values_unlocked` arma la lista de `NodeId` y llama `uaclient.get_attributes(node_ids, AttributeIds.Value)`. Es **un** servicio Read para todos los nodos de esa URL. Si ese método no está, cae a un `get_data_value` por nodo.

`DAQ._apply_daq_sample` escribe el CVT solo con un `DataValue` presente: `Value.Value`, `SourceTimestamp` (`ensure_utc`) y `StatusCode` (`status_code_to_quality`, y el entero en `opc_code`). El valor pasa por `convert_value` de unidad de campo a unidad de display.

Misses: `AUTOMATION_DAQ_BAD_AFTER_MISSES` (1–20, default **3**). Antes de ese umbral se conserva la última calidad. Al llegar, se reescribe el último valor con calidad BAD. El DAQ no sustituye el tag por su derivado `.f`: `_register_wavelet_tag` fuerza la fuente cruda.

`is_connected` y `is_token_valid` leen `uaclient._uasocket._connection`. Es API privada de `opcua` 0.98.13. No existe en asyncua.

El comentario de `read_data_value_bounded` dice «Serialize asyncua I/O». El código serializa I/O de `opcua`, no de asyncua.

---

## 4. Mapeo y browse

El alta de un cliente y el árbol para el HMI viven en `OPCUAClientManager` (`automation/managers/opcua_client.py`) y en `Client.browse_tree_generic`.

El browse está acotado: profundidad 10 y 50 000 nodos, con un conjunto de NodeIds visitados para no ciclar. Sigue siendo un browse por nodo, no un browse con continuación en una sola llamada. `get_node_attributes` pide, en serie, clase, browse name, data value, display name, tipo, access level, descripción, valor, dimensiones y value rank. Mapear una variable son del orden de diez round-trips. Eso se nota al armar el vínculo en el HMI. No es el ciclo de scan.

`get_node_data_values_by_opcua_address` busca el cliente cuya `server_url` coincide y delega en `read_data_values_bounded`. Si el cliente no está conectado, devuelve el diccionario de `None` (miss), no el `None` de «todavía en vuelo».

---

## 5. Dónde se pierde tiempo

| Hecho | Efecto |
|---|---|
| Un worker por PLC | El Read de `DAQ-500` y el de `DAQ-1000` contra el mismo PLC no se solapan. El segundo recibe `None` mientras el primero no termina, y ese ciclo no muestrea |
| DAS y DAQ comparten `_io_lock` | Una notificación que lee, o un browse del HMI que toma el lock, retrasa el poll |
| La suscripción DAS publica cada 1000 ms | El corte `scan_time <= 100` no cambia el periodo OPC. El tag «rápido» se entera a 1 Hz |
| El callback DAS escribe el CVT en el hilo de red | Conversión de unidades y `set_value_fast` alargan el hilo que tiene que seguir recibiendo Publish |
| El timeout no aborta el Read | Un PLC lento ocupa el único worker más allá de 0.5 s. Los ciclos siguientes siguen viendo «en vuelo» |
| Browse y atributos en serie | El mapeo de un nodo variable es caro. El scan por lote ya no lo es, cuando `get_attributes` existe |
| `opcua` 0.98.13 sigue instalado | El servidor embebido ya no lo instancia. El cliente sí. Mientras el cliente no migre, el paquete vulnerable permanece por este camino |

Lo que ya está bien y no hay que reabrir: un Read por URL y por ciclo DAQ, una suscripción por cliente, el índice por NodeId, el presupuesto de 0.5 s, y la regla de no marcar BAD en un timeout suelto.

---

## 6. Contrato que la migración tiene que conservar

- El tag se encuentra por `node_namespace`, no por el nombre de negocio.
- Se escribe la unidad de display, no la unidad cruda del PLC, salvo que ya coincidan.
- `DataValue` completo: valor, `StatusCode`, `SourceTimestamp`. `read_values` de asyncua tira el status y el timestamp. El Read de campo tiene que usar `Client.read_attributes(..., AttributeIds.Value)`, que devuelve `list[DataValue]`.
- `None` del reader significa «el Read anterior sigue vivo». `{ns: None}` significa miss. Confundirlos marca BAD al primer ciclo lento.
- El umbral `AUTOMATION_DAQ_BAD_AFTER_MISSES` y el timeout `AUTOMATION_DAQ_READ_TIMEOUT_S` siguen siendo la política de planta.
- Una suscripción por `client_name`. Reemplazar un NodeId hace unsubscribe del monitored item anterior.
- El DAQ no adquiere el tag `.f`.
- Un tag de otro `opcua_client_name` o de otro nodo (multi-edge) no se suscribe.
- `subscribe_opcua`, `subscribe_tag` y `get_node_data_values_by_opcua_address` conservan la firma. El HMI y las máquinas no se enteran del cambio de librería.

---

## 7. Cómo pasarlo a asyncua

El servidor embebido ya corre `asyncua.Server` en un hilo de sistema (`gevent.monkey.get_original` para `Thread`, `Event` y `queue.Queue`), porque gevent parchea `threading` y no convive con el loop de asyncio. El cliente tiene que usar el mismo aislamiento y **otro hilo**. Un browse o un Read de un PLC lento en el loop del servidor embebido frenaría la publicación de tags. Dos loops, dos colas.

```text
Hilo gevent (DAQ, HMI, CVT)
    subscribe_opcua / while_running
        │  snapshot: url, NodeIds, periodo
        ▼
    ClientCommandQueue  (maxsize explícito)
        │
Hilo de sistema "opcua-asyncua-client"
    asyncio loop
        asyncua.Client por cada URL
        await read_attributes / create_subscription
        │  DataValue, sin tocar el CVT
        ▼
    cola de resultados hacia gevent
        DAS.update_tag_value / DAQ._apply_daq_sample
```

Invariantes:

1. Ningún `connect`, `read`, `browse` ni `create_subscription` corre en el hilo gevent.
2. Ningún `cvt.set_value` corre en el hilo asyncio. El callback de asyncua solo encola el `DataValue`.
3. La cola de comandos y la de resultados tienen `maxsize`. Si la de resultados se llena, se descarta el más viejo y se cuenta. No se bloquea el Publish.

### Fase 1 — misma firma, I/O todavía síncrono en el borde

`Client` deja de heredar de `opcua.Client`. Un adaptador pequeño habla con `asyncua.sync.Client` y expone `get_node`, `create_subscription`, `read_data_values_bounded` y `is_connected` como hoy. Sirve para comprobar que el NodeId, la calidad y el CVT no se mueven. No quita el worker único ni el lock: el wrapper síncrono bloquea a quien lo llama. No es el objetivo de performance. Es la red de seguridad.

Hay que sustituir, en esta fase, todo uso de `uaclient._uasocket` por el estado de sesión de asyncua (`client.uaclient` / el protocolo de conexión que exponga 2.0.1, sin atributos privados del stack viejo).

### Fase 2 — loop nativo, que es donde está el rendimiento

Comandos: `Connect`, `ReadBatch`, `Subscribe`, `Unsubscribe`, `Browse`, `Write`, `Disconnect`.

- `ReadBatch` lleva la URL y la lista de NodeIds. El loop hace `await client.read_attributes(nodes, ua.AttributeIds.Value)` una vez. El DAQ espera el resultado con el mismo presupuesto de 0.5 s, sobre un `Event` de hilo real, no sobre un future del pool de un solo worker. Dos DAQ contra dos PLC avanzan a la vez. Dos DAQ contra el mismo PLC se serializan en el loop con dos comandos, sin pisarse el future: cada uno tiene su respuesta.
- `Subscribe` crea **una** suscripción por URL. El periodo sale del `scan_time` del grupo, con suelo 100 ms y techo 1000 ms, en lugar del 1000 fijo. Los monitored items se agregan a esa suscripción. El handler asyncua encola `(namespace, DataValue)` y vuelve. El aplicado al CVT lo hace el ciclo gevent que ya drena la cola de resultados, reutilizando `update_tag_value`.
- `Browse` y `get_node_attributes` también van al loop, para que el HMI no tome `_io_lock` del scan. El tope de 10 niveles y 50 000 nodos se queda. Atributos de un nodo variable se leen con un `read_attributes` de varios `AttributeIds`, no con diez llamadas.
- `Write` de un setpoint usa `write_values` solo para el valor. No es el camino del DAQ.

El pool `opc-io-*` y `_daq_inflight` se retiran cuando el loop es la única puerta de red. El significado de `None` (en vuelo) pasa a ser «el comando `ReadBatch` de este ciclo aún no contestó antes del presupuesto».

### Qué no hacer

- No meter `asyncua.Client` en el loop del servidor embebido.
- No usar `read_values` para el DAQ: pierde `StatusCode` y `SourceTimestamp`.
- No escribir el CVT desde `datachange_notification` async.
- No anunciar un factor 1.8×. Esa cifra del spec del servidor compara otro producto con asyncua, no este cliente con `opcua` 0.98.13. El bench de esta migración es: N nodos, una URL, un Read, p95 antes y después, más dos URL en paralelo.

---

## 8. Mapa de API

| Hoy (`opcua` 0.98.13) | asyncua 2.0.1 |
|---|---|
| `opcua.Client.connect` / `disconnect` | `await client.connect()` / `await client.disconnect()` |
| `NodeId.from_string` | `ua.NodeId.from_string` |
| `uaclient.get_attributes(ids, Value)` | `await client.read_attributes(nodes, ua.AttributeIds.Value)` |
| `node.get_data_value()` | `await node.read_data_value()` |
| `create_subscription(1000, handler)` | `await client.create_subscription(period, handler)` |
| `subscription.subscribe_data_change(node)` | `await subscription.subscribe_data_change(node)` |
| `uaclient._uasocket._connection.is_open()` | Estado de la sesión asyncua, sin el socket privado |
| `datatype_to_varianttype` de `opcua.ua.uatypes` | El equivalente en `asyncua.ua`, o el nombre de tipo que ya devuelve `read_data_type` |

`Client` de `automation/opcua/models.py` tiene del orden de 1 300 líneas y mezcla sesión, browse, DAQ y serialización. El adaptador nuevo no tiene por qué mudarla entera en el primer corte: sesión y Read/Subscribe primero; browse después, detrás de la misma cola.

---

## 9. Riesgos

| Riesgo | Qué lo contiene |
|---|---|
| El callback asyncua y el CVT se pisan | La escritura del CVT queda en gevent. El loop solo encola |
| Un PLC lento bloquea al otro | Sesiones distintas en el mismo loop; ningún `Lock` global de I/O |
| El primer ciclo marca BAD | Se conserva `None` = en vuelo, distinto de `{ns: None}` |
| El wrapper síncrono se queda como solución final | La fase 1 no cierra el objetivo. El bench de la fase 2 es la puerta |
| `is_connected` privado rompe al cambiar la clase base | Se reemplaza en la fase 1, con un test que no abre socket |
| Geven convierte el hilo en greenlet | `get_original`, igual que el servidor |
| Se borra `opcua` de `requirements.txt` antes de tiempo | Se quita solo cuando `automation/opcua/` y `managers/opcua_client.py` ya no lo importan |

---

## 10. Criterios para la implementación que siga

| ID | Criterio |
|---|---|
| CA-DAQ-01 | `automation/opcua/` y el manager no importan `opcua` |
| CA-DAQ-02 | Un Read de N nodos de una URL es una llamada `read_attributes` |
| CA-DAQ-03 | El `DataValue` que llega a `_apply_daq_sample` trae valor, `StatusCode` y `SourceTimestamp` |
| CA-DAQ-04 | Timeout de 0.5 s devuelve en vuelo (`None`), no un mapa de misses |
| CA-DAQ-05 | Tres misses seguidos dejan el último valor en BAD. Uno solo, no |
| CA-DAQ-06 | Una suscripción por cliente. El periodo es el `scan_time` del grupo, entre 100 y 1000 ms |
| CA-DAQ-07 | Dos URL se leen en el mismo ciclo sin compartir un worker de `max_workers=1` |
| CA-DAQ-08 | El CVT no se escribe en el hilo del loop |
| CA-DAQ-09 | El loop del cliente no es el loop del servidor embebido |
| CA-DAQ-10 | Bench propio: p95 de un Read de N nodos, y p95 de dos URL en paralelo, escrito en la revisión V2 de este documento |

Fuera de este cliente: Security Policy activa en planta, AlarmCondition, histórico, PubSub, y volver a medir el arranque del servidor embebido.

---

*Fin de auditoría `AUDIT_OPCUA_CLIENT.md` V2 — 2026-09-23. La línea de base V1 queda en las secciones 1 a 10.*
