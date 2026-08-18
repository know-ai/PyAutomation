# Auditoría compacta: adquisición multi-edge y partición por línea

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | N equipos edge, cada uno con una instancia de PyAutomation + un servidor OPC UA de línea, historiador PostgreSQL **compartido** |
| **Premisa de planta** | 2 secciones / líneas; ~20 puntos por línea (P, T, Q, ρ); persistencia en la misma BD; el cliente exige un edge por línea |
| **Fecha original** | 2026-08-18 (baseline: hidratación `read_all()`, sin identidad de nodo) |
| **Compactación** | 2026-08-18 — este archivo ya era el documento único del dominio; se actualizaron enlaces y el contraste con specs |
| **Tipo** | Auditoría de contraste · arquitectura · nomenclatura industrial · backlog de grado nuclear |
| **Complementa** | `specs/01-MULTI-EDGE-ARCHITECTURE.md`, `docs/multi-edge.md`, [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [AUDIT_DB.md](./AUDIT_DB.md) |
| **Veredicto** | **Fase 1 está en código y pasó laboratorio de 1 edge** (iDetectFugas, `NODE_ID=edge-linea1`, `SEGMENT=Linea1`). Identidad con alias, fail-closed, hidratación acotada, single-writer O(1), SAF aislado, API/HMI acotados y contrato de alarmas de aplicación existen, con suite `test_multi_edge_*`. **No es un producto de grado nuclear:** faltan unique compuesto, RLS, consola/heartbeat operativo, migración de BD poblada, soak 24 h con **dos** edges reales y las defensas de §5. La spec `01` aún se titula «propuesta no implementado»: **el contraste de implementación es este archivo**, no el encabezado de la spec |
| **Clasificación** | Confidencialidad interna · grado de diseño (ISA-95 / IEC 62264) |

---

## 0. Respuesta directa

| Pregunta | Respuesta (hoy) |
|---|---|
| ¿Esto es «escalado horizontal»? | **Solo en un sentido estrecho.** No es *scale-out* de un servicio stateless. Es **scale-out del piso de adquisición**: N nodos edge, cada uno dueño de una **partición de I/O**, escribiendo a un **historiador compartido** |
| Nombre industrial habitual | **Distributed / edge data acquisition**; ISA-95: nodos de **Área / Línea**; SCADA: **interface nodes / collectors**. Software: **shared-database partitioned writers** |
| ¿PyAutomation aísla una línea por instancia? | **Sí, en el plano de aplicación.** Loaders de runtime filtran por `area` / `owner_node`. Sin `NODE_ID` y un área (`AREA` o `SEGMENT`) no hay `read_all()` de tags/OPC. El HMI/API siguen vivos (fail-closed de adquisición, no de presentación) |
| ¿El CVT de un edge persiste solo «su» línea? | El CVT es memoria de proceso y ahora **se poda** en reconnect. La persistencia sigue yendo al historiador global, con `area`/`owner_node` en el registro y rechazo de enqueue/replicación ajenos |
| ¿Al apagar y levantar un edge se mezcla la otra línea? | **No debe**, si la identidad está bien y el catálogo tiene `area`/`owner_node`. Filas históricas **nulas** no se infieren (salvo `AlarmSummary.area` copiado desde la definición `Alarms.area`). Una BD poblada **sin backfill de catálogo** no es un deploy válido de N edges |
| ¿Se puede desplegar N edges contra la misma BD? | **Sí como receta de código**, con un contenedor por área, journals `./db/saf/<node_id>/` y `owner_node` en clientes OPC. **No** está cerrada la evidencia de planta (2 procesos + 2 OPC + soak 24 h) |
| ¿El HMI pide histórico por área al abrir la pantalla? | **No.** Resumen de alarmas, eventos, logs, tendencias y datalogger arrancan en modo planta: **no envían** el parámetro `area`. El operador puede restringir después con el selector «Toda la planta» / un área |

Principio que no cambió: **un punto de proceso tiene un y solo un escritor de tiempo real.** El historiador es la verdad del pasado; el CVT es la verdad **local** del edge que posee esos tags.

---

## 1. Cómo se llama esto (y cómo no)

### 1.1 Lo que **no** es

| Término | Por qué no aplica |
|---|---|
| Escalado horizontal clásico (web) | Réplicas **idénticas** e **intercambiables**. Aquí cada edge **no** puede adquirir la línea del otro: el cable OPC UA es físico y local |
| Balanceo de carga (L4/L7) | No hay un pool de workers PyAutomation delante de un VIP para «repartir tags» |
| Sharding de base de datos | Sigue habiendo **un** historiador. Lo que se parte es la **adquisición**, no el almacenamiento |
| Multi-tenant SaaS | El cliente no pide dos empresas; pide dos **áreas de proceso** de la misma planta |
| HA activo-activo del mismo OPC | Fuera de alcance **permanente**. Mover I/O a otro edge sin cambio de red es inventar datos |

Llamar a esto «escalado horizontal» en un RFP o en un HAZOP confunde: un auditor pensará en N réplicas activas-activas del mismo servicio.

### 1.2 Nombre correcto (industria + software)

En **ISA-95 / IEC 62264** la jerarquía es Empresa → Sitio → **Área** → **Línea** → Unidad → Equipo. Cada edge es un nodo de **Nivel 2** (control/SCADA de línea) que publica hacia Nivel 3 (historiador / MES).

| Nombre | Uso |
|---|---|
| **Adquisición distribuida en el edge** | Conversación con el cliente / operaciones |
| **Colectores particionados por línea (partitioned collectors)** | Arquitectura de software |
| **Nodo de interfaz / interface node** | Historiadores (analogía PI, eDNA, Ignition Edge) |
| **Área ISA-95 como clave de partición** | Modelo de datos |
| **Single-writer per tag** | Invariante de consistencia (un tag, un dueño de escritura) |
| **Scale-out del tier de I/O** | Si hace falta la palabra *scale*: se escala la **captura**, no el proceso monolítico |

```
                    ┌─────────────────────────────────────┐
                    │     Historiador PostgreSQL (L3)      │
                    │   catálogo global + TagValue + SAF   │
                    └──────────────▲──────────▲────────────┘
                                   │          │
                    replica SAF    │          │    replica SAF
                    (solo su       │          │    (solo su
                     partición)    │          │     partición)
                                   │          │
              ┌────────────────────┴──┐    ┌──┴────────────────────┐
              │ Edge A  — Línea 1     │    │ Edge B  — Línea 2     │
              │ PyAutomation instancia│    │ PyAutomation instancia│
              │ CVT: tags de L1       │    │ CVT: tags de L2       │
              │ Cliente OPC UA → L1   │    │ Cliente OPC UA → L2   │
              │ SAF journal local     │    │ SAF journal local     │
              └──────────▲────────────┘    └──────────▲────────────┘
                         │                            │
              ┌──────────┴────────────┐    ┌──────────┴────────────┐
              │ Servidor OPC UA L1    │    │ Servidor OPC UA L2    │
              │ (equipo / red de L1)  │    │ (equipo / red de L2)  │
              └───────────────────────┘    └───────────────────────┘
```

Eso **sí** escala en horizontal el I/O (más líneas ⇒ más edges). El historiador escala aparte (conexiones, índices, retención).

---

## 2. Estado tras esta iteración (Fase 1 + laboratorio)

Contraste respecto al baseline («hidratación `read_all()`, filtro SEGMENT/MANUFACTURER solo en parte del hot path») y respecto al corte que cerró CA-EDGE-1..8 en unitarias.

### 2.1 Entregado en código

| Superficie | Qué hay ahora | Dónde |
|---|---|---|
| Identidad | `NodeScope` inmutable; multi-edge **true por defecto**. Adquisición exige `NODE_ID` y un área: `AUTOMATION_AREA` **o** `AUTOMATION_SEGMENT`. Sitio: `AUTOMATION_SITE` **o** `AUTOMATION_MANUFACTURER` (metadato, no fail-closed) | `automation/node_scope.py` |
| Alias | `AREA` y `SEGMENT` son la misma clave. Si ambos existen y **difieren** → `identity_conflict`, fail-closed. `SITE` y `MANUFACTURER` distintos **no** bloquean: se usa `MANUFACTURER` (un `SITE` residual no tumba el arranque) | `NodeScope.from_env`, `blocked_reason` nombra la causa real |
| Fail-closed | Sin identidad válida: API/HMI/health vivos; **no** hidratar CVT/OPC ni arrancar workers de adquisición | `connect_to_db` / `run` / `acquisition_ready` |
| Registro de nodo | Tabla `Nodes`; UPSERT idempotente; rechaza el mismo `node_id` en otra `area`; `last_seen` en reconnect | `automation/dbmodels/nodes.py` |
| Esquema | `area` / `owner_node` en Tags, OPCUA, Machines, Alarms, TagValue, AlarmSummary, Events, Logs; índice `(area, timestamp)` en histórico. **Sin backfill general** de filas nulas | `ensure_schema()` |
| Excepción de sello | `AlarmSummary.area` se escribe en el create y, al conectar, se **copia** desde `Alarms.area` si la fila histórica está nula. No infiere dueño desde el nombre ni desde `SEGMENT` | `AlarmSummary.create`, `_backfill_area_from_alarm` |
| Hidratación | Tags/alarmas/máquinas por `area`; clientes OPC por `owner_node`; users/roles/catálogos globales compartidos | loaders en `core.py` |
| Reconnect | Diff + `_prune_runtime_scope()`: retira tags/observers/alarmas/OPC ajenos **sin** vaciar el CVT | `core.py` |
| Single-writer | `owns_tag()` O(1) en `set_value` / `set_value_fast`; DAS no suscribe namespace ajeno; OPC no `connect()` si `owner_node` ≠ local | `cvt.py`, `subscription.py`, `opcua_client.py` |
| SAF | Journal `./db/saf/<node_id>/journal.db`; observer/orquestador rechazan enqueue ajeno; replicator descarta PENDING extranjero | `persistence/` |
| Trazabilidad PG | `application_name=PyAutomationIO:<node_id>:<rol>` (≤ 63 chars). Legacy `PyAutomationIO:<rol>` si multi-edge está off | `db_connections.py` |
| API / HMI | Runtime GET/Socket.IO acotados; POST/PUT/DELETE 403 recurso ajeno, 503 identidad ausente; import rechaza datos ajenos **antes** de mutar. Lecturas históricas **sin** filtro de área por defecto | `automation/modules/`, `export/import_configuration` |
| Health | `NODE_ID`, `NODE_AREA`, `NODE_SITE`, `MULTI_EDGE_ENABLED`, `ACQUISITION_READY`, `ACQUISITION_BLOCKED_REASON`, `SAF_QUEUE_DEPTH` | `/api/health/system` |
| Tags de API | `create_tag` sigue exigiendo prefijo de área (`Linea1.FI_01`). Unique global intacto | `core.create_tag` |
| Tags internos | Máquinas escriben `{MANUFACTURER}.{SEGMENT}.{máquina}.*` vía `cvt.set_tag` (sello `area`/`owner_node`, **sin** exigir prefijo `Linea1.`) | `state_machine.create_tag_internal_process_type` |
| Alarmas de aplicación | El nombre **no** lleva prefijo de área. La frontera es `owns_tag` del tag asociado. iDetectFugas: `alarm.{máquina}.leak` | `core.create_alarm`, `test_leak_alarm_name_does_not_need_area_prefix` |
| Alarmas de sistema | Siguen cualificadas: `Linea1.ALM.DB.Connection`, `Linea1.ALM.OPCUA.*` | `connection_alarms._scoped_name` |
| Histórico de planta | `filter_alarms_by` / events / logs / trends **no** inyectan el área del nodo. `area` es parámetro opcional. El write de `AlarmSummary` sigue sellando `area`. Catálogo historiador: `GET /api/tags/catalog`. Nodos: `GET /api/system/nodes` | `core.py`, `utils/history_query.py`, resources Flask |
| HMI histórico | Por defecto **omite** `area` (consulta de planta). El selector parte en «Toda la planta» (`selectedArea=""`). Solo si el operador elige una línea se añade `area` al POST. Trends/datalogger usan `/tags/catalog`, no el CVT | `hmi/src/pages/{AlarmsSummary,Events,OperationalLogs,Trends,DataLogger}.tsx` |
| Máquinas | `MachinesLoggerEngine.create` acepta `area` (el arranque ya no hace KeyError al persistir la máquina) | `logger/machines.py` |
| Lookups | `get_alarm` / `get_alarm_by_name` admiten `None` (un miss no tira `TypeError` en el hot path de la SM) | `core.py` |
| Pruebas | `test_multi_edge_*`: CA-EDGE-1..8, alias SEGMENT/MANUFACTURER, SITE residual, alarma `alarm.*.leak`, `AlarmSummary.area`, engine de máquinas. 2-edge live **opt-in**; soak 24 h **no ejecutado** | `automation/tests/` |
| Deploy iDetectFugas | `compose/.env` + `docker-compose.yml`: `NODE_ID=edge-linea1`, `SEGMENT=Linea1`, `MANUFACTURER=Test`. Sin `AREA`/`SITE` duplicados. Desarrollo local: `.env.local` + `wsgi.py` | repo aplicación |
| Docs de producto | `docs/multi-edge.md` describe alias y el contrato de nombres. `specs/01-MULTI-EDGE-ARCHITECTURE.md` **sigue** diciendo «propuesta no implementado». `idetectfugas/docs/DESPLIEGUE.md` **aún** documenta `SEGMENT` sin `NODE_ID` | NUC-16 abierto |

### 2.2 Contratos de comportamiento que hay que preservar

- Multi-edge on + sin `NODE_ID` o sin área (`AREA`/`SEGMENT`) → `acquisition_ready=False`; no hidratar runtime; no `read_all()` de tags/OPC.
- `AREA` y `SEGMENT` definidos y distintos → fail-closed (`identity_conflict`). No «elegir uno en silencio».
- `SITE` y `MANUFACTURER` distintos → **no** fail-closed. Gana `MANUFACTURER`. `blocked_reason` no debe decir «missing NODE_ID/AREA» si el fallo es otro.
- Un solo writer por tag: coinciden **área y nodo** (`owns_tag` no hace fallback a «misma área, otro nodo»).
- Inconsistencia `area`/`owner_node` en catálogo: **skip + evento crítico**, nunca corrección silenciosa.
- El frontend **no** es frontera de seguridad; la API sí.
- Tags creados por API/HMI: nombre cualificado con el área. Tags internos de máquina: contrato de la aplicación, sello de ownership en el objeto Tag.
- Alarmas de aplicación: ownership = tag asociado. No exigir `name.startswith(area.)`.
- Histórico (`alarms/summary`, events, logs, trends, datalogger): **sin** filtro de área por defecto. Si el cliente envía `area`, se restringe. El write de `AlarmSummary` sigue sellando esa columna.
- HMI de esas pantallas: **no rellena `area` al cargar.** `selectedArea` nace `""`; el payload solo incluye `area` si el operador elige una línea. Eso es consulta global, no «área del nodo en silencio».
- Runtime (CVT, alarmas activas, CRUD, Socket.IO `on.tag`/`on.alarm`, `GET /tags`, `/tags/list`): sigue particionado. El banner `on_connection` de last_alarms/events/logs usa el área local.

### 2.3 Gérmenes que ya no son el mecanismo

`AUTOMATION_SEGMENT` / `AUTOMATION_MANUFACTURER` son los nombres que ya usa iDetectFugas. PyAutomation los trata como alias de `AREA` / `SITE` (mismas columnas internas). **No hay que duplicar variables.** En el compose de iDetectFugas basta `NODE_ID` + `SEGMENT` + `MANUFACTURER`.

### 2.4 Hallazgos de laboratorio (iDetectFugas, 1 edge, 2026-08-18)

Evidencia contra proceso real (`./docker-entrypoint.sh`, venv con copia de `automation/`, PG compartido). No sustituye NUC-7.

| Síntoma | Causa en código | Estado |
|---|---|---|
| Arranque: `MachinesLoggerEngine.create() got an unexpected keyword argument 'area'` | El logger aceptaba `area`; el engine no | **Cerrado** — `logger/machines.py` |
| Hidratar alarmas: `KeyError: 'area'` en `create_alarm(reload=True, **alarm)` | `@validate_types` no declaraba `area` | **Cerrado** — `core.create_alarm` |
| Mensaje genérico «missing NODE_ID/AREA» con esas vars definidas | `SITE` residual ≠ `MANUFACTURER` se trataba como conflicto de identidad | **Cerrado** — mismatch de sitio no fail-close; `blocked_reason` es específico |
| Fuga disparada, HMI sin alarma; log `get_alarm_by_name` → `NoneType` | `create_alarm` exigía `Linea1.` y iDetectFugas usa `alarm.{máquina}.leak`; `validate_types(output=Alarm)` no admitía `None` | **Cerrado** — frontera = tag; lookup admite `None` |
| Log inundado `[ERROR] …` 1 Hz | `validate_types` hacía `print` además de `logger.error`; el `print` bypasea `DedupeFilter` | **Cerrado** — ver `AUDIT_LOGGING.md` LOG-M3 |
| Trends/Events cargan; `alarms/summary` vacío | `AlarmSummary` se persistía con `area` NULL; el GET inyectaba `area=Linea1` | **Cerrado** — sello en write + backfill; **Fase 2:** el GET ya no inyecta área (lectura de planta) |
| `Cannot get geospatial from KP` al pasar a leaking | KP estimado fuera de la tabla de referenciación lineal de `Linea1` | **Abierto** (dato de planta, no partición) |
| `0 tags found for state machine Test.Linea1.LDS` | `TagsMachines` vacío; los tags internos se hidratan por otro loader | **Esperado** |
| `SSLEOFError` al recargar HMI / reiniciar engines | El cliente cierra TLS a media respuesta | **Mitigado** (silencio en gunicorn/gevent; no es fallo de app) |

El venv de iDetectFugas **no** es editable: un fix en `github/PyAutomation` no vive en el proceso hasta copiar/reinstalar el wheel. Docker usa `dist/PyAutomationIO-2.8.1-…whl` hasta rebuild.

---

## 3. Qué ocurriría en el escenario del cliente (post-Fase 1)

Supuesto: Edge A `NODE_ID=edge-linea1` `SEGMENT=Linea1`, Edge B `NODE_ID=edge-linea2` `SEGMENT=Linea2`, misma BD, OPC A y OPC B en redes distintas, catálogo con `area`/`owner_node` poblados, wheel PyAutomationIO que incluye esta iteración. En laboratorio **solo se corrió A**.

| Evento | Comportamiento esperado ahora | Residual |
|---|---|---|
| Arranque A | Hidrata solo runtime de Linea1; no instancia el cliente OPC de B | Si el cliente de B quedó con `owner_node` NULL, A **no** lo carga (omitido). Hay que provisionar bien el catálogo |
| CVT A | Solo tags owned; prune en reconnect | Contaminación solo si un bug salta `owns_tag` o se desactiva multi-edge |
| Persistencia | Journal A namespaced; enqueue/replicación de tags de B rechazados | No hay alarma de planta tipo «intento de doble escritor» hacia SIEM/consola |
| Reinicio de A | Scoped hydrate + prune. Laboratorio 1-edge: alarmas `alarm.Test.Linea1.*.leak` hidratan | No hay soak 24 h ni segundo edge |
| Apagón de A, B sigue | B no toma la línea A (correcto). Puntos de A quedan *stale* | La consola central **aún no** existe |
| Homólogos `FI_01` | Coexisten como `Linea1.FI_01` y `Linea2.FI_01` (API) | Unique sigue **global**. Sin cualificar, el segundo `create_tag` falla |
| Alarmas de fuga | Nombre `alarm.{MANUFACTURER}.{SEGMENT}.{máquina}.leak`; ownership por el tag interno | Unique `Alarms.name` sigue global; dos líneas con el mismo manufacturer+machine chocan |
| `alarms/summary` (y events/logs/trends/datalogger) | El HMI de A **no envía** `area` al abrir: ve filas de toda la planta. El selector puede acotar a Linea1 o Linea2 | Filas históricas NULL en TagValue/Events/Logs no se infieren; `AlarmSummary` NULL se rellena **solo** si `Alarms.area` ya está |
| Usuarios | Compartidos (plano planta) | Sin RLS: un cliente SQL con el mismo rol **puede** leer/escribir filas de otra área |
| Health | `ACQUISITION_READY` y `NODE_*` visibles | El `healthcheck` Docker de iDetectFugas **no** exige `ACQUISITION_READY` |

**Conclusión de escenario:** el aislamiento de **aplicación** está. El aislamiento de **planta** (red, BD, tiempo, operación 24/7, evidencia 2-edge) no.

---

## 4. Invariantes de diseño — estado

| ID | Invariante | Estado Fase 1 | Hueco |
|---|---|---|---|
| **INV-N1** | `node_id` estable (no hostname efímero) | **Cubierto** (env + `Nodes`) | No hay enforcement operativo de «no usar hostname Docker» más allá de documentación |
| **INV-N2** | Un `area` ISA-95 por instancia | **Cubierto** (`SEGMENT` basta; `AREA` es alias; conflicto si ambos difieren) | No declarar `AREA` y `SEGMENT` a la vez. Un `SITE` residual ya no bloquea |
| **INV-N3** | Fail-closed: sin identidad no hidratar todo | **Cubierto** (HMI up, adquisición down) | Healthcheck de contenedor no falla si adquisición está bloqueada |
| **INV-N4** | Un `owner_node` por tag (single-writer) | **Cubierto** en CVT/API/SAF | Unique `(area, name)` **no** está; el prefijo es obligatorio **solo** en `create_tag` de API |
| **INV-N5** | OPC: solo `connect()` a clientes propios | **Cubierto** | Binding certificado OPC ↔ `owner_node` no existe |
| **INV-N6** | CVT solo partición propia (+ sistema del nodo) | **Cubierto** (hydrate + prune) | Evidencia 1-edge en lab; no soak 2-edge |
| **INV-N7** | Máquinas por área | **Parcial** (`area` en create/engine; hydrate scoped) | Unique `Machines.name` sigue global; iDetectFugas prefija `{MANUFACTURER}.{SEGMENT}.LDS` |
| **INV-N8** | SAF solo encola owned | **Cubierto** | Journal en volumen compartido entre dos contenedores sería accidente de deploy |
| **INV-N9** | No dos edges al mismo `nodeId` OPC | **Cubierto** en software | VLAN/firewall sigue siendo deber de OT, no del código |
| **INV-N10** | Plant catalog vs area runtime | **Cubierto** en loaders | Import aún trae catálogos globales (variables/unidades) sin firma |
| **INV-N11** | Heartbeat `last_seen`; **no** robar I/O | **Parcial** (`last_seen` se actualiza) | No hay UI/consola «nodo ausente / stale». No hay lease de propiedad |
| **INV-N12** | `application_name` con `node_id` | **Cubierto** | Hay que verificar en `pg_stat_activity` de planta, no solo en unitarias |

SOLID (sigue vigente para el backlog):

| Principio | Cómo se aplicó | Qué falta |
|---|---|---|
| SRP | `NodeScope` concentra identidad | Provisioner de catálogo (quién asigna `owner_node`) no es un servicio |
| OCP | Nueva línea = nuevo env, sin `if linea == 3` | Receta N-edge de producto (compose por línea) no está industrializada en iDetectFugas más allá de Linea1 |
| LSP | Historiador intacto; cambia el filtro | Unique global rompe el LSP de «mismo tag local, distinta área» sin prefijo |
| ISP | Users globales vs runtime de área; lecturas históricas de planta | Consola de **proceso en vivo** de otros edges y heartbeat de peers no existen |
| DIP | Loaders usan `scoped()` / `owns_*` | No hay `ICatalogPartition` inyectable para tests de propiedad formales |

---

## 5. Qué queda **fuera** de esta iteración (tenerlo presente)

Esta sección es el contrato de deuda. Nada de lo siguiente está «casi hecho»: o es decisión explícita de fase, o es requisito de **grado nuclear / clase mundial** que no se cierra con más unitarias.

### 5.1 Decisiones de alcance (no negociar como bugs de Fase 1)

| Ítem | Por qué se dejó fuera | Riesgo si se ignora en planta |
|---|---|---|
| **RLS PostgreSQL** (`SET pyautomation.area` + policies) | Defensa de último recurso; el filtro de aplicación es Fase 1 | Un leak de credenciales o un script Peewee mal acotado lee/escribe **toda** la planta |
| **Backfill / migración de BD poblada** | No inferir dueños históricos. La copia `AlarmSummary.area ← Alarms.area` **no** es migración de planta | Activar multi-edge sobre BD vieja **omite** TagValue/Events/Logs con `area` NULL: la línea «desaparece» o el summary queda a medias si la definición tampoco tiene área |
| **Unique compuesto `(area, name)` / `(area, display_name)`** | Compatibilidad: unique global + namespacing | Un operador crea `FI_01` sin prefijo y tumba el segundo edge; el display HMI queda cualificado de forma rígida |
| **Consola central / heartbeat de nodos** | Las pantallas **históricas** del HMI embebido ya son vista de planta (sin `area` por defecto). Sigue faltando consola de **proceso en vivo** de otros edges y heartbeat «nodo ausente» | Sala de control ve el pasado de toda la planta desde cualquier edge; el CVT/alarmas activas siguen siendo locales |
| **Heartbeat avanzado / «nodo ausente»** | `last_seen` existe; no hay producto alrededor | El operador no distingue *stale* de *cero*. Tentación de «pasar la línea al otro edge» |
| **Failover automático de I/O** | **Fuera de alcance permanente** | Split-brain. Inventar valores. Incidente de seguridad de proceso |
| **Soak 24 h + IT 2-edge real** | Runbook escrito; harness opt-in vacío de evidencia | Entregar a planta sin prueba de no-go (escritura cruzada, PENDING creciente, OPC ajeno) |

### 5.2 Defensas de profundidad que un auditor NRC / ISA-95 pedirá

No son «nice to have». Son la diferencia entre *colector particionado en software* y *sistema de adquisición de misión crítica*.

| ID | Deuda | Por qué es nuclear-grade | Siguiente fase sugerida |
|---|---|---|---|
| **NUC-1** | **Tiempo.** Sin PTP/NTP auditado ni detección de reloj saltado entre edges | TagValue de dos líneas no es comparable; un salto de reloj rompe unique `(tag, timestamp)` y forenses | Fase 2 ops: fuente de tiempo, alarma `ALM.NODE.ClockSkew`, política de rechazo de samples con timestamp futuro/pasado fuera de ventana |
| **NUC-2** | **Red OT.** El código asume VLAN por línea; no la verifica | Si hay ruteo, un bug o un cliente mal provisionado **puede** alcanzar el OPC ajeno a nivel TCP | Matriz owner × endpoint + probe de «este OPC no debe ser reachable»; documentar zonificación IEC 62443 |
| **NUC-3** | **RLS + rol por nodo** | Defensa cuando la aplicación miente o hay consola SQL | `FORCE ROW LEVEL SECURITY` en Tags/TagValue/OPCUA/Alarms; `current_setting('pya.area')` |
| **NUC-4** | **Catálogo firmado / provisioner** | Hoy cualquier admin local importa JSON; un import de otra área se rechaza, pero el catálogo global (unidades, users) no está firmado | Rol provisioner; firma del export; prohibir mutar `owner_node` desde el edge salvo self |
| **NUC-5** | **Unique `(area, name)`** | Namespacing es disciplina humana. En nuclear no se confía en convenciones | Migración de unique; CVT indexa nombre **dentro del área**; display_name local `FI_01` |
| **NUC-6** | **Alarma de doble escritor / corrupción de catálogo hacia operación** | SAF descarta y loguea; no hay ISA-18.2 persistente tipo `ALM.NODE.ForeignWrite` / `UnscopedCatalog` visible en HMI de planta | Alarmas de sistema por nodo, ack obligatorio, reporte a Events con criticidad alta |
| **NUC-7** | **Evidencia de planta (CA-EDGE live + soak)** | Unitarias no sustituyen dos OPC, reboot, corte de red y 24 h | Harness `AUTOMATION_TWO_EDGE_IT=1` con artefactos; No-Go documentado firmado por operaciones |
| **NUC-8** | **Observabilidad L3** | Health local existe; no hay métricas de intentos 403, discards SAF, prune count, `last_seen` de peers | Prometheus/OpenTelemetry: `cvt_foreign_write_rejected_total`, `saf_foreign_discard_total`, `node_last_seen_seconds` |
| **NUC-9** | **Identidad de canal OPC UA** | `owner_node` es un string de configuración | Certificado de cliente OPC ligado al `NODE_ID`; rechazo si el endpoint no está en allowlist del nodo |
| **NUC-10** | **Lease de propiedad (sin robo)** | `last_seen` no impide que un humano cambie `owner_node` en caliente y cree dos escritores | Lease + quorum humano (two-person rule) para reasignar un tag; nunca automático |
| **NUC-11** | **Healthcheck de deploy = adquisición lista** | Compose hoy solo prueba HTTP | Fallar el contenedor (o un probe aparte) si `ACQUISITION_READY=false` en planta; en laboratorio puede ser warning |
| **NUC-12** | **Migración de plantas existentes** | Filas NULL se omiten | Playbook de backfill **explícito** (nunca inferido): mapa línea→nodo revisado por ingeniería; ventana de corte; rollback |
| **NUC-13** | **Máquinas / alarmas unique por área** | Prefijos de máquina en iDetectFugas; unique global; alarmas de app ya **no** usan prefijo de área | `(area, name)` en Machines y Alarms; bindings TagsMachines validados en BD |
| **NUC-14** | **Pista de auditoría inmutable** | Events/Logs llevan `area`; no hay WORM / append-only / hash chain | Retención + integridad (hash del lote SAF, firma del nodo) para forense post-incidente |
| **NUC-15** | **Pruebas de propiedad formales** | Microbench `set_value` < 0,25 ms/call; no hay pruebas de modelo (TLA+/QuickCheck) del invariante single-writer | Property-based: ∀ write, owner∈{self} ∨ no-mutación; ∀ hydrate, CVT ⊆ area |
| **NUC-16** | **Documentación de producto / spec** | `docs/multi-edge.md` y `compose/.env` iDetectFugas actualizados; laboratorio 1-edge documentado en §2.4 | `specs/01-MULTI-EDGE-ARCHITECTURE.md` sigue diciendo «propuesta no implementado»; `DESPLIEGUE.md` de iDetectFugas no lista `NODE_ID` |
| **NUC-17** | **Secretos y blast radius** | Mismo usuario PG para todos los edges | Credencial por nodo o mismo user + RLS; rotación; no compartir `./temp/db` entre contenedores |
| **NUC-18** | **Determinismo de journal ante crash** | Contratos SAF existentes (idempotencia, circuit breaker) | Ensayo de kill -9 / disco lleno / UID 65532 en distroless **por nodo**; no solo el journal legado |

### 5.3 Lo que **nunca** debe entrar en el backlog como «feature»

- Kubernetes autoscaling de PyAutomation (réplicas intercambiables).
- Un edge que «rescata» el OPC de otro porque `last_seen` envejeció.
- Cache del CVT ajeno «solo lectura» en el HMI local (eso es consola L3, no edge).
- Inferir `owner_node` desde `SEGMENT` o desde el prefijo del nombre en datos históricos.

---

## 6. Plan de fases (actualizado)

| Fase | Entrega | Estado |
|---|---|---|
| **0** | Documento + decisión `NODE_ID` / área (`AREA` o `SEGMENT`) | **Hecho** (esta auditoría + spec 01 + plan de implementación) |
| **1** | Identidad, columnas, hydrate, fail-closed, single-writer, SAF, API, CA-EDGE en tests | **Hecho en código** (2026-08-18). Laboratorio 1-edge iDetectFugas **hecho** (identidad + fugas + summary). Soak/IT 2-edge **pendiente** |
| **2** | Lecturas históricas de planta + HMI global por defecto; alarmas/máquinas de sistema por nodo; `ALM.NODE.*`; healthcheck de adquisición; compose N-edge | **Parcial (2026-08-18):** histórico API/HMI de planta (sin `area` al abrir). Falta `ALM.NODE.*`, healthcheck de adquisición, receta N-edge, evidencia 2-edge |
| **3** | Unique `(area, name)` / `(area, display_name)`; CVT scoped por área sin prefijo obligatorio | Pendiente |
| **4** | Heartbeat operativo + consola «nodo ausente»; RLS; rol/credencial por nodo | Pendiente |
| **5** | Receta N líneas industrializada; soak firmado; NUC-1..NUC-18 en umbral acordado con producto | Pendiente |

Fuera de alcance **permanente:** HA activo-activo del **mismo** OPC; mover una línea a otro edge sin cambio de red; autoscaling de PyAutomation.

---

## 7. Criterios de aceptación

| ID | Criterio | Evidencia Fase 1 | Gate que falta |
|---|---|---|---|
| **CA-EDGE-1** | Tras reboot, CVT sin tags de otra área | Unitaria `test_ca_edge_1_*` + prune reconnect | Reboot de contenedor real contra PG compartido |
| **CA-EDGE-2** | No abre sesión OPC UA ajena | `test_opc_client_never_connects_for_foreign_owner` | Dos servidores OPC; tcpdump / `is_opened` |
| **CA-EDGE-3** | Samples trazables (`application_name` / `owner_node`) | Unitaria de `historian_application_name` | `pg_stat_activity` + filas TagValue en planta |
| **CA-EDGE-4** | Caída de A: B sigue; B no escribe tags de A | Journals aislados + rechazo enqueue | Kill de A en laboratorio 2-edge |
| **CA-EDGE-5** | Sin `NODE_ID`: no `read_all()` tags/OPC | Fail-closed + `test_ca_edge_5_*` | Arranque de imagen iDetectFugas sin env (HMI up, `ACQUISITION_READY=false`) |
| **CA-EDGE-6** | Homólogos cualificados coexisten | `Linea1.FI_01` / `Linea2.FI_01` en unitaria; alarmas de app **no** usan ese prefijo | Unique compuesto (Fase 3); dos líneas reales con `alarm.Test.Linea*.LDS.leak` |
| **CA-EDGE-7** | Idle PG ≤ 4 por edge | Health `DB_CONNECTIONS_EXPECTED_MAX` | Censo real 2 edges × LoggerWorker |
| **CA-EDGE-8** | Runtime local no lista puntos ajenos; el histórico es de planta | API/Socket.IO de **proceso en vivo** acotados + 403; lecturas históricas globales; HMI omite `area` al abrir (`selectedArea=""`) | Operador en HMI real **2-edge**: CVT local vs resumen/trends de planta sin tocar el selector |

No-Go de producto (siguen vigentes, **ninguno cerrado en hardware**):

- Escritura cruzada en TagValue.
- Sesión OPC ajena.
- Crecimiento sostenido de `SAF_QUEUE_DEPTH` / `PENDING_ROWS`.
- Contaminación del **CVT / alarmas activas / listados de runtime** (tags, máquinas, OPC). Ver histórico de otra línea desde el HMI **no** es No-Go: es el contrato de planta.

---

## 8. Relación con conexiones y SAF

Multi-edge **no** sustituye el trabajo de reconexión ni el techo de sockets. Cada proceso sigue siendo un colector con 1 LoggerWorker. El SAF **por disco local y por `node_id`** es el patrón correcto de interface node: la línea no pierde muestras si el historiador central cae.

Lo que faltaba en el baseline era **pertenencia**. Eso ya está en el plano de aplicación.

Lo que falta para clase mundial es **pertenencia demostrable en planta más defensas que no confían en la aplicación**.

---

## 9. Conclusión

La premisa del cliente (un edge por línea, un OPC UA por línea, un historiador) es **estándar de planta**. PyAutomationIO ya no es un monolito de catálogo: es un **colector particionado con fail-closed, single-writer y SAF aislado**, verificable en suite dirigida y, en 1 edge, en iDetectFugas.

Eso **no** equivale a certificación de grado nuclear ni a «listo para N líneas». Un inspector mirará RLS, tiempo, zonificación de red, unique de datos, consola de nodo ausente, catálogo firmado, soak de 24 h **con dos edges** y la imposibilidad física de dos escritores. Esas piezas están listadas en **§5**.

**Regla de avance:** no abrir Fase 3 (unique compuesto) ni Fase 4 (RLS/consola) hasta tener **NUC-7** (evidencia 2-edge + soak) o un waiver firmado de operaciones. No desplegar dos instancias contra una BD **poblada sin backfill**. No implementar failover mágico de I/O. No volver a exigir prefijo de área en el **nombre** de alarmas de aplicación.

Cuando producto autorice la siguiente oleada, el orden de máximo retorno / mínimo split-brain es: **evidencia 2-edge → alarmas `ALM.NODE.*` + healthcheck de adquisición → unique `(area, name)` → RLS → consola stale.**
