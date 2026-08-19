# Auditoría: máquinas de estado, ciclo, buffers y relación con CVT / adquisición

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/state_machine.py`, `automation/workers/state_machine.py`, `automation/opcua/subscription.py`, `automation/tags/`) |
| **Alcance** | Ciclo de vida de una SM; `machine_interval`; buffers de variables suscritas; relación con CVT, DAS, DAQ y OPC UA; versatilidad de periodos por capa |
| **Fecha** | 2026-08-18 — evidencia de código |
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) (ciclo atómico / historiador), [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md) (deadband / Kalman), [AUDIT_MULTI_EDGE.md](./AUDIT_MULTI_EDGE.md) (scope en DAQ/DAS), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) (observers, GIL) |
| **Consumidor de referencia** | iDetectFugas (`gitlab/intelcon/idetectfugas`) — LDS/NPW/PPA/… **sobreescriben** `while_waiting` y llenan **su** `self.buffer`, no el `self.data` del framework |
| **Veredicto** | El runtime de SM es **core y usable** (A− scheduler). Las tres capas de tiempo **sí son independientes**. El buffer canónico `StateMachineCore.data` **no se alimenta** (SM-H1): `wait → run` del core es teatro salvo que la app lo sustituya. La cadencia de la ventana algorítmica en planta es hoy **el ciclo de la máquina**, no el `scan_time` de campo |
| **Clasificación** | Auditoría de arquitectura · runtime de control |

---

## 0. Respuesta directa

| Pregunta | Respuesta (código 2026-08-18) |
|---|---|
| ¿Cada cuánto corre un ciclo de máquina? | Cada `machine_interval` **segundos** (default **1.0**). El scheduler compensa el tiempo de `loop()`: duerme `interval − elapsed`. Si `elapsed > interval` loguea *NOT executed on time* y no duerme |
| ¿Cómo se configura? | Constructor (`interval=`), `append_machine(..., interval=FloatType(s))`, `set_interval()`, API `PUT /machines/<name>/attributes` (`interval`), persistencia BD (`Machines.interval`) y YAML de app si el módulo lo implementa |
| ¿El buffer de tags suscritos se llena con el dato de campo? | **El CVT sí** (último valor + observers). **`self.data` del framework no**: `notify()` actualiza `ProcessType.value` (last-wins) y `data_timestamp`; **nunca** hace `self.data[tag](muestra)`. Ver SM-H1 |
| ¿Con qué frecuencia se actualiza el valor visto por la SM? | A ritmo de **adquisición** (DAQ/DAS) que pasa deadband. Cada `cvt.set_value` notifica `MachineObserver` → `machine.notify` |
| ¿Con qué frecuencia se llena el buffer de ventana? | En el **core: nunca**. En apps tipo iDetectFugas: **una muestra por ciclo de máquina** (`verify_inputs` en `while_waiting` / `while_running`), tomada del `ProcessType` ya notificado |
| OPC UA cada 200 ms y SM a 1 s: ¿qué pasa? | Campo → CVT ~5 Hz. La SM ve el **último** valor en cada tick de 1 s. Las 4 muestras intermedias **no entran** en la ventana de la máquina (se perdieron para el algoritmo; el historiador SAF sí las puede tener si pasaron deadband) |
| ¿Se puede llenar el buffer a otra frecuencia ≥ adquisición? | **No hay palanca de “fill interval”.** Para muestrear más fino que el ciclo hay que **bajar `machine_interval`** (y entonces el ciclo también corre más rápido) **o** empujar muestras en `notify()` (hoy no existe). No se puede “llenar el buffer a 200 ms y ejecutar lógica a 1 s” con el core actual |
| ¿El ciclo puede ser más rápido que el campo? | **Sí.** Si `machine_interval` < `scan_time`, el ciclo **repite el último valor** de CVT. La ventana se llena de duplicados |
| ¿Tiempos de muestreo distintos por capa? | **Sí, y es el diseño actual.** Ver §4. No hay un reloj maestro único |

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
| `DAQ` | SM de **sondeo** OPC UA; un ejemplar por `scan_time` (`DAQ-200`, `DAQ-1000`, …) |
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
| **C. Framework SM** | `StateMachineCore.data[tag_name]` | **Nadie** (SM-H1) | — | `buffer_size` (default **10**), roll `backward` |
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

**SM-H1 — Crítica (producto / framework):** `StateMachineCore.data` es un anillo huérfano. `buffer_size` / `buffer_roll_type` del core no gobiernan la ventana real salvo que la subclase copie el tamaño a `self.buffer` (LDS lo hace en `on_enter_waiting`). Cambiar `buffer_size` por API llama `set_buffer_size` → `restart_buffer()` del **core** y, en iDetectFugas, persistencia YAML + reinicio de la ventana de app.

---

## 4. Capas de muestreo — versatilidad actual

```
Campo / PLC
    │  scan_time del tag (ms)
    ├─ ≤ 100 ms o None  →  DAS (suscripción OPC UA, datachange)
    └─ > 100 ms         →  DAQ-<scan_time>  (poll, intervalo = scan_time/1000 s)
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

Deadband en `CVT.set_value` **corta** `Tag.set_value` y por tanto **no** hay `MachineObserver`. El `ProcessType` de la SM se queda en el último valor que pasó la banda. Ver [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md).

Kalman (“gaussiano”) si está ON actúa en este hot path, **antes** de que la SM vea el valor.

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

**SM-C1 — Diseño vigente:** las capas 1 y 3 **sí** tienen periodos propios. La capa “buffer de SM” **no** tiene periodo propio: o es el ciclo (apps) o no existe (core).

---

## 5. Ejemplo numérico — OPC UA 200 ms, SM 1 s, `buffer_size=40`

1. Tag con `scan_time=200` → se crea/reutiliza `DAQ-200`, `interval=0.2` s, modo async.
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
    → machines_engine.bind_tag
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

Decoradores IAD en `CVT.set_value` siguen **comentados**. `process_filter` no corre. Una SM **no** puede asumir datos “acondicionados de proceso”; solo deadband + Kalman opcional.

### 7.7 API de atributos

`PUT .../attributes`: `threshold`, `interval`, `buffer_size`, `on_delay` (+ modo de umbral PPA/NPW). `buffer_size` persiste YAML **antes** de reiniciar. `interval` se escribe en BD como `IntegerType(int(interval_value))` — **trunca** subsegundos al persistir (0.2 s → 0). **SM-H2.**

### 7.8 Roll del buffer

`forward` = newest at index 0; `backward` = append (default de SM). `Buffer` exige `size > 1` internamente (`maxlen = max(size, 2)`). La API acepta `buffer_size > 0`: un `1` pasa REST y choca con el anillo.

---

## 8. Hallazgos

| ID | Severidad | Hecho | Impacto | Mitigación actual / residual |
|---|---|---|---|---|
| **SM-H1** | Alta (framework) | `self.data` nunca recibe muestras; `notify` es last-wins | Core `wait→run` no funciona; docs mienten; `buffer_size` del core no es la ventana | Apps (iDetectFugas) override + `self.buffer`. Residual: cualquier SM “vanilla” se queda en `wait` |
| **SM-H2** | Media | Persistencia de `interval` vía API usa `int(seconds)` | `0.2` s se guarda como `0` en BD; al reboot el config loader puede romper el periodo | No usar subsegundo si se depende de BD, o persistir float |
| **SM-H3** | Baja | DAS actualiza su anillo si `set_value` retorna no-`None`; el deadband de CVT **retorna el valor** sin notificar SM | Tendencia HMI puede avanzar y la SM no | Correlacionar `on.tag` vs `ProcessType` |
| **SM-H4** | Media (ops) | DAS publishing interval fijo **1000 ms**; el umbral 100 ms no es el periodo de muestreo OPC | Quien pone `scan_time=50` cree 20 Hz; el cliente pide publish 1 Hz | Para 200 ms usar **DAQ** (`scan_time>100`), no DAS |
| **SM-H5** | Baja | Dos fórmulas de tamaño de `das.buffer` (10 s vs 600 s; `ceil(scan_time/1000)` trata 200 ms como 1 s) | Anillo HMI de tags sub-segundo queda corto (~10 muestras) | No fiarse de DAS buffer como historiador |
| **SM-C1** | Info / diseño | Periodos por capa independientes; no hay fill-interval | Decimación last-wins si SM más lenta que el campo | Documentar; o implementar push en `notify` si se exige ventana a ritmo de campo |
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
| API atributos SM | `automation/modules/machines/resources/machines.py` |
| Guía (desactualizada en el punto del buffer C) | `docs/Developments_Guide/core/state_machines.md` |
| Patrón app de ventana real | `gitlab/intelcon/idetectfugas/app/modules/{lds,npw,...}/__init__.py` `verify_inputs` |

---

## 10. Criterio de aceptación (si se cierra SM-H1)

Un tag de campo a 200 ms y una SM a 1 s deben poder declararse así, de forma explícita y testeable:

1. **Adquisición** = 200 ms (DAQ-200).
2. **Ciclo de lógica** = 1 s (`machine_interval`).
3. **Ventana** = o bien “N ciclos de máquina” (hoy, de facto) o “N muestras de campo” (requiere push en `notify` o un sampler). **No mezclar ambos significados en un solo `buffer_size` sin documentarlo.**

Hasta entonces, en planta: **`buffer_size` × `machine_interval` ≈ horizonte temporal de la ventana**, no `buffer_size` × `scan_time`.

---

## 11. Conclusión

PyAutomation **sí** deja definir tiempos distintos por capa: `scan_time` (campo, ms, agrupado en DAQ o DAS), `machine_interval` (lógica, s, por máquina) e historiador (evento CVT). Esa es la versatilidad real.

Lo que **no** está es un tercer reloj “frecuencia de llenado del buffer de la SM” desacoplado del ciclo. El anillo del framework no se alimenta; las aplicaciones serias muestrean el CVT **una vez por tick**. OPC UA a 200 ms no llena una ventana de 40 a 200 ms: llena el CVT a 200 ms y, si la máquina corre a 1 s, la ventana avanza a 1 Hz.

Para una SM nueva: no confiar en `while_waiting` del core; decidir si la ventana es tiempo-de-máquina o tiempo-de-campo; y no bloquear el `while_*`.
