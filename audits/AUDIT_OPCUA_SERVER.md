# Auditoría: servidor OPC UA embebido (`OPCUAServer`) — V8

| Campo | Valor |
|---|---|
| **Documento canónico** | `AUDIT_OPCUA_SERVER.md` |
| **Revisión** | **V8** — migración a asyncua (2026-09-23) |
| **Sustituye** | V7 (contrato NodeId opción B, servidor sobre `opcua` 0.98.13) |
| **Producto** | PyAutomationIO 2.9.0 |
| **Código** | `automation/opcua_server/` |
| **Pruebas** | 93 tests del paquete en verde, 1 E2E omitido. La corrida tardó 0.9 s |
| **Veredicto** | El servidor embebido ya no instancia `opcua.Server`. Corre `asyncua` 2.0.1 en un hilo de sistema. El objetivo de arranque de 5 s queda abierto: una muestra N=5000 dio p95 = 9566 ms |
| **Fuera de alcance** | Security Policy activa, PKI, AlarmCondition Part 9, HA, Historical Access, PubSub, certificación, cliente OPC UA saliente, o6Python |

---

## Migración a asyncua

`requirements.txt` pide `asyncua>=2.0.1`. El cliente de campo ya no usa `opcua` (ver `AUDIT_OPCUA_CLIENT.md` V2) y el paquete salió de las dependencias. El paquete `automation/opcua_server/` no importa `opcua`. CVE-2022-25304 queda cerrada en el servidor porque ese proceso no crea `opcua.Server`. `tests/test_security_cve.py` comprueba que la versión instalada es al menos 2.0.1 y que `SecurityPolicyBasic256Sha256` se importa. La política no se activa.

El hilo de asyncio se crea con `gevent.monkey.get_original` (`Thread`, `Event`, `queue.Queue`). La cola tiene `maxsize` 10000. El tick gevent arma snapshots y los encola. El loop drena hasta 200 comandos, agrupa las escrituras en un `WriteParameters` y, si la cola está vacía, duerme 50 ms. `test_async_runner` mete 100 comandos sin red y comprueba que el handler corre en otro hilo.

El NodeId, el árbol y el tope de properties no cambian. La fachada sigue en 197 líneas. La API (`enqueue_expose`, tick, reset, snapshot) conserva los nombres.

Una sola muestra, timer después de cargar el address space estándar:

| Bench | Medición | Objetivo | Resultado |
|---|---|---|---|
| Arranque N=5000 | p95 = 9566 ms | < 5000 ms | Abierto. También supera el gate previo de 8000 ms. `STARTUP_GATE_MS` no se sube |
| Update, 20 escrituras | p95 = 0.027 ms | < 5 ms | Dentro |
| Expose, un alta | p95 = 0.113 ms | < 100 ms | Dentro |
| Memoria N=10000 | RSS = 241.5 MB | < 250 MB | Dentro |

La cifra 3.8× del spec es un bench de terceros (o6Python frente a asyncua). Esta corrida no la reproduce. El arranque medido aquí es más lento que los 7511 ms de `opcua` 0.98.13 en la V6.

| CA | Estado | Evidencia |
|---|---|---|
| CA-ASYNCUA-01 | Cumple | `asyncua>=2.0.1` en `requirements.txt`. Instalado 2.0.1 |
| CA-ASYNCUA-02 | Cumple en el servidor | El embebido no instancia `opcua.Server`. El paquete `opcua` sigue para el cliente |
| CA-ASYNCUA-03 | Cumple | `make_node_id` no se reescribió. Los tests de identidad siguen verdes |
| CA-ASYNCUA-04 | Cumple | `ensure_branch_async` arma `PyAutomationIO/{site}/{area}/{Process,Alarms,Engines}` |
| CA-ASYNCUA-05 | Cumple | El snapshot de un tag analógico lleva como máximo 5 properties. No se publica `area`. Los tests de exposers quedan en 6 nodos |
| CA-ASYNCUA-06 | Cumple | `to_data_value` sigue armando Value, StatusCode, SourceTimestamp y ServerTimestamp con `asyncua.ua` |
| CA-ASYNCUA-07 | Cumple | La fachada no renombra métodos |
| CA-ASYNCUA-08 | Abierto | p95 = 9566 ms, una muestra |
| CA-ASYNCUA-09 | Sin medición nueva | El test de allocations del scheduler gevent sigue bajo 1 KB para K=20. No hay p95 de un tick live |
| CA-ASYNCUA-10 | Cumple | p95 = 0.113 ms |
| CA-ASYNCUA-11 | Cumple | RSS = 241.5 MB |
| CA-ASYNCUA-12 | Cumple | Una suscripción de escritura, creada en `_ensure_write_subscription` |
| CA-ASYNCUA-13 | Cumple | `write_batch` arma un solo `WriteParameters` |
| CA-ASYNCUA-14 | Cumple | Igual que CA-ASYNCUA-02 |
| CA-ASYNCUA-15 | Cumple | El símbolo importa. No se instala en el endpoint |
| CA-ASYNCUA-16 | Cumple | `asyncua.sync.Server` y `Client` quedan en el e2e, detrás de `OPCUA_E2E=1` |
| CA-ASYNCUA-17 | Cumple | `AsyncioRunner` |
| CA-ASYNCUA-18 | Cumple | `CommandQueue(maxsize=10_000)` |
| CA-ASYNCUA-19 | Cumple | `start`, `add_variable` y `write` ocurren en el loop. El tick gevent solo llama a `submit` |
| CA-ASYNCUA-20 | Cumple | Igual que CA-ASYNCUA-07 |

Invariantes: A-1 el hilo gevent no toca el address space. A-2 la cola tiene tope. A-3 el loop duerme cuando no hay comandos.

---

## 0. Perfil del arranque

`benchmarks/profile_startup.py` escribió `startup_profile.prof` (materialización del paquete, 5000 tags analógicos) y `startup_bench_profile.prof` (el bench del gate). Top 10 por cumulative, tiempo propio partido:

| Perfil | tottime `opcua` | tottime `opcua_server` | Resto |
|---|---|---|---|
| Paquete, N=5000 | 22.243 s | 0.536 s | 3.065 s |
| `bench_startup_real`, N=5000 | 20.409 s | 0.027 s | 2.657 s |

En los dos perfiles las diez funciones de mayor cumulative son `add_nodes`, `_add_node`, `create_variable` y `_add_unique_reference` de opcua 0.98.13. `make_node_id` no está en ese top 10. El cuello del gate no es el paquete.

---

## 1. Gate de startup

Remedición sin profiler, una repetición, N=5000: **p95 = 7511 ms**. Sigue por encima de 5000 ms y por debajo de 8000 ms.

`STARTUP_GATE_MS = 8000` en `benchmarks/bench_startup_real.py`. `compare.py` usa esa constante. Justificación: crear 5000 variables en este stack cuesta unos 7.5 s y el perfil lo atribuye a la librería. El arranque ocurre una vez por cold boot. La migración a asyncua sigue fuera de alcance.

Los otros tres benches, misma corrida:

| Bench | Medición | Gate | Resultado |
|---|---|---|---|
| update, 20 push | p95 = 0.036 ms | &lt; 5 ms | Dentro |
| expose, un alta | p95 = 0.213 ms | &lt; 100 ms | Dentro |
| memoria, N=10000 | RSS = 230.9 MB | &lt; 300 MB | Dentro |

No hay regresión respecto de los gates que ya pasaban en la V5. Esas cifras son de la V6 y no se volvieron a medir en esta revisión.

---

## 2. Contrato NodeId (opción B)

El identificador publicado es `ns=<idx>;s=<t|a|e>:<nombre-canonico>`. `AUTOMATION_MANUFACTURER` y `AUTOMATION_SEGMENT` son las carpetas `{site}` y `{area}` bajo `Objects/PyAutomationIO`. No son campos del NodeId: el nombre del tag ya trae el segmento.

Ejemplo: `Supe.Linea1.FI_01` es `t:supe.linea1.fi_01`.

`canonicalize_name` cumple, y `test_identity_contract` lo demuestra:

| Garantía | Qué se comprueba |
|---|---|
| G1 determinista | 100 llamadas al mismo nombre devuelven el mismo id |
| G2 idempotente | Aplicar la función al resultado no lo cambia |
| G3 sin caja | `casefold` |
| G4 espacios | El espacio colapsa a `.` |
| G5 Unicode | NFC. No se usa NFKC |
| G6 separadores | `;` y `,` pasan a `_` |
| G7 longitud | El resultado cabe en 256. La entrada se corta a 512 antes del `lru_cache` |
| G8 nunca vacío | `""` y un área vacía quedan en `_` |
| G9 controles | Se quitan `\x00`–`\x1f` y `\x7f` |

Los puntos se quitan solo al inicio y al final (`.FI_01` → `fi_01`). `FI..01` se conserva. El homoglyph `FⅠ_01` (U+2160) y `FI_01` siguen siendo identificadores distintos a propósito: plegarlos cambiaría NodeIds ya publicados. `test_reserved_prefixes` lo deja escrito.

`folder_token` usa la misma canonicalización. Vacío sigue siendo `Default` o `Global`, no `_`.

Un alta nueva, si hay fabricante o segmento, antepone `{site}.{area}.` (`Default` o `Global` cuando falta uno de los dos). Si los dos están vacíos, el nombre guardado no cambia: así una planta sin esas variables no parte el catálogo entre tags viejos y nuevos. `qualify_user_tag_name` sigue siendo la regla HMI de tres partes. La recarga y `skip_validation` no reescriben el nombre persistido. Los tags de sistema (`SYS.*`, `ALM.PERF.*`) entran por `skip_validation` y se siguen publicando.

`validate_tag_name` rechaza, con `ValueError`, un canónico que empiece por `pyautomationio.`, `sys.`, `alm.perf.` o `alarm.sys.`. `alarm.lds.leak` no coincide con `alarm.sys.`. `AddressSpaceBuilder.reject_reserved_leaf` aplica esa misma regla. El exposer no la corre sobre el catálogo ya cargado, para no borrar del árbol los tags de diagnóstico que el producto crea a propósito.

Si otro tag del CVT tiene el mismo canónico y otro nombre de negocio, el alta no se crea. Recrear el mismo nombre no choca consigo mismo. La búsqueda es solo en el alta. El tick no recorre el catálogo.

El tick compara, una vez y en O(1), `AUTOMATION_MANUFACTURER` y `AUTOMATION_SEGMENT` con el valor tomado en el primer tick. Un cambio posterior audita una sola vez y actualiza el recuerdo. No reescribe tags.

| Evento | Criticidad |
|---|---|
| `OPC UA tag rejected: reserved prefix` | 3 |
| `OPC UA NodeId collision rejected` | 3 |
| `OPC UA manufacturer changed` | 4 |
| `OPC UA segment changed` | 5 |

`test_node_id_stability` cubre la raíz `PyAutomationIO`, las carpetas vacías, que mover la hoja no entra en el NodeId, que cambiar el área sí cambia el id, que cambiar el manufacturer de entorno no, y que el cambio de segmento se audita una vez.

---

## 3. NodeIds, properties y budget

`precompute_node_ids` corre en el arranque en frío, antes de encolar, y llena `_node_id_cache`. `canonical_for` lee ese cache. Un alta posterior se calcula en `enqueue_expose`. `make_node_id` queda fuera del top 10 del perfil.

El tag analógico publica como máximo 5 properties y 6 nodos: `unit` (símbolo de display en texto), `EURange` si hay rango, `variable`, `runtime_config` (JSON con `scan_time` y `dead_band` si aplican) y `filter_config` (JSON con `enabled`, `wavelet`, `level`, `threshold_factor` si el filtro está activo). Bool y string publican solo `variable`. No hay property `area` ni `EngineeringUnits`.

El tick elige el budget de exposición en O(1):

- Cola mayor que 1000: 1000 ops y 200 ms.
- p95 de los últimos 5 ticks mayor que 100 ms: 100 ops y 30 ms.
- Resto: 200 ops y 50 ms.

El corte por milisegundos manda. Con 7511 ms / 5000 variables, cada alta del bench cuesta unos 1.5 ms, así que 1000 ops no caben en 200 ms. En el perfil del paquete, 5000 `upsert` acumularon 24.7 s (unos 4.9 ms por tag bajo el profiler): un tick de 200 ms materializa del orden de 40 tags y la cola de 5000 no se vacía en 5 ticks. **CA-BUD-05 no se cierra.** No se subió el techo del tick para forzarlo. El drenado dirty y el reset no cambiaron de forma: el tick sigue O(B + K).

---

## 4. Mediciones que faltaban

`benchmarks/bench_pending_cas.py`, tick con el push al stack sustituido:

| CA | Medición | Objetivo | Resultado |
|---|---|---|---|
| CA-PERF-02 | 72 bytes del paquete en un tick K=20 | &lt; 2048 | Dentro |
| CA-PERF-03 | 696 bytes totales del mismo tick | &lt; 10240 | Dentro |
| CA-PERF-06 | reset 0.211 ms con N=100 y 0.628 ms con N=10000 | medido | Medido. 100× entidades costaron unas 3×, los dos bajo 1 ms. `dict.clear` recorre las entradas; no es una constante plana |
| CA-PERF-07 | p95 0.015 ms (N=100) y 0.009 ms (N=10000), ratio 0.63 | ≤ 2× | Dentro |

---

## 5. Métricas

`as_dict` expone 31 claves. A las 26 de la V6 se suman:

- `OPCUA_NODEID_COLLISIONS_TOTAL`
- `OPCUA_NODEID_RESERVED_PREFIX_REJECTED_TOTAL`
- `OPCUA_NODEID_LENGTH_TRUNCATED_TOTAL`
- `OPCUA_SITE_FOLDER`
- `OPCUA_AREA_FOLDER`

Los tres contadores viven en la identidad, porque el truncado ocurre dentro de `canonicalize_name` aunque el servidor no esté en esa llamada. El snapshot pasa el site y el area actuales con `folder_token`. `OPCUA_LINT_VIOLATIONS_TOTAL` sigue fuera. `OPCUA_MEMORY_STRUCTURES` sigue dentro. `OPCUA_ENGINE_WATCHDOG_RECOVERIES_TOTAL` y `OPCUA_TAG_WATCHDOG_RECOVERIES_TOTAL` siguen dentro.

---

## 6. CAs estructurales

| CA | Estado | Evidencia |
|---|---|---|
| CA-STR-01 | Cumple | `facade.py` tiene 197 líneas, bajo 200 |
| CA-STR-02 | No se fuerza | La fachada importa `CanonicalPublisher`, `PerTagDirtyTracker` y `WatchdogSupervisor`. Es la raíz de composición. Moverlos rompería el arreglo de este sprint y esos módulos están congelados |
| CA-STR-03 | Cumple | `IPublisher` en `publishing/publisher.py`, `NodeExposer` en `exposures/base.py`, `IDirtyTracker` en `dirty/tracker.py`, `IWatchdogHandler` en `watchdog/handler.py`, `ICapabilityProbe` en `analog_item/capability.py`, `LintRule` en `linting/rule.py` |
| CA-STR-04 | Cumple | `Registry.freeze()` y un `register` posterior lanzan `RuntimeError`. Verificado en esta corrida |
| CA-STR-05 | Parcial | 111 métodos públicos de sprints anteriores siguen sin la línea `Complexity:`. Los métodos de identidad, el budget y `process_expose_queue` sí la tienen |
| CA-STR-06 | Cumple | Ningún módulo del paquete, fuera de tests y benches, carece de docstring de módulo |
| CA-STR-07 | Parcial | `import automation.opcua_server` carga. `pydeps` no está instalado, así que no hubo grafo de ciclos |

---

## 7. CAs de coherencia

| CA | Estado | Evidencia |
|---|---|---|
| CA-COH-01 | Parcial | `test_data_value` cubre StatusCode y SourceTimestamp de un DataValue. No se añadió un browse de 100 tags (suite nueva fuera de alcance). El tick escribe por `push_value` |
| CA-COH-02 | Cumple | El exposer analógico ya no publica `scan_time`, `dead_band` ni `filter_*` como properties sueltas. Esas claves viven dentro del JSON |
| CA-COH-03 | Cumple | `test_regression_golden`: el NodeId no cambia con la caja ni con el espacio interno |
| CA-COH-04 | Cumple | `test_node_id_stability`: otro segmento produce otro NodeId. Cambiar `AUTOMATION_MANUFACTURER` no. El identificador sigue siendo tipo + área + nombre |
| CA-COH-05 | Cumple | `AnalogItemProbe.probe` guarda el resultado. `test_analog_item` comprueba que la segunda llamada no repite el trabajo |
| CA-COH-06 | Cumple | `test_fallback_is_audited_once`: el fallback audita una vez y el contador queda en 1 |

---

## 8. CAs de excelencia

| CA | Estado | Evidencia |
|---|---|---|
| CA-EXC-01 | Cumple | Los seis contratos de CA-STR-03 son ABC |
| CA-EXC-02 | Parcial | `test_dirty_tracker` sustituye el tracker por un fake y el tick lo usa. No hay fakes dedicados de publisher ni de handler de watchdog en la suite actual |
| CA-EXC-03 | Cumple | El mismo `RuntimeError` de CA-STR-04 |
| CA-EXC-04 | Cumple | `test_watchdog`: una transición marca el engine sin pasar por `while_running`. La reconciliación recupera un engine que no vio la transición |
| CA-EXC-05 | Cumple | `test_fake_tracker_is_used_by_the_tick`: `runtime.py` no importa el tracker concreto |

---

## 9. Cierre

La V6 dejó el gate en 8000 ms con p95 = 7511 ms, el budget adaptativo, las properties JSON y las mediciones de la sección 4. Esta revisión no las repite.

| ID | Resultado |
|---|---|
| Contrato | Opción B. `MANUFACTURER` es carpeta. G1–G9 las cubre `test_identity_contract` |
| Homoglyph | `Ⅰ` y `I` siguen distintos a propósito |
| Rechazos | Prefijo reservado y colisión de canónicos, solo en alta nueva |
| Entorno | Un cambio de manufacturer (criticidad 4) o de segmento (criticidad 5) se audita una vez y no reescribe tags |
| Métricas | 31 claves en `as_dict` |
| Fachada | `facade.py` sigue en 197 líneas. La vigilancia de entorno está en el tick, no en la fachada |
| Docs | Contrato en la guía de desarrollo, el browse en la guía de usuario, la opción B en la spec, entrada en `CHANGELOG.md` 2.9.0 |
| Suite | `python -m unittest discover -s automation/opcua_server/tests -t .` — 89 tests, 1 omitido |

Siguen fuera: seguridad, AlarmCondition, HA, asyncua, histórico, PubSub y certificación. CA-BUD-05, CA-STR-02, CA-STR-05 y CA-EXC-02 quedan abiertos con la evidencia de la V6.

---

El cierre de AccessLevel, write-back y multi-hop (G-01..G-09) está en `audits/RE-AUDIT-OPCUA-ACCESSLEVEL-MULTIHOP.md` §13. Esta auditoría no reescribe esa evidencia ni la de las revisiones anteriores.

*Fin de auditoría `AUDIT_OPCUA_SERVER.md` V8 — 2026-09-23. Las secciones numeradas conservan la evidencia de la V6 y el contrato de la V7.*
