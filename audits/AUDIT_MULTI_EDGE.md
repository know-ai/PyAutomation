# Auditoría: Adquisición multi-edge y partición por línea (¿escalado horizontal?)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Dos (N) equipos edge, cada uno con una instancia de PyAutomation + un servidor OPC UA de línea, historiador PostgreSQL **compartido** |
| **Premisa de planta** | 2 secciones / líneas; ~20 puntos por línea (P, T, Q, ρ); persistencia en la misma BD; el cliente exige un edge por línea |
| **Fecha** | 2026-08-18 |
| **Tipo** | Auditoría de arquitectura · **sin cambio de código** · estrategia y nomenclatura industrial |
| **Complementa** | `STORE_AND_FORWARD.md`, `PERSISTENCE_FLOW.md`, `AUDIT_DB_CONNECTIONS.md`, `AUDIT_OPTIMAL_CONNECTIONS.md` |
| **Veredicto** | **La funcionalidad no está diseñada.** Hay gérmenes (`AUTOMATION_SEGMENT` / `AUTOMATION_MANUFACTURER`) en el *hot path* de escritura, pero la **hidratación** carga **todo** el catálogo. Dos instancias sobre la misma BD **no** son un cluster de réplicas: son **colectores particionados**. Hoy, al reiniciar un edge, ese proceso carga tags, clientes OPC UA, alarmas y máquinas de **ambas** líneas |
| **Clasificación** | Confidencialidad interna · grado de diseño (ISA-95 / IEC 62264) |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Esto es «escalado horizontal»? | **Solo en un sentido estrecho.** No es *scale-out* de un servicio stateless detrás de un balanceador. Es **scale-out del piso de adquisición**: N nodos edge, cada uno dueño de un **partición de I/O**, escribiendo a un **historiador compartido** |
| Nombre industrial habitual | **Distributed / edge data acquisition**; en ISA-95: nodos de **Área / Línea**; en SCADA/historiadores: **interface nodes / collectors** (PI Interface, Ignition Edge, Wonderware Area). En software: **shared-database partitioned writers** |
| ¿PyAutomation aísla hoy una línea por instancia? | **No en el arranque.** `load_db_to_cvt`, `load_opcua_clients_from_db`, `load_db_to_alarm_manager` leen `Tags.read_all()` / `OPCUA.read_all()` / todas las alarmas |
| ¿El CVT de un edge persiste solo «su» línea? | El CVT es **memoria de proceso**. La persistencia va al historiador **global**. El filtro `SEGMENT`+`MANUFACTURER` solo aplica en algunos *callbacks* de OPC/DAQ **si ambas env están definidas**; no filtra la carga ni el catálogo |
| ¿Al apagar y levantar un edge se mezcla la otra línea? | **Sí.** El proceso vacío hidrata el catálogo completo. Intentará crear clientes OPC UA de la otra línea, meter sus tags en el CVT y (si el servidor es alcanzable) suscribirse |
| ¿Hay que programarlo ahora? | **No.** Esta auditoría fija el modelo, los invariantes y el plan. Implementar es una operación posterior (identidad de nodo + hidratación acotada + un solo escritor por tag) |

---

## 1. Cómo se llama esto (y cómo no)

### 1.1 Lo que **no** es

| Término | Por qué no aplica |
|---|---|
| Escalado horizontal clásico (web) | Réplicas **idénticas** e **intercambiables**. Cualquier réplica sirve cualquier request. Aquí cada edge **no** puede adquirir la línea del otro: el cable OPC UA es físico y local |
| Balanceo de carga (L4/L7) | No hay un pool de workers PyAutomation delante de un VIP para «repartir tags» |
| Sharding de base de datos | Sigue habiendo **un** historiador. Lo que se parte es la **adquisición**, no el almacenamiento |
| Multi-tenant SaaS | El cliente no pide dos empresas; pide dos **áreas de proceso** de la misma planta |

Llamar a esto «escalado horizontal» en un RFP o en un HAZOP confunde: un auditor pensará en N réplicas activas-activas del mismo servicio.

### 1.2 Nombre correcto (industria + software)

En **ISA-95 / IEC 62264** la jerarquía es Empresa → Sitio → **Área** → **Línea** → Unidad → Equipo. Cada edge es un nodo de **Nivel 2** (control/SCADA de línea) que publica hacia Nivel 3 (historiador / MES).

Nombres que sí comunican el diseño:

| Nombre | Uso |
|---|---|
| **Adquisición distribuida en el edge** | Conversación con el cliente / operaciones |
| **Colectores particionados por línea (partitioned collectors)** | Arquitectura de software |
| **Nodo de interfaz / interface node** | Historiadores (analogía PI, eDNA, Ignition Edge) |
| **Área ISA-95 como clave de partición** | Modelo de datos |
| **Single-writer per tag** | Invariante de consistencia (un tag, un dueño de escritura) |
| **Scale-out del tier de I/O** | Si hace falta la palabra *scale*: se escala la **captura**, no el proceso monolítico |

Principio nuclear: **un punto de proceso tiene un y solo un escritor de tiempo real.** El historiador es el bus de verdad para el pasado; el CVT es la verdad **local** del edge que posee esos tags.

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

## 2. Cómo PyAutomation reparte hoy el trabajo de adquisición

### 2.1 Un proceso, un CVT, un DAS

Dentro de **una** instancia:

1. El **cliente OPC UA** (tabla `opcua`) se conecta al servidor local de la línea.
2. **DAS** (suscripciones) o la máquina **DAQ** (lectura cíclica) copian el valor al **CVT** (tabla en RAM, `Singleton` por proceso).
3. Observers del tag encolan en el **journal SAF local** (`db/saf/journal.db`).
4. **LoggerWorker** replica PENDING al PostgreSQL remoto.

Eso es **adquisición vertical en un solo host**. No hay réplica del CVT entre procesos. No hay consenso. No hay «quién es el líder de FI_01».

El CVT **no sabe** qué línea es. Es un diccionario `nombre → Tag` en ese proceso.

### 2.2 Gérmenes de partición (insuficientes)

| Pieza | Qué hace | Qué no hace |
|---|---|---|
| `AUTOMATION_SEGMENT` / `AUTOMATION_MANUFACTURER` (`automation/__init__.py`) | Env de proceso | No es identidad de nodo; no se valida al boot |
| `Tags.segment` / `Tags.manufacturer` | FK en catálogo | `name` y `display_name` siguen **unique globales** |
| DAS / DAQ / LoggerWorker `get_tags_from_queue` | Si **ambas** env están set, solo `set_value` / encola tags cuyo `tag.segment` y `tag.manufacturer` coinciden | Si **faltan** las env, el filtro se **desactiva** (`elif not MANUFACTURER and not SEGMENT`) y se acepta todo |
| `GET` tags con `manufacturer`/`segment` | Filtro opcional de **consulta** HMI sobre el CVT ya cargado | No evita haber hidratado el mundo |
| SAF por disco local | Cada edge tiene su journal | Replica **cualquier** tag que haya encolado ese proceso (si el CVT tiene la línea ajena, puede intentar persistirla) |

### 2.3 Hidratación: el hueco

Tras `connect_to_db` / `reconnect_to_db`, `_hydrate_runtime_from_db` ejecuta, **sin filtro de nodo**:

| Método | Fuente | Efecto en 2 edges |
|---|---|---|
| `load_opcua_clients_from_db` | `OPCUA.read_all()` | Edge A instancia **todos** los clientes, incluido el de la línea B |
| `load_db_to_cvt` | `Tags.read_all()` → `create_tag(reload=True)` | El CVT de A contiene tags de B (valores muertos o, peor, suscritos si el OPC B es alcanzable) |
| `load_db_to_alarm_manager` | todas las alarmas | Alarmas de la otra línea en RAM; transiciones espurias |
| `load_db_to_roles` / `users` | catálogo global | Aceptable **si** el directorio de usuarios es de planta (compartido) |
| `load_db_tags_to_machine` | `Machines` por **nombre** | Choque si ambas líneas despliegan `LDS`, `PPA`, `NPW` (nombre unique global) |

`OPCUA.client_name` es unique. No hay columna `owner_node` / `area` / `segment` en el cliente OPC.

LoggerWorker, si `_clients` está vacío, vuelve a `load_opcua_clients_from_db()` — otra vez **todo**.

### 2.4 Invariantes de esquema que impiden dos líneas «iguales»

| Recurso | Unique hoy | Consecuencia |
|---|---|---|
| Tag `name`, `display_name`, `identifier` | Global | No pueden existir dos `FI_01` (una por línea) salvo prefijar a mano (`Linea1.FI_01`) |
| Cliente OPC `client_name` | Global | Un nombre, un registro; ambos edges lo cargan |
| Máquina `name` | Global | Un solo `LDS` en BD; el segundo edge reutiliza/ confunde la misma fila |
| Alarma `name` | Global | `alarm.LDS.leak` no se puede duplicar por línea |
| `TagValue (tag, timestamp)` | Unique | Exact-once **por tag**; no distingue escritor. Si dos edges escriben el mismo tag, el segundo `ON CONFLICT` se pierde (SAF) — silencio, no alarma de doble escritor |

### 2.5 Lo que **sí** está a favor de multi-edge

| Pieza | Por qué ayuda |
|---|---|
| SAF local por host | Cada línea aguanta outage de BD sin compartir journal |
| Un escritor Peewee por proceso (LoggerWorker) | El censo de conexiones **por edge** sigue siendo 1–3 idle |
| Exact-once en TagValue | Evita duplicar muestras **si** cada tag tiene un solo dueño |
| HMI / Socket.IO por proceso | El operador en el edge A ve el CVT de **ese** proceso (hoy contaminado por hidratación total) |
| Consola central (`iDetectFugas-console`) | Sitio natural de **vista de planta** leyendo el historiador, no el CVT de un edge |

---

## 3. Qué ocurriría en el escenario del cliente (as-is)

Supuesto: Edge A `SEGMENT=Linea1`, Edge B `SEGMENT=Linea2`, misma BD, OPC A = `192.168.1.81:4840`, OPC B = otro host.

| Evento | Comportamiento actual |
|---|---|
| Arranque A | Carga clientes A **y** B. Intenta TCP al OPC de B (timeout, alarma `ALM.OPCUA.*` ajena, o conexión cruzada si hay ruteo) |
| Arranque B | Simétrico |
| CVT A | Tags de ambas líneas en RAM. Escritura DAS solo a tags con segment=Linea1 **si** ambas env están set |
| Persistencia | A replica samples de tags que **él** actualizó. Tags de B en el CVT de A quedan congelados y pueden confundir HMI/alarmas locales |
| Reinicio de A | Otra vez `read_all()`. No hay «no cargar la línea B» |
| Apagón de A, B sigue | B no «toma» la línea A (tampoco debe). Los puntos de A dejan de escribirse. Correcto físicamente; no hay failover de I/O (el OPC A no está en B) |
| Nombres `FI_01` en ambas líneas | El segundo `Tags.create` falla por unique. Hay que namespacing **hoy** a mano, sin garantía de que el hydrate lo respete |
| Usuarios | Ambos edges ven los mismos users (razonable para planta) |
| `SYS.DB.Disconnected` | Tag/alarma globales; ambos procesos las hidratan y las disparan | 

**Conclusión de escenario:** el usuario tiene razón: **no se ha trabajado el aislamiento de instancia.** Lo que hay es un monolito de catálogo pensado para **un** PyAutomation por base de datos.

---

## 4. Invariantes de diseño (grado nuclear)

Antes de código, contratos. Si se viola uno, no hay «feature»: hay incidente.

| ID | Invariante | Verificación |
|---|---|---|
| **INV-N1** | Toda instancia tiene `node_id` estable (no el hostname efímero de Docker salvo que esté fijado) | Env + fila `nodes` en BD |
| **INV-N2** | Toda instancia declara **un** `area_id` / línea ISA-95 que posee | `AUTOMATION_AREA` o `AUTOMATION_SEGMENT` **obligatorio** en multi-edge |
| **INV-N3** | **Fail-closed:** si el modo es multi-nodo y falta identidad, **no** hidratar el catálogo completo | Boot aborta o queda en modo degradado local, nunca `read_all()` |
| **INV-N4** | Cada tag de proceso tiene **un** `owner_node` (single-writer) | Unique `(name, area)` o nombre cualificado; check al crear y al hidratar |
| **INV-N5** | Cada cliente OPC UA tiene `owner_node`; un edge solo `connect()` a los suyos | `load_opcua_clients_from_db` WHERE owner = me |
| **INV-N6** | El CVT de un proceso solo contiene tags de su partición (+ tags de sistema de **ese** nodo) | Tras hydrate, `cvt.tag_count()` = catálogo filtrado |
| **INV-N7** | Máquinas de aplicación (LDS, PPA, …) son **por área** o llevan sufijo de línea; no un `LDS` global | Unique `(name, area)` |
| **INV-N8** | El journal SAF solo encola tags cuyo owner es este nodo | Defensa en profundidad aunque el CVT esté limpio |
| **INV-N9** | Dos edges **no** se suscriben al mismo `nodeId` OPC | Matriz owner × endpoint |
| **INV-N10** | Usuarios/roles/unidades/tipos pueden ser **globales de planta**; la adquisición no | Separar *plant catalog* vs *area runtime* |
| **INV-N11** | Heartbeat de nodo en BD (`last_seen`) para operación; **no** para robar I/O automáticamente | Failover de OPC es decisión humana / de red, no split-brain |
| **INV-N12** | `application_name` libpq incluye `node_id` | Censo `pg_stat_activity` atribuible |

SOLID aplicado al futuro diseño:

| Principio | Cómo |
|---|---|
| SRP | Un servicio **NodeScope** (identidad + predicado SQL/ORM). Los loaders no «saben» de Docker |
| OCP | Nuevas líneas = nuevo nodo + área, sin if/else por nombre de planta en `core.py` |
| LSP | El historiador no cambia; cambia el **filtro de hidratación** |
| ISP | APIs de catálogo global (users) distintas de APIs de runtime de área (tags DAQ) |
| DIP | `ICatalogPartition.tags_for(node)` ; hydrate depende de la abstracción, no de `Tags.read_all()` |

---

## 5. Estrategia recomendada (sin implementar)

### 5.1 Identidad de nodo (prioridad 0)

Tres env, no una:

```
AUTOMATION_NODE_ID=edge-linea-1          # estable, único en la planta
AUTOMATION_AREA=Linea1                   # ISA-95 Area / línea (puede reutilizar SEGMENT)
AUTOMATION_SITE=PlantaNorte              # opcional, para N plantas
```

Persistir tabla `nodes (id, area, site, last_seen, version, hostname)`. El boot hace upsert del self. Sin `NODE_ID` en modo planta multi-edge: **no arrancar adquisición remota**.

`AUTOMATION_SEGMENT` hoy puede **mapearse** a `AREA` para no romper iDetectFugas (`Linea1` ya está en compose). No basta: hay que usarlo en **hydrate**, no solo en DAS.

### 5.2 Partición del catálogo

Modelo mental de dos planos:

| Plano | Contenido | Quién lo escribe | Quién lo lee al boot |
|---|---|---|---|
| **Plant catalog** | Users, roles, units, variables, tipos de alarma | Administración central | Todos los edges |
| **Area runtime** | Tags de proceso, clientes OPC, máquinas LDS/PPA, alarmas de proceso, bindings | El edge dueño (o un provisioner que asigna `owner_node`) | **Solo el dueño** |

Tags de sistema (`SYS.DB.Disconnected`, `SYS.OPCUA.<este_cliente>`) se **instancian por nodo** (`SYS.<node_id>.DB.Disconnected`) o se filtran por owner. No un único tag global disparado por dos procesos.

### 5.3 Nombres de tags

Opción A (mínima, compatible con unique actual): **nombre cualificado** `Linea1.FI_01`, `Linea2.FI_01`. El display_name puede ser `FI_01` por línea si se relaja unique de `display_name` a `(display_name, area)`.

Opción B (correcta a medio plazo): unique compuesto `(area_id, name)` y el CVT indexa `name` **dentro del área del nodo**. El historiador guarda `area` en cada serie.

La consola central agrupa por área. El edge nunca muestra la otra línea en su HMI local (su CVT no la tiene).

### 5.4 Hidratación acotada (el cambio de comportamiento)

Sustituir `read_all()` en el camino de boot/reconnect por consultas particionadas:

- Tags: `WHERE owner_node = me OR area = my_area`
- OPC UA clients: `WHERE owner_node = me`
- Alarms de proceso: vía tag dueño de este nodo
- Machines: `WHERE area = my_area` (o `owner_node`)
- Users/roles: sin filtro (plano planta)

Fail-closed: si el filtro devolvería «todo» porque `area` es NULL en filas viejas, **no cargar esas filas** y emitir alarma de configuración (`ALM.NODE.UnscopedCatalog`). Migración: backfill de `owner_node` antes de activar el modo.

### 5.5 Single-writer y anti split-brain

No implementar failover automático de la línea A hacia el edge B. El servidor OPC de A no está en B; «tomar» esos tags sería inventar datos.

Sí implementar:

- Rechazo al `create_tag` / `add_opcua_client` si `owner_node` ≠ self (salvo rol de provisioner).
- Al replicar SAF, si el tag.owner ≠ self, **no ACK remoto** y alarma (catálogo corrupto).
- Heartbeat visible en consola: edge A last_seen; si A muere, la consola muestra **stale**, no valores de B.

### 5.6 Historiador y conexiones

Dos edges × 1–3 conexiones idle = **2–6** backends `PyAutomationIO:<node_id>:<rol>`. Cabe en la política actual. No es un argumento contra multi-edge.

`application_name=PyAutomationIO:edge-linea-1:LoggerWorker`.

### 5.7 Vista de planta

| Superficie | Fuente de verdad |
|---|---|
| HMI embebida del edge | CVT **local** (solo su área) |
| Consola / sala de control | Historiador (ambas líneas, read-only) |
| Tendencias largas | `TagValue` ya persistido |

No hay que clonar el CVT entre edges. Eso sería cache distribuida sin líder: fuera de alcance y peligroso.

### 5.8 Seguridad

- Cada edge solo tiene ruta de red a **su** OPC UA (firewall / VLAN por línea). Aunque el hydrate se equivoque, el TCP a la otra línea debe fallar.
- Credenciales de BD: mismo historiador, mismo rol **o** rol por nodo con RLS (`WHERE area = current_setting('pya.area')`) como defensa de último recurso (PostgreSQL). RLS es fase 2; el filtro de aplicación es fase 1.
- Auditoría: eventos `node_id` en `Events` / `Logs`.

---

## 6. Plan de fases (cuando se autorice código)

| Fase | Entrega | Criterio |
|---|---|---|
| **0** | Documento (este) + decisión de nombres (`NODE_ID` / `AREA`) | Firmado por producto |
| **1** | Identidad + `owner_node` en tags y clientes OPC + hydrate filtrado + fail-closed | Soak 2 edges, misma BD: CVT A ∩ tags(B) = ∅; OPC A no lista el cliente de B |
| **2** | Máquinas y alarmas por área; tags de sistema por nodo | `LDS` de L1 y `LDS` de L2 coexisten |
| **3** | Unique compuesto o namespacing obligatorio; migración de `FI_01` | No se puede crear tag huérfano de área |
| **4** | Heartbeat + consola «nodo ausente»; RLS opcional | Operador ve stale, no datos cruzados |
| **5** | (Opcional) N líneas / N edges; misma receta | No aparece un `if linea == 3` |

Fuera de alcance explícito: HA activo-activo del **mismo** OPC; mover una línea a otro edge sin cambio de red; Kubernetes autoscaling de PyAutomation.

---

## 7. Criterios de aceptación (cuando se implemente)

| ID | Criterio |
|---|---|
| **CA-EDGE-1** | Edge A, tras reboot, CVT sin tags cuyo `area` ≠ Linea1 |
| **CA-EDGE-2** | Edge A no abre sesión OPC UA hacia el servidor de Linea2 |
| **CA-EDGE-3** | Samples de Linea1 en `TagValue` solo con `application_name` / owner de A (trazable) |
| **CA-EDGE-4** | Caída de A: B sigue; no aparecen escrituras de tags de A desde B |
| **CA-EDGE-5** | Arranque sin `NODE_ID` en modo multi-nodo: no `read_all()` de tags/OPC |
| **CA-EDGE-6** | Dos tags homólogos (`FI_01`) coexisten, uno por área |
| **CA-EDGE-7** | Conexiones PG idle por edge siguen ≤ 4; suma de edges lineal, no explosiva |
| **CA-EDGE-8** | HMI local de A no lista puntos de B; consola central sí (historiador) |

---

## 8. Relación con el «escalado» de conexiones y SAF

Multi-edge **no** sustituye el trabajo de reconexión ni el techo de sockets. Cada proceso sigue siendo un colector con 1 LoggerWorker. El SAF **por disco local** es exactamente el patrón correcto de interface node: la línea no pierde muestras si el historiador central cae.

Lo que falta no es más pooling ni más workers gunicorn. Falta **pertenencia**.

---

## 9. Conclusión

La premisa del cliente (un edge por línea, un OPC UA por línea, un historiador) es **estándar de planta**, no un experimento. En la industria no se vende como «Kubernetes horizontal»: se vende como **adquisición distribuida con historiador unificado** y **partición por área ISA-95**.

PyAutomation hoy es un **nodo único dueño de todo el catálogo**. Los env `SEGMENT`/`MANUFACTURER` son un filtro parcial de *runtime*, no un *scope* de *bootstrap*. Por eso, al levantar un edge, **sí** se mezclaría la otra línea.

La corrección de grado nuclear es aburrida y por eso es la correcta: **identidad de nodo, fail-closed, un escritor por tag, hidratación acotada, sin failover mágico de I/O.** Cuando producto autorice implementación, la Fase 1 cabe en ese contrato. Hasta entonces, no desplegar dos instancias contra la misma BD como si fueran réplicas.
