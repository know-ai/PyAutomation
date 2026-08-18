# Auditoría: Adquisición multi-edge y partición por línea

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | N equipos edge, cada uno con una instancia de PyAutomation + un servidor OPC UA de línea, historiador PostgreSQL **compartido** |
| **Premisa de planta** | 2 secciones / líneas; ~20 puntos por línea (P, T, Q, ρ); persistencia en la misma BD; el cliente exige un edge por línea |
| **Fecha original** | 2026-08-18 (baseline: hidratación `read_all()`, sin identidad de nodo) |
| **Actualización** | 2026-08-18 (post-iteración Fase 1 / CA-EDGE-1..8 en código) |
| **Tipo** | Auditoría de contraste · arquitectura · nomenclatura industrial · backlog de grado nuclear |
| **Complementa** | `specs/01-MULTI-EDGE-ARCHITECTURE.md`, `docs/multi-edge.md`, `STORE_AND_FORWARD.md`, `PERSISTENCE_FLOW.md`, `AUDIT_DB_CONNECTIONS.md`, `AUDIT_OPTIMAL_CONNECTIONS.md` |
| **Veredicto** | **Fase 1 entregada en código.** Identidad, fail-closed, hidratación acotada, single-writer O(1), SAF aislado y API/HMI acotados existen y están cubiertos por pruebas unitarias/integración en proceso. **No es aún un producto de grado nuclear de clase mundial:** faltan unique compuesto, RLS, consola/heartbeat operativo, migración de BD poblada, soak 24 h con dos edges reales y varias defensas de profundidad (tiempo, red, catálogo firmado, evidencia de planta). |
| **Clasificación** | Confidencialidad interna · grado de diseño (ISA-95 / IEC 62264) |

---

## 0. Respuesta directa

| Pregunta | Respuesta (hoy) |
|---|---|
| ¿Esto es «escalado horizontal»? | **Solo en un sentido estrecho.** No es *scale-out* de un servicio stateless. Es **scale-out del piso de adquisición**: N nodos edge, cada uno dueño de una **partición de I/O**, escribiendo a un **historiador compartido** |
| Nombre industrial habitual | **Distributed / edge data acquisition**; ISA-95: nodos de **Área / Línea**; SCADA: **interface nodes / collectors**. Software: **shared-database partitioned writers** |
| ¿PyAutomation aísla una línea por instancia? | **Sí, en el plano de aplicación de esta iteración.** Loaders de runtime filtran por `area` / `owner_node`. Sin `NODE_ID`+`AREA` no hay `read_all()` de tags/OPC. El HMI/API siguen vivos (fail-closed de adquisición, no de presentación) |
| ¿El CVT de un edge persiste solo «su» línea? | El CVT es memoria de proceso y ahora **se poda** en reconnect. La persistencia sigue yendo al historiador global, con `area`/`owner_node` en el registro y rechazo de enqueue/replicación ajenos |
| ¿Al apagar y levantar un edge se mezcla la otra línea? | **No debe**, si la identidad está bien y el catálogo tiene `area`/`owner_node`. Filas históricas **nulas** no se infieren: se omiten (fail-closed de catálogo huérfano). Una BD poblada **sin backfill** no es un deploy válido de esta fase |
| ¿Se puede desplegar N edges contra la misma BD? | **Sí como receta de código**, con un contenedor por área, journals `./db/saf/<node_id>/` y `owner_node` en clientes OPC. **No** está cerrada la evidencia de planta (2 procesos + 2 OPC + soak 24 h) |

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

## 2. Estado tras esta iteración (Fase 1)

Contraste respecto al baseline de esta misma auditoría («hidratación `read_all()`, filtro SEGMENT/MANUFACTURER solo en parte del hot path»).

### 2.1 Entregado en código

| Superficie | Qué hay ahora | Dónde |
|---|---|---|
| Identidad | `NodeScope` inmutable; `AUTOMATION_MULTI_EDGE_ENABLED` **true por defecto**; `NODE_ID` y `AREA` obligatorios para adquisición | `automation/node_scope.py`, `automation/__init__.py`, `automation/core.py` |
| Fail-closed | Sin identidad: API/HMI/health vivos; **no** hidratar CVT/OPC ni arrancar workers de adquisición | `PyAutomation.connect_to_db` / `run` / `acquisition_ready` |
| Registro de nodo | Tabla `Nodes`; UPSERT idempotente; rechaza re-registrar el mismo `node_id` en otra `area`; `last_seen` en reconnect | `automation/dbmodels/nodes.py` |
| Esquema | `area` / `owner_node` en Tags, OPCUA, Machines, Alarms, TagValue, AlarmSummary, Events, Logs; índices simples y `(area, timestamp)` en histórico. **Sin backfill** | `ensure_schema()` idempotente |
| Hidratación | Tags/alarmas/máquinas por `area`; clientes OPC por `owner_node`; users/roles/catálogos globales compartidos | loaders en `core.py` |
| Reconnect | Diff + `_prune_runtime_scope()`: retira tags/observers/alarmas/OPC ajenos **sin** vaciar el CVT | `core.py` |
| Single-writer | `owns_tag()` O(1) en `set_value` / `set_value_fast`; DAS no suscribe namespace ajeno; OPC no `connect()` si `owner_node` ≠ local | `cvt.py`, `subscription.py`, `opcua_client.py` |
| SAF | Journal `./db/saf/<node_id>/journal.db`; observer/orquestador rechazan enqueue ajeno; replicator descarta PENDING extranjero | `persistence/` |
| Trazabilidad PG | `application_name=PyAutomationIO:<node_id>:<rol>` (≤ 63 chars, truncado determinista). Legacy `PyAutomationIO:<rol>` si multi-edge está off | `db_connections.py` |
| API / HMI | GET/Socket.IO acotados; POST/PUT/DELETE 403 recurso ajeno, 503 identidad ausente; import rechaza datos ajenos **antes** de mutar | `automation/modules/`, `export/import_configuration` |
| Health | `NODE_ID`, `NODE_AREA`, `NODE_SITE`, `MULTI_EDGE_ENABLED`, `ACQUISITION_READY`, `ACQUISITION_BLOCKED_REASON`, `SAF_QUEUE_DEPTH` | `/api/health/system` |
| Nombres | Namespacing obligatorio `Linea1.FI_01` (unique global intacto). Alarmas de sistema cualificadas (`Area-X.SYS.DB.Disconnected`) | `create_tag`, `connection_alarms` |
| Pruebas | Suites `test_multi_edge_*`; CA-EDGE-1..8 mapeados a unitarias; 2-edge live **opt-in**; soak 24 h **runbook**, no ejecutado en esta sesión | `automation/tests/`, `docs/multi-edge.md` |
| Deploy iDetectFugas | Identidad en `compose/.env` + passthrough en `docker-compose.yml` (`edge-linea1` / `Linea1`) | repo aplicación |

### 2.2 Contratos de comportamiento que hay que preservar

- Multi-edge on + sin `NODE_ID`/`AREA` → `acquisition_ready=False`; no hidratar runtime; no `read_all()` de tags/OPC.
- Un solo writer por tag: coinciden **área y nodo** (`owns_tag` no hace fallback a «misma área, otro nodo»).
- Inconsistencia `area`/`owner_node` en catálogo: **skip + evento crítico**, nunca corrección silenciosa.
- El frontend **no** es frontera de seguridad; la API sí.
- `AUTOMATION_SEGMENT` es fallback transitorio de `AREA`; no es la clave de partición.

### 2.3 Gérmenes que ya no son el mecanismo

`AUTOMATION_SEGMENT` / `AUTOMATION_MANUFACTURER` siguen existiendo (iDetectFugas los usa para LDS/geospatial). **No** son el filtro de hidratación ni el de escritura. El hot path de adquisición usa `NodeScope` / `owner_node`.

---

## 3. Qué ocurriría en el escenario del cliente (post-Fase 1)

Supuesto: Edge A `NODE_ID=edge-linea1` `AREA=Linea1`, Edge B `NODE_ID=edge-linea2` `AREA=Linea2`, misma BD, OPC A y OPC B en redes distintas, catálogo con `area`/`owner_node` poblados, wheel PyAutomationIO que incluye esta iteración.

| Evento | Comportamiento esperado ahora | Residual |
|---|---|---|
| Arranque A | Hidrata solo runtime de Linea1; no instancia el cliente OPC de B | Si el cliente de B quedó con `owner_node` NULL, A **no** lo carga (omitido). Hay que provisionar bien el catálogo |
| CVT A | Solo tags owned; prune en reconnect | Contaminación solo si un bug salta `owns_tag` o se desactiva multi-edge |
| Persistencia | Journal A namespaced; enqueue/replicación de tags de B rechazados | No hay alarma de planta tipo «intento de doble escritor» hacia SIEM/consola |
| Reinicio de A | Scoped hydrate + prune | No hay soak 24 h que lo demuestre en hardware real |
| Apagón de A, B sigue | B no toma la línea A (correcto). Puntos de A quedan *stale* | La consola central **aún no** existe; el operador no tiene «nodo ausente» de producto |
| Homólogos `FI_01` | Coexisten como `Linea1.FI_01` y `Linea2.FI_01` | Unique sigue siendo **global**. Sin cualificar, el segundo `create` falla |
| Usuarios | Compartidos (plano planta) | Sin RLS: un cliente SQL con el mismo rol **puede** leer/escribir filas de otra área |
| Health | `ACQUISITION_READY` y `NODE_*` visibles | El `healthcheck` Docker de iDetectFugas **no** exige `ACQUISITION_READY` |

**Conclusión de escenario:** el aislamiento de **aplicación** está. El aislamiento de **planta** (red, BD, tiempo, operación 24/7, evidencia) no.

---

## 4. Invariantes de diseño — estado

| ID | Invariante | Estado Fase 1 | Hueco |
|---|---|---|---|
| **INV-N1** | `node_id` estable (no hostname efímero) | **Cubierto** (env + `Nodes`) | No hay enforcement operativo de «no usar hostname Docker» más allá de documentación |
| **INV-N2** | Un `area` ISA-95 por instancia | **Cubierto** (`AREA` obligatorio; `SEGMENT` fallback) | iDetectFugas debe mantener `AREA == SEGMENT` a mano |
| **INV-N3** | Fail-closed: sin identidad no hidratar todo | **Cubierto** (HMI up, adquisición down) | Healthcheck de contenedor no falla si adquisición está bloqueada |
| **INV-N4** | Un `owner_node` por tag (single-writer) | **Cubierto** en CVT/API/SAF | Unique `(area, name)` **no** está; namespacing es convención + chequeo al crear |
| **INV-N5** | OPC: solo `connect()` a clientes propios | **Cubierto** | Binding certificado OPC ↔ `owner_node` no existe |
| **INV-N6** | CVT solo partición propia (+ sistema del nodo) | **Cubierto** (hydrate + prune) | Evidencia solo unitaria, no soak 2-edge |
| **INV-N7** | Máquinas por área | **Parcial** | Unique `Machines.name` sigue global; iDetectFugas ya prefija `{SEGMENT}.LDS` |
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
| ISP | Users globales vs runtime de área | APIs de historiador de planta (consola) no existen en este repo |
| DIP | Loaders usan `scoped()` / `owns_*` | No hay `ICatalogPartition` inyectable para tests de propiedad formales |

---

## 5. Qué queda **fuera** de esta iteración (tenerlo presente)

Esta sección es el contrato de deuda. Nada de lo siguiente está «casi hecho»: o es decisión explícita de fase, o es requisito de **grado nuclear / clase mundial** que no se cierra con más unitarias.

### 5.1 Decisiones de alcance (no negociar como bugs de Fase 1)

| Ítem | Por qué se dejó fuera | Riesgo si se ignora en planta |
|---|---|---|
| **RLS PostgreSQL** (`SET pyautomation.area` + policies) | Defensa de último recurso; el filtro de aplicación es Fase 1 | Un leak de credenciales o un script Peewee mal acotado lee/escribe **toda** la planta |
| **Backfill / migración de BD poblada** | No inferir dueños históricos | Activar multi-edge sobre BD vieja **omite** filas NULL: la línea «desaparece» del edge o queda a medias |
| **Unique compuesto `(area, name)` / `(area, display_name)`** | Compatibilidad: unique global + namespacing | Un operador crea `FI_01` sin prefijo y tumba el segundo edge; el display HMI queda cualificado de forma rígida |
| **Consola central / vista de planta** | HMI embebida es frontera local; historiador es la vista L3 | Operación de sala de control sigue dependiendo de N HMIs o de SQL ad hoc |
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
| **NUC-13** | **Máquinas / alarmas unique por área** | Prefijos en iDetectFugas; unique global en BD | `(area, name)` en Machines y Alarms; bindings TagsMachines validados en BD, no solo por prefijo |
| **NUC-14** | **Pista de auditoría inmutable** | Events/Logs llevan `area`; no hay WORM / append-only / hash chain | Retención + integridad (hash del lote SAF, firma del nodo) para forense post-incidente |
| **NUC-15** | **Pruebas de propiedad formales** | Microbench `set_value` < 0,25 ms/call; no hay pruebas de modelo (TLA+/QuickCheck) del invariante single-writer | Property-based: ∀ write, owner∈{self} ∨ no-mutación; ∀ hydrate, CVT ⊆ area |
| **NUC-16** | **Documentación de producto / spec** | `docs/multi-edge.md` y compose iDetectFugas actualizados | `specs/01-MULTI-EDGE-ARCHITECTURE.md` sigue diciendo «propuesta no implementado»; DESPLIEGUE.md de iDetectFugas no lista `NODE_ID` |
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
| **0** | Documento + decisión `NODE_ID` / `AREA` | **Hecho** (esta auditoría + spec 01 + plan de implementación) |
| **1** | Identidad, columnas, hydrate, fail-closed, single-writer, SAF, API, CA-EDGE en tests | **Hecho en código** (2026-08-18). Soak/IT 2-edge **pendiente de evidencia** |
| **2** | Alarmas/máquinas de sistema por nodo como producto; `ALM.NODE.*`; healthcheck de adquisición; compose N-edge | **Siguiente** (parcialmente germinado: nombres cualificados, `last_seen`) |
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
| **CA-EDGE-6** | Homólogos cualificados coexisten | `Linea1.FI_01` / `Linea2.FI_01` | Misma prueba con unique compuesto (Fase 3) |
| **CA-EDGE-7** | Idle PG ≤ 4 por edge | Health `DB_CONNECTIONS_EXPECTED_MAX` | Censo real 2 edges × LoggerWorker |
| **CA-EDGE-8** | HMI local no lista puntos ajenos | API/Socket.IO acotados + 403 | Operador en HMI real; consola L3 **aún no** cubre «sí ve ambas en historiador» |

No-Go de producto (siguen vigentes, **ninguno cerrado en hardware**):

- Escritura cruzada en TagValue.
- Sesión OPC ajena.
- Crecimiento sostenido de `SAF_QUEUE_DEPTH` / `PENDING_ROWS`.
- Contaminación de HMI/CVT.

---

## 8. Relación con conexiones y SAF

Multi-edge **no** sustituye el trabajo de reconexión ni el techo de sockets. Cada proceso sigue siendo un colector con 1 LoggerWorker. El SAF **por disco local y por `node_id`** es el patrón correcto de interface node: la línea no pierde muestras si el historiador central cae.

Lo que faltaba en el baseline era **pertenencia**. Eso ya está en el plano de aplicación.

Lo que falta para clase mundial es **pertenencia demostrable en planta más defensas que no confían en la aplicación**.

---

## 9. Conclusión

La premisa del cliente (un edge por línea, un OPC UA por línea, un historiador) es **estándar de planta**. PyAutomationIO ya no es un monolito de catálogo: es un **colector particionado con fail-closed, single-writer y SAF aislado**, verificable en suite dirigida.

Eso **no** equivale a certificación de grado nuclear. Un inspector mirará RLS, tiempo, zonificación de red, unique de datos, consola de nodo ausente, catálogo firmado, soak de 24 h y la imposibilidad física de dos escritores. Esas piezas están listadas en **§5** para no redescubrirlas en la siguiente iteración.

**Regla de avance:** no abrir Fase 3 (unique compuesto) ni Fase 4 (RLS/consola) hasta tener **NUC-7** (evidencia 2-edge + soak) o un waiver firmado de operaciones. No desplegar dos instancias contra una BD **poblada sin backfill**. No implementar failover mágico de I/O.

Cuando producto autorice la siguiente oleada, el orden de máximo retorno / mínimo split-brain es: **evidencia de planta → alarmas `ALM.NODE.*` + healthcheck de adquisición → unique `(area, name)` → RLS → consola stale.**
