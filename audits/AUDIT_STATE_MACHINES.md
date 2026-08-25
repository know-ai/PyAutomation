# Auditoría: máquinas de estado, ciclo, buffers y relación con CVT / adquisición

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/state_machine.py`, `automation/workers/state_machine.py`, `automation/opcua/subscription.py`, `automation/tags/`) |
| **Alcance** | Ciclo de vida de una SM; `machine_interval`; buffers de variables suscritas; relación con CVT, DAS, DAQ y OPC UA; versatilidad de periodos por capa |
| **Fecha** | 2026-08-18 — evidencia de código; **re-auditoría post spec 02** (desacoplamiento temporal) |
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), `specs/02-STATE-MACHINE-TEMPORAL-DECOUPLING.md` |
| **Consumidor de referencia** | iDetectFugas — **dual-path**: legado si `sample_interval IS NULL`; migrado lee `self.data` (`app/sampling.py`) |
| **Veredicto** | **A−** con tres relojes. SM-H1 **cerrado** si `sample_interval` está definido (`SampleSchedThread` → `_push_to_buffer`). Modo legado = comportamiento pre-spec. Regla de oro `execution ≥ sample ≥ scan` rechazada en API (400) |
| **Clasificación** | Auditoría de arquitectura · runtime de control |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-18, spec 02) |
|---|---|
| ¿Cada cuánto corre un ciclo de **ejecución**? | Cada `execution_interval` / `machine_interval` **segundos** (default **1.0**, mínimo **0.01** salvo DAQ). Compensa `loop()`: duerme `interval − elapsed` |
| ¿Cada cuánto se **muestrea** el buffer? | Si `sample_interval` no es NULL: `SampleSchedThread` (hilo OS propio) llama `_sample_once` cada `sample_interval` s, con override por tag. Si es NULL: **legado** — no hay sampler; iDetectFugas sigue muestreando en el tick de ejecución |
| ¿Cómo se configura? | `PUT /machines/<name>/attributes` (`execution_interval` / `interval`, `sample_interval`, `sample_overrides`). HMI detalle: checkbox «Personalizar muestreo». Persistencia: `machines.execution_interval`, `machines.sample_interval`, `tags_machines.sample_override` |
| ¿El buffer de tags suscritos se llena con el dato de campo? | CVT = last-wins a ritmo de adquisición. **Modo desacoplado:** `_push_to_buffer` copia `ProcessType.value` al anillo `IBufferProvider` (`self.data`) a ritmo de muestreo. **Legado:** `self.data` sigue sin llenarse; las apps usan su `self.buffer` |
| OPC UA 200 ms, sample 0.2 s, ejecución 1.0 s | DAQ-200 escribe CVT ~5 Hz. Sampler toma 1 muestra / 0.2 s (5 por ventana de ejecución). `while_running` corre a 1 Hz **leyendo** el buffer, sin llenarlo (cláusula nuclear) |
| ¿Se puede llenar el buffer a otra frecuencia que el ciclo? | **Sí**, activando `sample_interval` con `execution_interval >= sample_interval >= scan_time` |
| ¿El ciclo puede ser más rápido que el muestreo o el campo? | **No vía API.** `MachineConfigError` → HTTP **400** con el mensaje de la regla violada |
| ¿Tiempos distintos por capa? | Adquisición (`scan_time` ms) / muestreo (`sample_interval` s, override por tag) / ejecución (`execution_interval` s) / historiador (evento CVT) |

### 0.1 Contrato spec 02 (implementado)

| Reloj | Pieza | Aislamiento |
|---|---|---|
| Adquisición | DAS / DAQ → CVT | Sin cambios |
| Muestreo | `SampleSchedThread` + `IBufferProvider._push_to_buffer` | **Hilo OS** (no greenlet del hub): un `while_*` bloqueante no detiene el llenado |
| Ejecución | `SchedThread` / `run_machine_cycle` → `loop()` | No llama `_push_to_buffer`. En legado inyecta `_legacy_sample_and_execute()` (no-op de fábrica) |

Validación: `validate_temporal_config` en `automation/state_machine_timing.py`. Métricas en `/api/health/system`: `SAMPLE_LAG_MS`, `EXECUTION_CYCLE_US`, `BUFFER_UTILIZATION_%`.

Migración: `ensure_schema` añade columnas y hace `execution_interval = interval` donde era NULL. Rollback: `sample_interval = NULL`.

Tests: `automation/tests/test_state_machine_timing.py` (CA-SM-01, 02, 04, latencia N=100). Soak 24 h CA-SM-05 en planta.

---

## 1. Qué es una máquina en PyAutomationIO

PyAutomation no es un PLC: las aplicaciones (LDS, mezcladores, DAQ, servidor OPC UA embebido) son **máquinas de estados** sobre `python-statemachine`, registradas en el singleton `Machine` y ejecutadas por `StateMachineWorker`.

```
Aplicación (LDS, NPW, Mixer, …)
        │  AutomationStateMachine / StateMachineCore
        ▼
Machine (singleton)  →  StateMachineManager  →  StateMachineWorker
                                                ├─ async: un SchedThread por máquina
                                                └─ sync: un heap cooperativo compartido
```

| Pieza | Rol |
|---|---|
| `StateMachineCore` | Estados `start → wait → run` (+ `restart` / `reset`). Buffers, suscripción a tags, `notify`, `loop` |
| `AutomationStateMachine` | Añade `test` y `sleep` |
| `DAQ` | SM de **sondeo** OPC UA; un ejemplar por `(área, scan_time)` (`Linea1.DAQ-1000`, `Linea2.DAQ-200`, …). Sin área: legado `DAQ-1000` |
| `OPCUAServer` | SM que publica CVT/alarmas/engines al address space |
| `ProcessType` | Variable de proceso. `read_only=True` + `tag` = **entrada** de campo. `read_only=False` = **salida** que escribe CVT (`create_tag_internal_process_type`) |

El ciclo de vida operativo (no el DSL de transiciones) es:

1. **Define** clase con estados / `while_<estado>` / transiciones.
2. **Declara** `ProcessType` de entrada (huecos sin tag) y de salida.
3. **`append_machine(machine, interval, mode)`** — default `mode="async"`, `interval=1.0` s.
4. **`machine.start()`** (lo llama `PyAutomation` al boot) → `StateMachineWorker`.
5. **`subscribe_to(tag)`** (HMI/API o hidratación) → `MachineObserver` en el tag del CVT + `restart_buffer()`.
6. Scheduler: `stamp_machine_cycle` → `machine.loop()` → `while_<estado_actual>`.
7. **`join` / `drop` / `stop`** para alta/baja en caliente (DAQ al crear un tag con `scan_time` > 100 ms).

---

## 2. Gestión del tiempo de ciclo

### 2.1 Unidad y default

| Parámetro | Unidad | Default | Dónde vive |
|---|---|---|---|
| `machine_interval` | **segundos** (float) | `1.0` | `StateMachineCore.__init__(interval=1.0)` |
| `Tag.scan_time` | **milisegundos** (int) | `None` | Tag / BD / API |
| Publicación DAS OPC UA | ms | **1000** | `DAS.get_or_create_subscription(..., period=1000)` |

No mezclar: `interval=0.2` en la SM es 200 **ms** de ciclo; `scan_time=200` en el tag es 200 **ms** de adquisición.

### 2.2 Scheduler (contrato de periodo)

Cada máquina async tiene su propio `SchedThread` + `MachineScheduler`:

```
loop:
    stamp_machine_cycle(machine)          # 1 instante UTC ms → machine.cycle_timestamp
    machine.loop()                        # while_<state>
    scheduler.call_later(get_interval(), loop)
```

Cuando el heap entrega la siguiente tarea, `sleep_elapsed` hace:

```
elapsed = now - last
sleep(interval - elapsed)   # si elapsed > interval → warning, no sleep
```

Efecto: **periodo ≈ `machine_interval`**, no “intervalo después de terminar” puro ni “intervalo desde el start del tick” puro: resta el trabajo del ciclo. Un `while_running` de 300 ms con `interval=1.0` duerme ~700 ms.

Si el trabajo **supera** el intervalo, el siguiente tick arranca enseguida y aparece:

`State Machine: {name} NOT executed on time - Execution Interval: … - Elapsed: …`

No hay skip de ciclo ni cola de ticks atrasados: se **atrasa** y se pierde isocronía.

`run_machine_cycle` envuelve `loop()` en `ephemeral_historian` si la BD está viva. Un `OperationalError` de Peewee **se traga**: el scheduler **sigue**. Outage de historiador no debe matar LDS/DAQ.

### 2.3 Sync vs async

| Modo | Comportamiento |
|---|---|
| **`async`** (default) | Un hilo `SM-<nombre>` por máquina. Periodos **independientes**. DAQ siempre se registra así |
| **`sync`** | Varias máquinas en **un** heap y **un** `last` compartido. `sleep_elapsed` usa el intervalo de la **próxima** máquina del heap. No es un reloj isócrono por máquina; no usar sync si los intervalos difieren |

`Machine.join()` solo engancha al **async** scheduler. Una SM `sync` añadida en caliente no entra por `join`.

Cambio de intervalo en runtime (`set_interval` / API): se lee `get_interval()` **después** de cada ciclo. El tick en curso no se recorta; el siguiente delay ya usa el valor nuevo. No hace falta reiniciar el worker.

### 2.4 Sello de ciclo (relación con el historiador)

Antes de `loop()`, `stamp_machine_cycle` pone `machine.cycle_timestamp` (UTC, milisegundo). Todo `ProcessType.set_value` **de salida** en ese tick comparte ese instante salvo timestamp explícito. UNIQUE `(tag_id, timestamp)` colapsa reescrituras del mismo tag en el mismo ciclo. Eso **no** es el timestamp de campo (`data_timestamp` / `SourceTimestamp` OPC). Detalle: [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md).

---

## 3. Tres “buffers” que no son el mismo objeto

Confundirlos es el origen de la pregunta “¿cada cuánto se llena el buffer?”.

| Capa | Objeto | Quién escribe | Cadencia | Tamaño |
|---|---|---|---|---|
| **A. CVT — valor actual** | `Tag.value` + `Tag.timestamp` | DAS `datachange` o DAQ `while_running` → `cvt.set_value` | Adquisición ∩ deadband | 1 muestra (last-wins) |
| **A'. CVT — anillo del tag** | `Tag.values` / `Tag.timestamps` | `Tag.set_value` | Igual que A | `Buffer()` default **10** |
| **B. DAS / tendencias HMI** | `DAS.buffer[tag]{values,timestamp}` | Mismo hot path de campo **y** escrituras internas de SM | Adquisición (y a veces deadband inconsistente, SM-H3) | `ceil(10 / ceil(scan_time/1000))` al crear tag; `restart_buffer` usa **600 s** equivalentes — **fórmulas distintas** |
| **C. Framework SM** | `StateMachineCore.data` via `IBufferProvider` | `SampleSchedThread._push_to_buffer` si `sample_interval` definido; **nadie** en legado | `sample_interval` (desacoplado) o nulo (legado) | `max(buffer_size, 2×ceil(exec/sample))` acotado a 10 000 |
| **D. App (LDS/NPW/…)** | `self.buffer[...]` propio | `verify_inputs()` en el ciclo | **`machine_interval`** | `buffer_size` de la máquina / YAML |

`ProcessType` de entrada **no es un buffer**: es el último valor notificado. La ventana temporal para un algoritmo hay que construirla en C (roto) o en D (lo que hace iDetectFugas).

### 3.1 Cómo *debería* llenarse C (diseño documentado vs código)

`docs/Developments_Guide/core/state_machines.md` y `while_waiting` del core dicen:

1. Suscribir tags → `restart_buffer()` crea un `Buffer` por tag de entrada.
2. Cada cambio de CVT alimenta esos buffers.
3. Cuando **todos** tienen `len == size`, `wait → run`.

`notify()` hoy:

```
process_type.value = value          # last-wins
self.data_timestamp = timestamp
# no hay self.data[tag](value)
```

Consecuencia:

- Si hay tags suscritos, `self.data` existe y está **vacío** → `while_waiting` del core **nunca** hace `wait_to_run`.
- Si no hay tags, `self.data == {}` (falsy) → **tampoco** hace `wait_to_run`.

DAQ y `OPCUAServer` **saltan** ese contrato (`while_waiting` → `wait_to_run` inmediato). Las apps de planta **reimplementan** la espera sobre su buffer D.

**SM-H1 — Cerrado (modo desacoplado) / residual legado:** con `sample_interval` el SampleScheduler alimenta `self.data`. En legado (`NULL`) el anillo del core sigue vacío a propósito para no romper LDS/NPW (`self.buffer` de app). `buffer_size` dimensiona el anillo del provider (y sigue gobernando la ventana YAML de iDetectFugas).

---

## 4. Capas de muestreo — versatilidad actual

```
Campo / PLC
    │  scan_time del tag (ms)
    ├─ ≤ 100 ms o None  →  DAS (suscripción OPC UA, datachange)
    └─ > 100 ms         →  {area}.DAQ-<scan_time>  (poll; un poller por línea y ms)
            │
            ▼
         CVT  (1 Hz…N Hz según scan_time y deadband)
            │  MachineObserver (evento, no periódica)
            ▼
     ProcessType.value   ← last-wins, ritmo de campo
            │
            │  (app) verify_inputs una vez por machine_interval
            ▼
     Ventana algorítmica (buffer D)   ← ritmo de SM
            │
            ▼
     while_running / diagnósticos / ProcessType de salida → CVT otra vez
            │
            ▼
     SAF / historiador   ← ritmo de cada set_value que pasó deadband
                           (campo) o cycle_timestamp (salidas de SM)
```

### 4.1 Capa 1 — Adquisición de planta (`scan_time`)

**Por tag**, no por máquina. Tags con el **mismo** `scan_time` (> 100) **comparten** una SM `DAQ-{ms}`: un solo hilo lee todos esos nodos cada `scan_time` ms.

Umbral duro en `subscribe_opcua`:

| `scan_time` | Camino | Cadencia real |
|---|---|---|
| `None` o `≤ 100` | **DAS** `subscribe_data_change` | Evento del servidor OPC UA. La suscripción python-opcua se crea con **publishing interval 1000 ms** (`period=1000`), **no** con el `scan_time` del tag. El 100 ms es solo el *switch* DAS vs DAQ |
| `> 100` (p. ej. **200**) | **DAQ** poll `get_node_value_by_opcua_address` | Un ciclo DAQ cada 0,200 s. Lectura síncrona, no monitored item |

HMI Dash histórica limita el input de scan a **min 500 ms / step 500**. La API REST **no** impone ese mínimo: 200 ms es legal por API/BD.

DAQ respeta `node_scope` (multi-edge): no escribe tags de otra área.

### 4.2 Capa 2 — CVT

Memoria de proceso. Una escritura = valor actual + notify de observers (SM, alarmas, `TagObserver` → SAF, `on.tag` SocketIO).

Deadband en `Tag.set_value` **corta** el ingest wavelet y los observers. El `ProcessType` de la SM se queda en el último valor que pasó la banda. Ver [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md).

El filtrado wavelet actúa **off-thread** en tag `.f`; la SM suscrita consume el valor filtrado, no el raw del hot path.

### 4.3 Capa 3 — Ciclo de máquina (`machine_interval`)

**Por ejemplar de SM**, independiente del `scan_time` de sus tags.

Puede ser:

- **Mayor** que el campo (típico: campo 200 ms, LDS 1 s) → decimación implícita last-wins.
- **Igual** → una muestra de ventana por muestra de campo (salvo deadband / jitter).
- **Menor** → oversampling del último valor.

No hay clamp del tipo “interval ≥ scan_time”. El framework **no avisa**.

### 4.4 Capa 4 — Historiador

No es un muestreo configurable de la SM. Cada `set_value` de campo que pasa deadband encola SAF. Las salidas de máquina (`leak`, `leak_flow`, …) se estampan con `cycle_timestamp`. **Historiador ≠ periodo de máquina ≠ scan_time.** Ya auditado en SAF / persistencia.

### 4.5 ¿Se puede pedir “llenar buffer ≥ campo y ciclo ≥ buffer”?

| Deseado | ¿Hoy? |
|---|---|
| Campo 200 ms, SM 1 s, ventana con **todas** las muestras de 200 ms | **No.** Haría falta que `notify()` (o un sampler) empujara C/D a ritmo de campo **sin** ejecutar `while_running` a 200 ms |
| Campo 200 ms, SM 200 ms, ventana de N ciclos | **Sí:** `scan_time=200` y `machine_interval=0.2`. Coste: 5× CPU de `while_*` |
| Campo 200 ms, SM 50 ms | **Sí técnicamente**; la ventana se llena de repetidos. Inútil salvo lógica combinacional |
| Tags a 200 ms y 1000 ms en la **misma** SM | **Sí.** El CVT mezcla ritmos. La SM, al muestrear last-wins una vez por ciclo, ve un collage. La ventana D no interpola |
| DAS (≤100 ms) + SM lenta | El valor llega por **evento**, no por el intervalo de la SM. Sigue siendo last-wins al tick de la máquina |

**SM-C1 — Diseño vigente:** tres relojes. `sample_interval` es el fill-interval del buffer del core. En legado el fill sigue siendo el ciclo de ejecución (apps).

---

## 5. Ejemplo numérico — OPC UA 200 ms, SM 1 s, `buffer_size=40`

1. Tag con `scan_time=200` en Linea1 → se crea/reutiliza `Linea1.DAQ-200` (`DAQ-200` en modo monolítico).
2. Cada 200 ms DAQ lee el nodo, `cvt.set_value` → `MachineObserver` → `notify` → `inlet_flow.value` = último caudal.
3. LDS (ejemplo) con `machine_interval=1.0` y `buffer_size=40`:
   - cada 1 s `verify_inputs()` hace `self.buffer['inlet_mass_flow'](valor_actual)`;
   - hace falta **40 s** de `wait` para llenar la ventana (40 muestras × 1 s), no 8 s (40 × 200 ms);
   - en esos 40 s el campo produjo ~200 muestras; la ventana guarda **40**.
4. En `run`, el mismo patrón: **1 Hz** de algoritmo sobre un anillo de 40 s de tiempo de máquina.

Si se bajara LDS a `interval=0.2` con el mismo `buffer_size=40`, la ventana cubriría **8 s** de planta y el CPU de LDS subiría 5×.

---

## 6. Suscripción, CVT y adquisición — flujo de un tag de campo

```
create_tag(..., opcua_address, node_namespace, scan_time)
    → CVT
    → subscribe_opcua
         DAS o DAQ.subscribe_to(tag)
    → db_manager.attach  (TagObserver → SAF)
    → das.buffer[name] dimensionado

machine.subscribe_to(tag, default_tag_name=?)
    → ProcessType.tag = tag
    → attach MachineObserver
    → restart_buffer()     # core C, vacío
    → machines_engine.bind_tag   # IntegrityError/FK missing: log + continue (CA-ISOLATION-04)
```

Unsubscribe: `tag.detach_machine(self)` **antes** de limpiar `ProcessType.tag` (evita notify a SM fantasma). Si un DAQ se queda sin tags, el manager lo **elimina** del registro.

Salidas de máquina: `create_tag_internal_process_type` crea ` {machine}.{variable} ` en CVT, las engancha al logger y al historiador. `ProcessType.set_value(..., machine=self)` escribe CVT con `cycle_timestamp` y, si el tag está en `das.buffer`, también el anillo HMI.

---

## 7. Ciclo de vida — features que hay que conocer

### 7.1 Estados core y transiciones

`starting → waiting → running`; desde `run`/`wait` se puede ir a `restart` (limpia buffers y vuelve a `wait`) o `reset` (vuelve a `start`). `AutomationStateMachine` añade `test` / `sleep`. Transición manual: `transition(to=...)` / `send(...)`. SocketIO `on.machine` en cada `on_enter_*`.

`criticity` cambia con las transiciones (run=1, restart/reset=5, …) — usado por UI/alarmística de la propia máquina, no es ISA-18.2 del tag.

### 7.2 Arranque y persistencia

`Machine.start()`: si el historiador está vivo, `load_db_machines_config()` pisa `interval`, `buffer_size`, `buffer_roll_type`, `on_delay`, `threshold`, `identifier` sobre el ejemplar Python **antes** de `append_machine`. Flags `_on_delay_from_db` / `_threshold_from_db` evitan que un default de YAML pise planta.

DAQ se nombra `DAQ-{interval_ms}` en `append_machine` (el `name` del constructor se reescribe).

### 7.3 Observadores y fugas

`MachineObserver` suelta la SM en `release()`. Unsubscribe / `delete_tag` deben `detach`. Ciclo de vida de observers: [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md).

### 7.4 Multi-edge

DAQ y DAS no escriben tags que el `node_scope` no posee. `notify` no re-chequea scope: si el observer quedó enganchado a un tag ajeno, el valor llegaría. El prune de boot desuscribe. Ver [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md).

### 7.5 Contrato de `while_*`

Deben ser **cortos**. `time.sleep` dentro del handler **rompe** el periodo (el scheduler ya duerme). Trabajo pesado (wavelet, FiPy) contiende el GIL con gevent: [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md).

### 7.6 IAD / filtros

Decoradores IAD en `CVT.set_value` siguen **comentados**. Una SM **no** debe asumir datos pre-acondicionados en el tag source; para filtrado wavelet debe suscribirse al tag `.f` (`filter_enabled`). Solo deadband aplica al raw en hot path.

### 7.7 API de atributos

`PUT .../attributes`: `threshold`, `interval`, `buffer_size`, `on_delay` (+ modo de umbral PPA/NPW). `buffer_size` persiste YAML **antes** de reiniciar. `interval` se escribe en BD como `IntegerType(int(interval_value))` — **trunca** subsegundos al persistir (0.2 s → 0). **SM-H2.**

### 7.8 Roll del buffer

`forward` = newest at index 0; `backward` = append (default de SM). `Buffer` exige `size > 1` internamente (`maxlen = max(size, 2)`). La API acepta `buffer_size > 0`: un `1` pasa REST y choca con el anillo.

---

## 8. Hallazgos

| ID | Severidad | Hecho | Impacto | Mitigación actual / residual |
|---|---|---|---|---|
| **SM-H1** | Cerrada (opt-in) | Sampler escribe `self.data` si `sample_interval` está set | `wait→run` del core funciona en modo desacoplado | Residual: legado = iDetectFugas `self.buffer` |
| **SM-H2** | Media | Persistencia de `interval` vía API usa `int(seconds)` | `0.2` s se guarda como `0` en BD; al reboot el config loader puede romper el periodo | No usar subsegundo si se depende de BD, o persistir float |
| **SM-H3** | Baja | DAS actualiza su anillo si `set_value` retorna no-`None`; el deadband de CVT **retorna el valor** sin notificar SM | Tendencia HMI puede avanzar y la SM no | Correlacionar `on.tag` vs `ProcessType` |
| **SM-H4** | Media (ops) | DAS publishing interval fijo **1000 ms**; el umbral 100 ms no es el periodo de muestreo OPC | Quien pone `scan_time=50` cree 20 Hz; el cliente pide publish 1 Hz | Para 200 ms usar **DAQ** (`scan_time>100`), no DAS |
| **SM-H5** | Baja | Dos fórmulas de tamaño de `das.buffer` (10 s vs 600 s; `ceil(scan_time/1000)` trata 200 ms como 1 s) | Anillo HMI de tags sub-segundo queda corto (~10 muestras) | No fiarse de DAS buffer como historiador |
| **SM-C1** | Info / diseño | Tres relojes; fill-interval = `sample_interval` (opt-in) | Legado decima last-wins al tick de ejecución | Activar muestreo personalizado |
| **SM-C2** | Info | Scheduler no encola ticks perdidos | Bajo sobrecarga se pierde isocronía, no se “alcanza” | Acortar `while_*` o subir `interval` |

---

## 9. Inventario de código

| Pieza | Archivo |
|---|---|
| Estados, `notify`, `subscribe_to`, `loop`, DAQ, OPCUAServer | `automation/state_machine.py` |
| Scheduler, `stamp_machine_cycle`, sync/async | `automation/workers/state_machine.py` |
| Registro, drop DAQ vacío | `automation/managers/state_machine.py` |
| DAS / datachange | `automation/opcua/subscription.py` |
| Switch DAS/DAQ, `subscribe_tag` | `automation/core.py` (`subscribe_opcua`, `subscribe_tag`) |
| `ProcessType.set_value` → CVT | `automation/models.py` |
| `MachineObserver` | `automation/tags/tag.py` |
| Anillo genérico | `automation/buffer.py` |
| Validador + IBufferProvider + métricas | `automation/state_machine_timing.py` |
| SampleScheduler (hilo OS) | `automation/workers/state_machine.py` (`SampleSchedThread`) |
| Schema `execution_interval` / `sample_interval` / `sample_override` | `automation/dbmodels/machines.py`, `managers/db.py` `ensure_schema` |
| API atributos SM | `automation/modules/machines/resources/machines.py` |
| HMI detalle (muestreo / ejecución) | `hmi/src/pages/MachinesDetailed.tsx` |
| Spec | `specs/02-STATE-MACHINE-TEMPORAL-DECOUPLING.md` |
| Tests CA-SM | `automation/tests/test_state_machine_timing.py` |
| Guía (desactualizada en el punto del buffer C) | `docs/Developments_Guide/core/state_machines.md` |
| Patrón app de ventana real | `gitlab/intelcon/idetectfugas/app/modules/{lds,npw,...}/__init__.py` `verify_inputs` |

---

## 10. Criterios de aceptación (spec 02)

- **CA-SM-01:** `sample_interval=0.2` + `execution_interval=1.0` → 5 puntos por ventana (`samples_per_execution`).
- **CA-SM-02:** tag `scan_time=500` ms → API/validador rechaza `sample_interval=0.2` (400 / `MachineConfigError`).
- **CA-SM-03:** columnas persistidas + backfill `execution_interval = interval`; SIGKILL no pierde la config.
- **CA-SM-04:** `sample_interval IS NULL` → no se lanza `SampleSchedThread`; `_legacy_sample_and_execute` es no-op.
- **CA-SM-05:** muestreo de 100 tags en &lt; 1 ms (unitaria); soak 24 h CPU &lt; 0.5 % a 1 kHz = planta.

Vanilla SM nueva: activar `sample_interval` y tratar `buffer_size × sample_interval` como horizonte de campo. iDetectFugas: dual-path en `app/sampling.py` + `LeakStateMachine` (legado si `sample_interval IS NULL`; migrado lee `self.data`).

---

## 11. Conclusión

Hay **tres relojes** cuando el operador activa muestreo personalizado: `scan_time` (campo), `sample_interval` (llenado del buffer del core, hilo aislado) y `execution_interval` (lógica). La API rechaza cualquier violación de `ejecución ≥ muestreo ≥ adquisición`.

iDetectFugas ya tiene **dual-path**: `sample_interval` nulo = legado (`self.buffer` de app); con muestreo personalizado los motores leen `self.data` y no empujan al provider. Detalle: `gitlab/intelcon/idetectfugas/audits/AUDIT_CORE_SAMPLING.md`. Una SM nueva debe setear `sample_interval` y no bloquear `while_*`.
