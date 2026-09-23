# Auditoría: servidor OPC UA embebido (`OPCUAServer`) — V2

| Campo | Valor |
|---|---|
| **Documento canónico** | `AUDIT_OPCUA_SERVER.md` |
| **Revisión** | **V2** — SPEC-RE-AUDIT-OPCUA-SERVER (hooks, latencia, HMI, reset, nodos, multi-edge) |
| **Producto** | PyAutomationIO — servidor OPC UA embebido |
| **Alcance** | Implementación detallada en `automation/state_machine.py` (~L2065–2627); hooks en `automation/core.py`; HMI React; coste BD/subscriptions; fidelidad CVT/alarmas; seguridad; madurez |
| **Fecha** | 2026-09-23 (re-auditoría con evidencia de código + microbench en `venv`) |
| **Stack** | `opcua==0.98.13` (`python-opcua` / freeopcua), gevent + `SM-OPCUAServer` |
| **Complementa** | [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md), [AUDIT_ALARMS.md](./AUDIT_ALARMS.md), [AUDIT_TAGS.md](./AUDIT_TAGS.md), [AUDIT_AUTH_AUTHORIZATION.md](./AUDIT_AUTH_AUTHORIZATION.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) |
| **Veredicto** | **C+ / B−** como puente DA de lectura en red controlada. **No apto** como frontera OT nuclear/industrial de clase mundial. V2 confirma gaps de **exposición dinámica incompleta**, **reset stale** (UA-S9), **N+1 BD** (UA-S11) y **subscriptions huérfanas** (UA-S12) |
| **Clasificación** | Auditoría de arquitectura · IIoT / OPC UA Part 3–5 · seguridad OT |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código actual) |
|---|---|
| ¿Qué es el servidor? | SM `OPCUAServer` que publica address space DA casero: carpetas `CVT` / `Alarms` / `Engines` (+ segmentación) |
| ¿Tipo de Variable? | `add_variable` → **BaseDataVariableType** (no `AnalogItemType`) |
| ¿Namespace URI? | `http://examples.freeopcua.github.io` (ejemplo freeopcua) |
| ¿NodeId? | `blake2b(..., digest_size=4).hexdigest()` → `ns=2;s=<8 hex>` |
| ¿Properties por tag? | **27** tras `pop_list` (no ~15; el serialize actual creció) → **28 nodos/tag** (1 Variable + 27 props) |
| ¿`sync_cvt_tags` en run? | Solo la **primera** pasada de `while_running` (`_cvt_resync_done`); luego solo `__update_*` |
| ¿Expose en `create_tag`? | **Sí, síncrono**; excepciones **tragadas** (`try/except` + `@logging_error_handler`) |
| ¿Expose en `create_alarm` / `append_machine`? | **No** — solo bootstrap `__set_alarms` / `__set_engines` |
| ¿Reset limpia `setattr`? | **No** → **UA-S9**: `hasattr(self, var_name)` sobrevive; tags no se re-registran |
| ¿Grado nuclear? | **No** |

### 0.1 Clasificación rápida

| Nivel | Qué entra |
|---|---|
| **Excelente** | Casi vacío en el *servidor*. El cliente OPC→CVT (StatusCode→Quality) es lo más sólido del ecosistema |
| **Bien** | Lifecycle SM; `_opcua_ready` + pending; AccessType persistido; multi-edge `_scope_owns_tag`; bind ocupado sin rebuild |
| **Mejorable** | DataValue Quality/Timestamp; URI/NodeId producto; delta-update; tests integración; env de puerto; **reducción de nodos** |
| **No cumplimos** | Security ≠ None; PKI; AlarmCondition+Ack; HA; certificación; **exposición dinámica de alarmas/engines**; **reset address-space coherente** |

---

## 1. Definición y ciclo de vida (implementación)

### 1.1 Piezas

| Pieza | Ubicación | Rol |
|---|---|---|
| `OPCUAServer` | `automation/state_machine.py` ~L2065 | Address space + poll |
| Singleton | `automation/__init__.py` → `opcua_server` | Arranque con `machines=(opcua_server,)` |
| Puerto | `AUTOMATION_OPCUA_SERVER_PORT` (default `53530`) | Drift documental vs `OPCUA_SERVER_PORT` |
| BD `OPCUAServer` | `dbmodels/opcua_server.py` + `logger/opcua_server.py` | Filas name/namespace/AccessType |
| REST | `modules/opcua/resources/server.py` | `/opcua/server/attrs` |
| HMI | `hmi/src/pages/OpcUaServer.tsx` → `/communications/server` | Lista AccessType (sin poll, sin Socket.IO) |
| Write-back | `opcua/subscription.py` → `SubHandlerServer` | DataChange → CVT |

### 1.2 Estados

```
start ──while_starting──► wait ──► run
  ▲                                 │
  └──────── while_resetting ◄───────┘
```

| Hook | Comportamiento real |
|---|---|
| `while_starting` | Crea `Server` **idempotente** si `self.server is None`; endpoint; URI ejemplo; folders CVT/Alarms/Engines; `start()`; `__set_cvt/alarms/engines` si no `_opcua_space_loaded`; `_opcua_ready=True`; `sync_cvt_tags` + flush pending; `reconcile_runtime_tag_catalog` |
| Bind `EADDRINUSE` | Warning + sleep 1 s; **no** rebuild (anti-starvation hub) |
| `while_running` | Primero: `sync_cvt_tags` + flush una vez (`_cvt_resync_done`); siempre: `__update_tags/alarms/engines` |
| `while_resetting` | `server.stop()`; `server=None`; limpia `_opcua_ready`, `_opcua_endpoint_up`, `_opcua_space_loaded`, `_cvt_resync_done`, `_pending_cvt_expose` — **no** limpia `my_folders` ni atributos `setattr` (**UA-S9**) |

### 1.3 Gate `_opcua_ready`

Tags creados antes del endpoint → `_pending_cvt_expose`. Core reintenta reconcile (~30 intentos). WARNING de reconcile = coordinación de arranque, no pérdida de CVT local.

---

## 2. SPEC V2 — respuestas pendientes

### 2.1 Hook de exposición (crítico)

**Evidencia:** `automation/core.py` `create_tag` ~L897; `expose_cvt_tag_on_opcua_server` ~L904–923; `reconcile_runtime_tag_catalog` ~L926–948; `create_alarm` ~L5648–5827; `Machine.append_machine` ~L84–164.

| Pregunta | Respuesta |
|---|---|
| ¿`create_tag` llama `expose_cvt_tag_on_opcua_server` **síncronamente**? | **Sí.** Tras CVT + historian + (opcional) subscribe cliente OPC, llama `self.expose_cvt_tag_on_opcua_server(tag)` en el mismo hilo, **antes** del `return`. No hay cola asíncrona aparte del pending interno del SM si `_opcua_ready=False`. |
| ¿Qué pasa si lanza excepción? | **Se traga.** (1) `expose_cvt_tag_on_opcua_server` envuelve en `try/except` → `logging.debug(..., exc_info=True)`. (2) El método lleva `@logging_error_handler`, que también absorbe fallos sin propagar al caller. **`create_tag` sigue devolviendo `(tag, message)` con éxito** aunque el nodo OPC no exista. |
| ¿Hook equivalente para `create_alarm`? | **No.** Tras `append_alarm` + persistencia, solo `ensure_tag_historian_catalog` del tag. **Cero** llamada a OPC UA. Alarmas nuevas en runtime **no** aparecen en el address space hasta un restart donde `__set_alarms` corra — y con **UA-S9** ni eso es fiable tras reset. |
| ¿Hook para `append_machine`? | **No.** `Machine.append_machine` registra la SM, persiste BD/local y `create_tag_internal_process_type`. Engines solo se materializan en `__set_engines` en bootstrap (`_opcua_space_loaded`). |

**Implicación:** el path “dinámico” documentado solo cubre **CVT tags**. Alarmas y engines son **snapshot de arranque**.

```
create_tag ──sync──► expose_cvt_tag_on_opcua_server ──try/except──► expose_cvt_tag
                         │                                              │
                         └─ también intenta tag filtrado `.f`           ├─ pending si !ready
                                                                        └─ _register_cvt_tag + push

create_alarm ──► AlarmManager ──► (sin OPC)
append_machine ──► machine_manager ──► (sin OPC engines)
```

---

### 2.2 Medición real de latencia

**Método (2026-09-23, host de desarrollo, `venv`):**

1. **Sim DB:** FakeNode UA + `time.sleep` por cada `__load_saved_access_type` (28 llamadas/tag = 1 Variable + 27 props).
2. **Real UA:** `opcua.Server` en `127.0.0.1:<ephemeral>`, `__load` stub (sin Peewee), midiendo solo coste `add_variable` + `add_property` + AccessLevel bits.
3. **Micro `__load` real:** Peewee mockeado (sin I/O disco/red).

#### A) Exposición total — DB simulada 0.5 ms/query

| N tags | total | mean/tag | p50 | p95 | p99 | loads |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 23.0 ms | 23.0 | 23.0 | 23.0 | 23.0 | 28 |
| 10 | 253.9 ms | 25.4 | 25.4 | 27.8 | 28.2 | 280 |
| 100 | 2854.7 ms | 28.6 | 27.3 | 32.6 | 59.4 | 2800 |

#### B) DB simulada 2.0 ms/query (PG remoto / SQLite contención)

| N tags | total | mean/tag | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|---:|
| 1 | 75.0 ms | 75.0 | 75.0 | 75.0 | 75.0 |
| 10 | 833.7 ms | 83.4 | 84.4 | 85.4 | 85.5 |
| 100 | 8427.6 ms | 84.3 | 84.5 | 87.1 | 118.4 |

#### C) `opcua.Server` real, sin DB

| N tags | total | mean/tag | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|---:|
| 1 | 4.3 ms | 4.3 | 4.3 | 4.3 | 4.3 |
| 10 | 95.6 ms | 9.6 | 3.3 | 38.2 | 60.9 |
| 100 | 505.1 ms | 5.1 | 3.3 | 5.2 | 77.5 |

**Lectura:** el cuello de botella de bootstrap/expose masivo es **N×28 queries BD** (UA-S11), no el stack UA. A ~0.5–2 ms/query, **100 tags = 2.8–8.4 s** bloqueando el hilo de `create_tag` / reconcile. En planta con miles de tags al arranque, esto es **latencia de arranque observable** (HMI/API).

---

### 2.3 Coste de `__load_saved_access_type` (UA-S11 / UA-S12)

**Código:** `state_machine.py` ~L2578–2627.

Por **cada** Variable y **cada** Property:

1. `app.get_opcua_server_record_by_namespace(namespace)` → **1 SELECT**.
2. Si no existe → `create_opcua_server_record` → **1 INSERT** (+ mirror catalog).
3. Si AccessType `Write`/`ReadWrite` → `server.create_subscription(100, handler)` + `subscribe_data_change(node)` **sin** guardar en `handler.subscriptions`.

| Métrica | Valor |
|---|---|
| Queries por tag (Read, primera vez) | **28** (1 var + 27 props): 28 SELECT + 28 INSERT |
| Queries por tag (ya en BD) | **28 SELECT** |
| Microbench `__load` mock (Read/create) | mean **0.41 ms**/llamada (n=50) — *sin* latencia real de BD |
| Microbench Write mock | mean **0.39 ms**; `create_subscription` **sí** se invoca |
| Subscriptions tras **100 tags Write en Variable+props** | **2800** (100×28) — **ninguna** registrada en `SubHandlerServer.subscriptions` |
| Subscriptions si solo Variables en Write (props Read) | **100** huérfanas |
| Default al crear nodo | `access_type="Read"` → **0** subscriptions |

**Contraste:** `core.update_opcua_server_node_access_type` / callbacks Dash **sí** mantienen `handler.subscriptions[namespace]` al cambiar AccessType desde HMI. El path de **bootstrap** `__load_saved_access_type` **no** — **UA-S12**.

---

### 2.4 HMI — polling y cache

| Archivo | Rol |
|---|---|
| `hmi/src/pages/OpcUaServer.tsx` | UI AccessType del **servidor embebido** (`/communications/server`) |
| `hmi/src/services/opcua.ts` → `getOpcUaServerAttributes` | `GET /opcua/server/attrs` |
| `hmi/src/pages/Communications.tsx` | Cliente OPC UA (browse/poll) — **otro** producto |

| Pregunta | Respuesta |
|---|---|
| ¿Intervalo de fetch (página Server)? | **Ninguno periódico.** `useEffect` → `loadAttributes()` al montar y cuando cambia `debouncedNameFilter` (debounce **300 ms**). |
| ¿TTL de caché? | **No.** Estado React local; tras update AccessType se parchea el array en memoria. Sin React Query / SWR / TTL. |
| ¿Socket.IO `on.opcua_server.*`? | **No existe.** `socket.ts` emite/escucha `on.opcua.connected` / `on.opcua.disconnected` (cliente). La página Server **no** se suscribe a eventos de address space. |
| ¿Communications poll? | Sí: **cada 1 s** `getNodeAttributes` del **cliente** seleccionado (`pollingEvery1s`) — no refresca el inventario del servidor embebido. |

**Gap UX:** nodos creados en runtime (tags nuevos) **no** aparecen en la tabla HMI hasta recargar la página manualmente.

---

### 2.5 Bug de reset (UA-S9) — reproducido estructuralmente

**`while_resetting` limpia:**

- `server.stop()` / `server = None`
- `_opcua_ready`, `_opcua_endpoint_up`, `_opcua_space_loaded`, `_cvt_resync_done`
- `_pending_cvt_expose.clear()`

**No limpia:**

- `self.my_folders` (refs a folders del server muerto)
- Ningún `delattr` / rebuild de atributos `setattr(self, var_name, node)`
- `self.objects`, `self.idx` (huérfanos)

**Reproducción lógica (verificada en bench):**

1. `setattr(self, "CVT_Bench.Tag_0001", node)` → `hasattr` True.
2. Simular reset (flags + `server=None`, **sin** borrar attr).
3. `hasattr` sigue **True**.
4. `_register_cvt_tag` hace `if hasattr(self, var_name): return False` → **no crea** nodo en el **nuevo** address space.
5. `_push_cvt_tag_value` llama `set_value` sobre el **node muerto** → fallo silencioso / datos fantasma.

**Secuencia usuario:** crear tag → reset servidor OPC → crear mismo tag (o sync) → **no aparece** (o aparece roto). Tags **nuevos** con otro `var_name` pueden intentar `my_folders[segment].add_variable` sobre folder **stale** → comportamiento indefinido.

**Fix mínimo:** en `while_resetting`, además de flags:

- Borrar o reconstruir `my_folders = {}`
- Eliminar attrs que referencian nodos UA (whitelist de nombres de SM, o dict `_ua_nodes` en lugar de `setattr` en `self`)
- Preferible: `self._ua_nodes: dict[str, Node]` en vez de contaminar el namespace de la SM

---

### 2.6 Reducción de nodos (AnalogItem + lean props)

#### Claves de `Tag.serialize()` y clasificación post-`pop_list`

`pop_list` actual (`_register_cvt_tag`):

`id`, `value`, `timestamp`, `timestamps`, `values`, `name`, `description`, `opcua_address`, `node_namespace`, `out_of_range_detection`, `frozen_data_detection`, `outlier_detection`

| Clave restante | Clasificación | Notas |
|---|---|---|
| `unit` | Estática / **redundante** si AnalogItem EU | |
| `display_unit` | Estática / **redundante** | |
| `data_type` | Estática / **redundante** (tipo UA) | |
| `variable` | Estática — útil | Tipo de proceso |
| `display_name` | Estática — útil (ya en DisplayName attr) | Parcialmente redundante |
| `opcua_client_name` | Estática / **ops only** | No pertenece al modelo de proceso SCADA |
| `scan_time` | Estática | |
| `dead_band` | Estática | |
| `segment` | Estática | También en path de folder |
| `area` | Estática | Multi-edge |
| `owner_node` | Estática | Multi-edge |
| `kp` | Estática / poco útil en DA | |
| `manufacturer` | Estática | |
| `quality` | **Dinámica** — **no se refresca** en `__update_tags` | Solo valor Variable |
| `quality_label` | Dinámica / redundante vs quality | |
| `quality_substatus` | Dinámica | |
| `opc_status_code` | Dinámica | |
| `stale` | Dinámica — no refresca | |
| `stale_timestamp` | Dinámica | |
| `stale_age_ms` | Dinámica | |
| `bad_samples_dropped` | Dinámica / ops | |
| `filter_*` (5) | Estática / **ops** | No DA estándar |
| `unit_source` | Estática | |

**Conteo:**

| Escenario | Nodos/tag |
|---|---:|
| Actual (BaseDataVariable + 27 props) | **28** |
| Propuesta: AnalogItemType (Value + EngineeringUnits + EURange + ValuePrecision) + lean props (~12) | **~16** |
| Reducción | **~12 nodos/tag (−43%)** |
| 1000 tags | −12 000 nodos; −12 000 filas AccessType; −12 000× queries bootstrap |

**Además:** properties dinámicas de calidad son **engañosas** hoy: se crean al alta y **no** se actualizan en el poll — solo el Variable recibe `set_value` (float redondeado a 4 decimales). Mejor: Quality/Timestamp en `DataValue` (UA-S1) y **no** duplicar como Property estancada.

---

### 2.7 Multi-edge

**`_scope_owns_tag`** (`state_machine.py` L49–63 + `node_scope.owns_tag`):

- Scope deshabilitado → `True` (todo se expone).
- Scope inválido / tag `None` → `False`.
- Si multi-edge: exige `owner_node` owned **y** `tag.area == scope.area`.

Usado en: `_register_cvt_tag`, `_push_cvt_tag_value`, `__set_alarms`, `__update_alarms`. **Engines:** `__set_engines` **no** filtra por scope de área del engine (solo tags/alarms).

| Pregunta | Respuesta |
|---|---|
| ¿Filtra correctamente? | **Sí para tags/alarms** cuando el scope está bien configurado. Edge no publica tags ajenos. |
| ¿Dos edges en el mismo PG — se pisan NodeIds? | **En el address space de proceso: no** (cada edge tiene su propio `opcua.Server`). **En la tabla `opcuaserver` compartida: sí hay riesgo.** NodeId = hash del nombre **sin** manufacturer; FQNs distintos (`Site.A.PT` vs `Site.B.PT`) → hashes distintos. **Mismo FQN** en dos edges (misconfiguración) → **mismo** `ns=2;s=<hex>` → filas AccessType en PG se **pisan** por lookup `namespace`. |
| ¿Folder `{segment}` se duplica? | **No en un proceso.** `if segment not in self.my_folders: add_folder`. Tras UA-S9, folders stale pueden coexistir lógicamente con un server nuevo sin recrear limpio. |

---

## 3. Namespaces y address space

### 3.1 Árbol

```
Objects/
├── CVT/ | {segment}/
│   └── <TagName>                 # BaseDataVariable
│       └── 27 properties…
├── Alarms/ | {segment}/Alarms
│   └── <AlarmName>               # Variable (valor 0) + state props
└── Engines/ | {segment}/Engines
    └── <MachineName>             # Variable + keep_list props
```

### 3.2 Namespace / NodeId

| Atributo | Valor | Evaluación |
|---|---|---|
| URI | `http://examples.freeopcua.github.io` | **Mal** — URI de ejemplo |
| Índice | `register_namespace` → ns=2 típico | OK operativo |
| Identificador | blake2b digest_size=**4** (32 bit) | Colisión teórica a escala grande |
| Properties CVT | `blake2b(f"{name}_{key}")` | |
| Properties alarm/engine | `blake2b(f"{name}.{key}")` | Convención **inconsistente** `_` vs `.` |
| BrowseName | CVT: tag name; alarms/engines: a menudo `""` | Mejorable |

---

## 4. Relación CVT ↔ Variables

| Campo CVT | En OPC |
|---|---|
| `value` | Sí — `set_value` (float **round 4**) |
| `quality` / StatusCode | **No** en DataValue; property estática no refresca |
| `timestamp` | **No** Source/ServerTimestamp |
| Write-back | Si AccessType Write/RW → SubHandlerServer por DisplayName |

---

## 5. Alarmas ISA-18.2 ↔ OPC

Runtime ISA serio; exposición = Variable + properties de `alarm.state.serialize()`. **Sin** `AlarmConditionType`, **sin** Method Acknowledge. Updates por poll `__update_alarms`. Altas en caliente **sin hook** (§2.1).

---

## 6. Engines

Bootstrap `__set_engines` + poll `__update_engines`. Sin Methods de comando. Sin expose en `append_machine`.

---

## 7. AccessType

| AccessType | AccessLevel | Sub write-back |
|---|---|---|
| Read | CurrentRead | No |
| Write | CurrentWrite | Sí (bootstrap **sin** registro → UA-S12) |
| ReadWrite | Read+Write | Sí (igual) |

HMI/API `update_opcua_server_node_access_type` **sí** usa `handler.subscriptions`.

---

## 8. Seguridad

Endpoint `0.0.0.0`; **sin** `set_security_policy`; None/Anonymous; sin PKI OPC; certs HTTPS ≠ canal OPC. Mitigación = VLAN. Ver `AUDIT_AUTH_AUTHORIZATION.md`.

---

## 9. Robustez

| Tema | Evaluación |
|---|---|
| Bind ocupado | Bien |
| Reset address space | **Mal — UA-S9** |
| Expose síncrono + N+1 BD | **Mal a escala — UA-S11** |
| Subscriptions bootstrap | **Mal — UA-S12** |
| Update O(n)/s | OK cientos; tensión miles |
| HA / DoS limits | No / defaults |

---

## 10. Inventario de gaps (V2)

### 10.1 Bien

1. Lifecycle + `_opcua_ready` + pending CVT  
2. Carpetas segmentadas  
3. NodeId determinista  
4. AccessType persistido + HMI  
5. `_scope_owns_tag` en tags/alarms  
6. Anti-starvation bind  
7. Write-back con conversión de unidades (path HMI)

### 10.2 Mejorable / bugs confirmados

| ID | Gap | Evidencia |
|---|---|---|
| **UA-S1** | DataValue sin StatusCode/timestamps | `_push_cvt_tag_value` solo `set_value` |
| **UA-S2** | URI ejemplo | `while_starting` |
| **UA-S3** | digest_size=4; `_` vs `.` | `_register_cvt_tag` / alarms |
| **UA-S4** | (histórico) subs write — ver **UA-S12** | |
| **UA-S5** | Full-scan update cada tick | `while_running` |
| **UA-S6** | Stack 0.98.13 legacy | `requirements.txt` |
| **UA-S7** | Tests integración escasos | `test_opcua_server_dynamic_tags.py` |
| **UA-S8** | Env puerto inconsistente | docs vs código |
| **UA-S9** | Reset no limpia `setattr`/`my_folders` | `while_resetting` — **confirmado** |
| **UA-S10** | Sin expose dinámico alarm/engine | `create_alarm` / `append_machine` |
| **UA-S11** | 1 query BD por nodo+property | `__load_saved_access_type` — **28×/tag** |
| **UA-S12** | Subs write no registradas en bootstrap | vs `update_opcua_server_node_access_type` |
| **UA-S13** | HMI Server sin poll ni Socket.IO | `OpcUaServer.tsx` |
| **UA-S14** | 27 props; no AnalogItem; calidad estancada | §2.6 |
| **UA-S15** | Excepciones de expose tragadas | `expose_cvt_tag_on_opcua_server` |

### 10.3 No cumplimos (nuclear / clase mundial)

| ID | Requisito | Estado |
|---|---|---|
| **UA-N1–N3** | Security Policy, PKI, usuarios OPC | Ausente |
| **UA-N4** | Audit sesiones/writes OPC server | Ausente |
| **UA-N5** | AlarmCondition + Ack | Ausente |
| **UA-N6** | Quality→StatusCode fiel | Ausente |
| **UA-N7** | HA | Ausente |
| **UA-N8–N10** | Hardening / certificación / IEC 62443 canal | No |

---

## 11. Roadmap priorizado (V2)

### P0 — Correctitud (días–semanas)

1. **UA-S9** — limpiar nodos/folders en reset (dict `_ua_nodes`).  
2. **UA-S12** — registrar/delete subscriptions en `__load_saved_access_type`.  
3. **UA-S15** — al menos WARNING (no solo debug) si expose falla; métrica.  
4. **UA-S1** — Quality + Timestamp en DataValue.

### P1 — Escala y semántica

5. **UA-S11** — batch prefetch AccessType por namespaces; default Read sin INSERT por property si no hace falta fila.  
6. **UA-S14** — AnalogItem + lean props (−43% nodos).  
7. **UA-S10** — `expose_alarm` / `expose_engine` desde `create_alarm` / `append_machine`.  
8. **UA-S13** — poll o evento Socket.IO para tabla Server.

### P2 — Seguridad de planta

9. **UA-N1–N4**, **UA-S2/S3**, stack (**UA-S6**).

### P3 — Clase mundial

10. AC Part 9, HA, companion specs, certificación.

---

## 12. Archivos clave

| Path | Notas |
|---|---|
| `automation/state_machine.py` `OPCUAServer` | Lifecycle, register, load access, updates |
| `automation/core.py` `create_tag` / `expose_*` / `create_alarm` | Hooks asimétricos |
| `automation/opcua/subscription.py` | `SubHandlerServer.subscriptions` |
| `automation/tags/tag.py` `serialize` | 39 claves → 27 props |
| `automation/node_scope.py` | `owns_tag` |
| `hmi/src/pages/OpcUaServer.tsx` | Fetch on-demand |
| `hmi/src/pages/Communications.tsx` | Poll 1 s **cliente** |
| `automation/tests/test_opcua_server_dynamic_tags.py` | Expose/pending unitario |

**Búsqueda negativa:** cero `AlarmCondition` / `set_security_policy` / application cert en path del servidor embebido.

---

## 13. Resumen ejecutivo

El servidor embebido es un **espejo DA de CVT** con AccessType y multi-edge razonable, pero la re-auditoría V2 demuestra que:

1. La exposición **en caliente** solo existe para tags; alarmas/engines son snapshot de arranque.  
2. Fallos de expose **no fallan** `create_tag` (tragados).  
3. El coste real de alta masiva es **~28 queries BD/tag** (segundos a minutos a escala).  
4. El **reset deja attrs stale** — bug de fidelidad del árbol.  
5. La HMI del servidor **no** se actualiza sola.  
6. Sigue sin seguridad OPC ni Alarms & Conditions.

| Pregunta de negocio | Respuesta |
|---|---|
| ¿Exponer CVT a SCADA hoy? | Sí, con limitaciones |
| ¿Fiel a CVT/alarmas? | Parcial (valor sí; calidad/ack/alarmas dinámicas no) |
| ¿Grado nuclear? | **No** |
| ¿Primero qué? | UA-S9 + UA-S12 + UA-S1 + UA-S11 |

---

*Fin de auditoría `AUDIT_OPCUA_SERVER.md` V2 — 2026-09-23.*
