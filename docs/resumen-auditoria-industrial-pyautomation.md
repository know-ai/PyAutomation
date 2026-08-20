# PyAutomation — Documento de Resumen Técnico y Scope de Refactorización Industrial

**Versión analizada:** 2.1.3  
**Fecha:** Junio 2026  
**Objetivo:** Evaluar el estado actual de PyAutomation frente a los estándares de una plataforma SCADA/HMI de **clase mundial** para la industria de proceso (robusta, confiable, segura, rápida, fácil de instalar, interfaz industrial conforme a normas).

---

## 1. Resumen Ejecutivo

PyAutomation es una plataforma open-source de automatización industrial que integra adquisición de datos (OPC UA), tabla de valores en tiempo real (CVT), gestión de alarmas (ISA-18.2), registro histórico, máquinas de estado concurrentes y una HMI web basada en React. La arquitectura es modular en concepto pero concentra gran parte de la lógica en un núcleo monolítico (`core.py` ~5.000 líneas).

**Fortalezas actuales:** funcionalidad industrial básica completa, OPC UA cliente/servidor, alarmas con ciclo de vida, tendencias históricas y en tiempo real, bitácoras operativas, Docker, documentación extensa.

**Brecha principal:** el stack (Python/Flask/GIL + Socket.IO) y la arquitectura monolítica no alcanzan los requisitos de latencia determinista, escalabilidad edge, seguridad empresarial (LDAP/AD), testabilidad en entornos simulados y certificación industrial que exigen sistemas como Ignition, WinCC, AVEVA o PI System.

**Decisión estratégica v3.0:** la siguiente versión mayor se construirá sobre un stack industrial definido:

| Capa | Tecnología objetivo |
|---|---|
| **Backend / Runtime OT** | **Rust** (Tokio, gRPC, OPC UA nativo) |
| **HMI / SCADA** | **C#** (.NET 8 — WPF o Blazor Hybrid) |
| **Base de datos en tiempo real** | **TimescaleDB** o **InfluxDB** (ver §18.3) |
| **Comunicación** | **gRPC** (streaming) + mTLS |
| **Configuración / relacional** | PostgreSQL (si se elige InfluxDB para series) |

PyAutomation 2.x (Python/React) queda en modo mantenimiento; 3.x es una **reescritura dirigida**, no un parche incremental.

---

## 2. Stack Tecnológico

### 2.1 Backend

| Componente | Tecnología | Versión / Notas |
|---|---|---|
| Lenguaje | Python | 3.9 – 3.14 (Docker: 3.11) |
| Framework web | Flask + Flask-RESTX | 3.1.2 / 1.3.2 |
| Tiempo real (web) | Flask-SocketIO + gevent | 5.5.1, async_mode=`gevent` |
| Servidor WSGI | Gunicorn | 23.0.0 |
| ORM | Peewee | 3.18.3 |
| Bases de datos | SQLite, PostgreSQL, MySQL | PostgreSQL recomendado en producción |
| OPC UA | `opcua` (python-opcua) | 0.98.13 — librería legacy, no `asyncua` |
| Máquinas de estado | python-statemachine | 2.4.0 |
| Autenticación | Werkzeug hash + tokens en BD | PyJWT en requirements pero uso limitado |
| Criptografía | cryptography | 43.0.3 |
| Procesamiento numérico | NumPy, PyWavelets | Filtros y detección de anomalías |
| Contenedorización | Docker multi-stage + Supervisor + Nginx | Backend :8050, HMI :3000, OPC UA :53530 |

### 2.2 Frontend (HMI)

| Componente | Tecnología |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite 5 |
| Estado global | Redux Toolkit |
| UI | AdminLTE 4, Bootstrap 5 |
| Gráficos | Plotly.js + react-plotly.js |
| Tiempo real | socket.io-client 4.7 |
| HTTP | Axios |
| Layout SCADA | react-grid-layout (tendencias en tiempo real) |
| i18n | Locales ES/EN |

### 2.3 Infraestructura y despliegue

- **Docker Compose** con imagen `knowai/automation:latest`
- Volúmenes persistentes: `automation_db`, `automation_logs`
- Healthcheck vía `healthcheck.py`
- Límite de recursos por defecto: **0.5 CPU / 256 MB RAM** (insuficiente para planta)
- Variables de entorno para BD, secret key, superusuario, OPC UA

### 2.4 Stack actual vs. stack objetivo v3.0

| Criterio | v2.x (actual) | **v3.0 (objetivo)** |
|---|---|---|
| Backend de tiempo real | Python + GIL + threads | **Rust** — Tokio, sin GIL, binarios edge < 50 MB |
| API de proceso | REST + Socket.IO | **gRPC** (tonic) — streaming bidireccional |
| OPC UA | python-opcua 0.98 (deprecated) | **open62541** (FFI) o crate `opcua` / `async-opcua` en Rust |
| HMI operador | React 18 + Vite (web) | **C# .NET 8** — WPF (sala de control) o Blazor Hybrid |
| Series temporales | Peewee → TagValue en PostgreSQL/SQLite | **TimescaleDB** o **InfluxDB** |
| Config / usuarios / alarmas | Misma BD relacional | PostgreSQL (unificado con TimescaleDB) o PostgreSQL + InfluxDB |
| Edge | Monolito único | **Agentes Rust** desacoplados por área de planta |
| Autenticación | Local + RBAC básico | **LDAP / Active Directory** vía `System.DirectoryServices` + OIDC |

---

## 3. Arquitectura del Sistema

### 3.1 Capas

```
┌─────────────────────────────────────────────────────────┐
│  Presentación: React HMI · REST API · Socket.IO         │
├─────────────────────────────────────────────────────────┤
│  Aplicación: PyAutomation Core · AlarmManager · Workers │
│              State Machines · DataLogger · OPC UA Mgr   │
├─────────────────────────────────────────────────────────┤
│  Datos: CVT (memoria) · Peewee ORM · OPC UA Client/Srv  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Componentes núcleo

| Componente | Ubicación | Responsabilidad |
|---|---|---|
| `PyAutomation` | `automation/core.py` | Orquestación, API, Socket.IO, ciclo de vida (~5.069 líneas) |
| `CVTEngine` / `CVT` | `automation/tags/cvt.py` | Tabla de valores en memoria, thread-safe |
| `AlarmManager` | `automation/managers/alarms.py` | Definición, evaluación y ciclo de vida de alarmas |
| `DBManager` | `automation/managers/db.py` | Persistencia, cola de tags |
| `OPCUAClientManager` | `automation/managers/opcua_client.py` | Pool de clientes OPC UA, DAQ/DAS |
| `Machine` | `automation/state_machine.py` | Motor de máquinas de estado concurrentes |
| `DataLogger` / `DataLoggerEngine` | `automation/logger/datalogger.py` | Históricos TagValue |
| Workers | `automation/workers/` | LoggerWorker, AlarmWorker, StateMachine workers |
| Módulos REST | `automation/modules/` | Tags, Alarms, OPC UA, Users, Events, Database, Machines |

### 3.3 Módulos HMI (rutas)

| Ruta | Funcionalidad |
|---|---|
| `/communications/clients` | Gestión clientes OPC UA |
| `/communications/server` | Configuración servidor OPC UA embebido |
| `/tags/definitions` | CRUD de tags |
| `/tags/datalogger` | Consulta y exportación de históricos |
| `/tags/trends` | Tendencias históricas (Plotly) |
| `/real-time-trends` | Strip charts en tiempo real (Socket.IO) |
| `/alarms/definitions` | Configuración de alarmas |
| `/alarms/summary` | Resumen/historial de alarmas |
| `/events` | Eventos de sistema |
| `/operational-logs` | Bitácoras operativas |
| `/machines` | Máquinas de estado (PFM, Observer, DAQ, etc.) |
| `/user-management` | Usuarios y roles |
| `/database` | Configuración de BD |
| `/settings` | Ajustes de aplicación |

*Nota: SCADA y Performance están comentados en rutas — no activos en build actual.*

---

## 4. Patrones de Diseño y su Aplicación

### 4.1 Patrones implementados

| Patrón | Dónde se usa | Propósito |
|---|---|---|
| **Singleton** | `PyAutomation`, `CVTEngine`, `AlarmManager`, `DBManager`, `Machine`, `Users` | Una instancia global de recursos críticos |
| **Observer** | `Tag` → `TagObserver`, `MachineObserver`; CVT notifica a AlarmManager, DBManager, State Machines | Propagación de cambios de tags en tiempo real |
| **Worker-Engine** | `LoggerWorker` → `DataLoggerEngine`; workers de alarmas y state machines → engines thread-safe | Separar ejecución en hilos del acceso a datos |
| **State Machine** | `automation/state_machine.py` — DAQ, DAS, PFM, Observer, OPCUAServer | Lógica de adquisición y procesamiento por intervalo |
| **Repository** | `dbmodels/*` + engines | Abstracción de persistencia (parcial) |
| **Decorator** | `@set_event`, `@logging_error_handler`, `@db_rollback` | Eventos automáticos, logging, transacciones |
| **Queue** | `queue.Queue` en AlarmManager y DBManager | Desacoplar notificaciones de tags del procesamiento |

### 4.2 Patrones ausentes o débiles

- **Factory** documentado pero poco formalizado (creación de máquinas ad-hoc)
- **Dependency Injection** real (todo acoplado a singletons)
- **CQRS / Event Sourcing** para audit trail inmutable
- **Circuit Breaker / Retry** formal para OPC UA y BD
- **Hexagonal / Ports & Adapters** — el core conoce Flask, Socket.IO y Peewee directamente
- **Strangler Fig** para migración incremental — no existe plan en código

---

## 5. Funcionalidades Industriales

### 5.1 OPC UA — Cliente

**Ubicación:** `automation/managers/opcua_client.py`, `automation/opcua/`, `automation/modules/opcua/`

| Capacidad | Estado |
|---|---|
| Múltiples conexiones (pool) | ✅ |
| Discovery de servidores | ✅ |
| Modo DAQ (polling por `scan_time`) | ✅ — un hilo/state machine por tag o grupo |
| Modo DAS (suscripción) | ✅ — `DAS` subscription handler |
| Read/Write de nodos | ✅ |
| Browse de árbol de variables | ✅ con caché TTL 300s |
| Persistencia de clientes en BD | ✅ tabla `OPCUA` |
| Reconexión automática | ✅ parcial — LoggerWorker verifica conexiones |
| Certificados X.509 / seguridad OPC UA | ⚠️ Limitado |
| Modbus TCP / OPC DA | ❌ Planificado en roadmap |

**Deficiencias OPC UA Cliente:**
- Librería `opcua` 0.98.x no es mantenida activamente frente a `asyncua` o stacks nativos
- Sin soporte formal de redundant server pairs (OPC UA HA)
- Sin métricas de calidad de comunicación expuestas al HMI de forma estandarizada

### 5.2 OPC UA — Servidor

**Ubicación:** `automation/state_machine.py` (clase `OPCUAServer`), `automation/logger/opcua_server.py`, `automation/dbmodels/opcua_server.py`

| Capacidad | Estado |
|---|---|
| Servidor embebido exponiendo CVT | ✅ |
| Configuración de nodos (namespace, access type) | ✅ |
| Puerto configurable (default 53530) | ✅ |
| Integración con sistemas SCADA externos | ✅ vía OPC UA estándar |

**Deficiencias OPC UA Servidor:**
- No certificado contra profiles OPC UA (Nano, Micro, Standard)
- Sin address space dinámico tipado según companion specs (DI, ADI)
- Corre en el mismo proceso Python que el resto del sistema

### 5.3 Gestión de Tags (CVT)

**Ubicación:** `automation/tags/cvt.py`, `automation/tags/tag.py`, `automation/dbmodels/tags.py`

| Capacidad | Estado |
|---|---|
| CRUD de tags en memoria + BD | ✅ |
| Tipos: float, int, bool, str | ✅ |
| Unidades, variables, segmentos, fabricantes | ✅ |
| Deadband | ✅ |
| Filtro wavelet RT (`.f`) + calidad OPC | ✅ |
| Detección de anomalías: outlier, out-of-range, frozen data | ✅ |
| `scan_time` independiente por tag (state machine) | ✅ |
| Emisión Socket.IO `on.tag` | ✅ |
| Escritura a campo vía OPC UA | ✅ |

**Capacidad estimada:** miles de tags en documentación; sin benchmarks publicados ni pruebas de carga formales.

### 5.4 Gestión de Alarmas (ISA-18.2)

**Ubicación:** `automation/managers/alarms.py`, `automation/alarms/`, `automation/dbmodels/alarms.py`

| Capacidad | Estado |
|---|---|
| Tipos: BOOL, HH, H, L, LL | ✅ |
| Estados ISA-18.2: Normal, Unacknowledged, Acknowledged, RTN Unacknowledged, Shelved, Suppressed By Design, Out Of Service | ✅ |
| Acciones por estado (acknowledge, shelve, disable, etc.) | ✅ |
| Historial (`AlarmSummary`) | ✅ |
| Comentarios en alarmas (vía `Logs`) | ✅ |
| Notificación tiempo real `on.alarm` | ✅ |
| Priorización / flood suppression | ❌ No implementado |
| Alarm rationalization / KPI ANSI/ISA-18.2 | ❌ |
| Hornos de alarmas (alarm shelving con tiempo) | ⚠️ Parcial |

---

## 6. Estructura de Base de Datos

ORM: **Peewee**. Esquema auto-creado al conectar. Soporte: SQLite, PostgreSQL, MySQL.

### 6.1 Diagrama entidad-relación (lógico)

```
Manufacturer ──< Segment ──< Tags ──< TagValue (históricos)
                    │           │
Variables ──< Units ┘           ├──< Alarms ──< AlarmSummary ──< Logs
                                │
DataTypes ──────────────────────┘
                                │
OPCUA (clientes)                ├──< TagsMachines >── Machines
                                │
OPCUAServer (nodos servidor)    └──< Alarms

Roles ──< Users ──< Events ──< Logs
              │
              └──< Logs (directo)

AccessType ──< OPCUAServer

LinearReferencingGeospatial (módulo geoespacial independiente)
```

### 6.2 Tablas principales

| Tabla | Campos clave | Propósito |
|---|---|---|
| `Tags` | identifier, name, unit, data_type, opcua_*, scan_time, dead_band, filtros, anomalías | Configuración de tags de proceso |
| `TagValue` | tag_id, value, timestamp, unit | **Serie temporal** — índices en `timestamp` y `(tag, timestamp)` |
| `Alarms` | identifier, name, tag_id, trigger_type, trigger_value, state | Definición de alarmas |
| `AlarmSummary` | alarm_id, state_id, alarm_time, ack_time | Historial de transiciones |
| `AlarmStates` / `AlarmTypes` | Catálogos ISA | Estados y tipos |
| `Events` | timestamp, message, user_id, classification, priority, criticity | Auditoría de acciones |
| `Logs` | timestamp, message, user_id, event_id?, alarm_summary_id? | **Bitácora operativa** |
| `Users` / `Roles` | username, password (hash), role, token | Autenticación local |
| `OPCUA` | client_name, host, port | Clientes OPC UA persistidos |
| `OPCUAServer` | name, namespace, access_type | Nodos del servidor embebido |
| `Machines` | name, interval, threshold, buffer_size, classification | Config. state machines |
| `TagsMachines` | Relación N:M tags ↔ máquinas | |
| `LinearReferencingGeospatial` | Perfiles geoespaciales | Módulo especializado |

### 6.3 Deficiencias de persistencia

| Problema | Impacto |
|---|---|
| `TagValue` sin particionamiento ni retención automática (excepto backup SQLite >1GB que **borra** históricos) | Escalabilidad y compliance |
| Sin TimescaleDB / InfluxDB / PI para series temporales | Performance en millones de puntos |
| Sin migraciones versionadas (Alembic/Flyway) | Despliegues reproducibles |
| SQLite backup destructivo en `LoggerWorker` | Pérdida de datos históricos en edge |
| Contraseñas y tokens en misma tabla `Users` | Seguridad |
| Sin réplicas ni HA de BD | Disponibilidad |

---

## 7. Tiempo Real

### 7.1 Flujo actual

```
PLC/OPC UA → OPCUAClientManager → CVT.set_value()
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              TagObserver          Socket.IO emit       AlarmManager
              (queue)              on.tag               (evalúa umbrales)
                    │                                       │
                    ▼                                       ▼
              DBManager queue                          on.alarm
                    │
                    ▼
              LoggerWorker (cada ~10s) → TagValue en BD
```

### 7.2 Mecanismos

| Canal | Tecnología | Latencia típica estimada |
|---|---|---|
| Campo → CVT | OPC UA poll/subscription + Python | 100 ms – varios segundos (según scan_time) |
| CVT → HMI | Socket.IO (`on.tag`, `on.alarm`, `on.machine`) | 10–100+ ms (gevent + JSON) |
| CVT → BD | LoggerWorker batch (~10s default) | **No es tiempo real** — es histórico |
| HMI strip charts | Socket.IO + buffer local | Aceptable para visualización, no para control |

### 7.3 Deficiencias tiempo real

- **Socket.IO sobre HTTP/WebSocket** no es determinista; no apto para control de proceso crítico
- **GIL de Python** limita paralelismo real en adquisición masiva
- Sin garantías de latencia (SLA) ni jitter medido
- Sin separación entre red OT (campo) y red IT (HMI) a nivel de proceso
- El roadmap menciona gRPC/FastAPI pero **no está implementado**
- Frecuencia de polling mínima práctica ~100 ms; industria crítica exige 10–50 ms o determinismo

---

## 8. Gestión de Eventos

**Ubicación:** `automation/dbmodels/events.py`, decorador `@set_event`, página HMI `/events`

| Capacidad | Estado |
|---|---|
| Registro automático vía `@set_event` en operaciones CRUD | ✅ |
| Campos: message, description, classification, priority, criticity, user, timestamp | ✅ |
| Filtrado paginado por usuario, prioridad, criticidad, rango temporal | ✅ |
| Comentarios asociados (tabla `Logs`) | ✅ |
| Exportación / integración SIEM | ❌ |
| Eventos de proceso SOE (Sequence of Events) con resolución <1ms | ❌ |
| Inmutabilidad / WORM para FDA 21 CFR Part 11 | ❌ |

---

## 9. Bitácoras Operativas (Operational Logs)

**Ubicación:** `automation/dbmodels/logs.py`, HMI `/operational-logs`

Las bitácoras operativas (`Logs`) son el registro formal de acciones del operador y observaciones de planta:

- Vinculables a un **Evento** (`event_id`) o a un **AlarmSummary** (`alarm_summary_id`)
- Campos: timestamp, message, description, classification, user
- Creación manual desde HMI (`createLog`)
- Filtrado por usuario, alarma, evento, texto, rango temporal
- Paginación estándar (20 registros/página)

**Brechas vs. estándar industrial:**
- No hay plantillas de bitácora por turno (handover logs)
- Sin firma electrónica ni doble confirmación en acciones críticas
- Sin integración con procedimientos operativos (SOP/e-logbooks)
- Sin exportación regulada PDF con sello de tiempo

---

## 10. Data Logger

**Ubicación:** `automation/logger/datalogger.py`, `automation/workers/logger.py`, HMI `/tags/datalogger`

| Capacidad | Estado |
|---|---|
| Persistencia de TagValue en BD | ✅ |
| Deadband antes de registrar | ✅ |
| Consulta histórica con filtros temporales | ✅ |
| Exportación CSV desde HMI | ✅ |
| Agregaciones / downsampling | ⚠️ Limitado |
| Compresión de series | ❌ |
| Buffer en memoria antes de flush | ✅ vía workers |
| Periodo de flush configurable | ✅ default ~10s en LoggerWorker |

**Riesgo crítico:** En SQLite, cuando la BD supera 1 GB, `LoggerWorker.sqlite_db_backup()` copia el archivo, luego **elimina** TagValue, AlarmSummary, Events y Logs, y ejecuta VACUUM. Esto es inaceptable en entorno industrial sin política de archivo externo.

---

## 11. Graficación de Tendencias

### 11.1 Tendencias históricas (`/tags/trends`)

- Motor: **Plotly.js**
- Filtros: presets (1h, 6h, 12h, 1d, 1sem, 1mes), rango custom, timezone, múltiples tags
- Fuente: API REST → `TagValue` en BD
- Adecuado para análisis post-proceso; rendimiento degrada con grandes volúmenes sin downsampling server-side

### 11.2 Tendencias en tiempo real (`/real-time-trends`)

- Componente: `StripChart` + `react-grid-layout`
- Fuente: Socket.IO eventos `on.tag`
- Layout persistente en `localStorage`
- Múltiples strip charts configurables
- Adecuado para supervisión; no cumple estándar ISA-101 de jerarquía visual HMI sin trabajo adicional

### 11.3 Brechas

- Sin pensión de trends (trend templates) guardados en servidor
- Sin comparación de lotes (batch overlay)
- Sin límites de escala automáticos por tag (EN 60073 colores de alarma en gráficos)
- SCADA sináptico comentado/desactivado en rutas

---

## 12. Principios SOLID — Análisis Honesto

La documentación afirma cumplimiento SOLID. La realidad del código es mixta:

| Principio | Evaluación | Evidencia |
|---|---|---|
| **S** — Single Responsibility | ❌ Violado | `core.py` concentra API, sockets, tags, alarmas, OPC UA, import/export, BD |
| **O** — Open/Closed | ⚠️ Parcial | Nuevos módulos REST en `automation/modules/`, pero extender core requiere modificar el monolito |
| **L** — Liskov Substitution | ⚠️ Parcial | `BaseWorker`, `BaseLogger`, `BaseEngine` existen; subclases no siempre intercambiables |
| **I** — Interface Segregation | ❌ Débil | Sin interfaces formales (Protocol/ABC); dependencia directa de Flask, SocketIO, Peewee |
| **D** — Dependency Inversion | ❌ Violado | Singletons globales (`CVTEngine()`, imports directos); imposible inyectar mocks sin parches |

**Conclusión:** Los patrones Worker-Engine y Observer son sólidos para un MVP, pero el acoplamiento a infraestructura impide testabilidad y refactorización incremental real.

---

## 13. Performance — Estado Actual

### 13.1 Optimizaciones existentes

- CVT en memoria (acceso sub-ms según docs)
- Escrituras batch a BD vía worker
- Deadband en tags y logger
- Caché de browse OPC UA (300s)
- Adquisición por suscripción (DAS) para reducir tráfico
- Máquinas de estado con intervalos configurables

### 13.2 Cuellos de botella identificados

| Área | Problema |
|---|---|
| Python GIL | Threads no escalan en CPU-bound (filtros, muchos tags) |
| `core.py` monolítico | Cualquier request puede competir con adquisición |
| Socket.IO + gevent | Overhead JSON serialización por cada cambio de tag |
| Peewee ORM | Inserts fila-a-fila en históricos; sin bulk insert optimizado |
| Docker default | 256 MB RAM / 0.5 CPU — subdimensionado |
| Sin profiling continuo | Página Performance comentada en HMI |
| Tests de carga | No existen |

### 13.3 Métricas objetivo para grado industrial (referencia)

| Métrica | Objetivo industrial | PyAutomation estimado |
|---|---|---|
| Tags activos | 50.000+ | ~5.000–10.000 sin validar |
| Latencia campo→HMI | < 200 ms (supervisión) | 200 ms – 2 s |
| Throughput históricos | 100.000 puntos/seg | < 1.000 puntos/seg |
| Disponibilidad | 99.9%+ (HA) | Single point of failure |
| Tiempo de arranque en frío | < 30 s | Variable; carga de tags/OPC UA |

---

## 14. Seguridad y Usuarios

### 14.1 Estado actual

- Roles: sudo, admin, supervisor, operator, auditor, guest (niveles 0–256)
- Autenticación local con hash Werkzeug
- Tokens de sesión almacenados en BD (hasheados)
- Socket.IO autenticado con token en handshake
- CORS habilitado (`*`) en Socket.IO
- Secret key por variable de entorno (default débil en docker-compose)
- Sin LDAP / Active Directory / SSO
- Sin MFA
- Sin rate limiting en API
- Sin auditoría inmutable tipo Part 11

### 14.2 Brechas críticas

- Credenciales por defecto documentadas en `docker-compose.yml`
- Sin segregación de redes OT/IT
- Sin hardening checklist (IEC 62443)
- Sin rotación de certificados OPC UA automatizada

---

## 15. Testabilidad

| Aspecto | Estado |
|---|---|
| Tests unitarios | 5 archivos en `automation/tests/` (~30 casos) |
| Cobertura | Tags, alarmas, usuarios, roles, OPC UA serialización, geoespacial |
| Tests de integración OPC UA | ❌ |
| Tests de carga / soak | ❌ |
| Simulador de planta (digital twin) | ❌ |
| CI/CD con tests automáticos | `.github/workflows/publish.yml` — publicación, no suite completa |
| HIL (Hardware-in-the-Loop) | ❌ |

**Riesgo:** Probar en planta real es peligroso. No existe banco de pruebas con PLC simulado (Prosys, Kepware, Matrikon) integrado en CI.

---

## 16. Deficiencias Consolidadas

### 16.1 Deficiencias que usted identificó (confirmadas en código)

| # | Deficiencia | Confirmación |
|---|---|---|
| 1 | Stack no acorde — debería ser Rust/C# | ✅ Python+Flask no es industrial-grade para RT |
| 2 | Escalabilidad edge distribuida | ✅ Monolito único; sin agentes edge |
| 3 | LDAP / Active Directory | ✅ Solo auth local |
| 4 | Tiempo real debería ser gRPC | ✅ Solo REST + Socket.IO |
| 5 | Facilidad de despliegue/instalación | ⚠️ Docker existe pero recursos default inadecuados; sin instalador Windows/Linux nativo, sin K8s/Helm |
| 6 | Testeable fuera de planta | ✅ Cobertura mínima, sin simulador |

### 16.2 Deficiencias adicionales detectadas en auditoría

1. **Monolito `core.py`** — mantenibilidad y riesgo de regresiones
2. **Librería OPC UA deprecated** — deuda técnica de conectividad
3. **Destrucción de históricos SQLite** en backup automático
4. **Sin HA / failover** — un solo contenedor/proceso
5. **Sin Modbus, MQTT, Sparkplug B** — protocolos industriales amplios ausentes
6. **SCADA sináptico desactivado** — brecha HMI vs. estándar ISA-101
7. **Sin cumplimiento formal** — IEC 62443, ISA-18.2 rationalization, ISA-101, FDA Part 11
8. **GIL + threads** — no escala para adquisición masiva
9. **Sin observabilidad** — OpenTelemetry, Prometheus, Grafana
10. **Sin versionado de configuración** — export/import JSON existe pero sin GitOps
11. **i18n parcial** — HMI bilingüe; documentación y mensajes de backend inconsistentes
12. **Roles RBAC no granulares** — sin permisos por pantalla/tag/acción

---

## 17. Roadmap v2.x vs. Programa v3.0

El `docs/roadmap.md` (v2.1–v2.3) planifica mejoras incrementales en Python/React. Con la decisión de stack **Rust + C# + TSDB**, ese roadmap pasa a **mantenimiento de correcciones** en la rama 2.x.

| Versión | Enfoque | Stack |
|---|---|---|
| **2.x** | Mantenimiento, bugfix, parches de seguridad | Python + React (actual) |
| **3.0** | Reescritura industrial completa | **Rust + C# + TimescaleDB/InfluxDB** |

La v3.0 **no** extiende `core.py`; reimplementa dominio y contratos a partir de la lógica validada en 2.x.

---

## 18. Arquitectura Objetivo v3.0 — Rust · C# · TSDB

### 18.1 Visión target

```
┌──────────────────────────────────────────────────────────────────────┐
│  SALA DE CONTROL                                                     │
│  HMI C# (.NET 8)                                                     │
│  · WPF (Windows industrial) o Blazor Hybrid (multi-plataforma)       │
│  · SCADA sináptico ISA-101 · Alarmas · Trends · Faceplates           │
│  · Cliente gRPC (Grpc.Net.Client) — streaming de tags/alarmas        │
│  · Auth: Windows Integrated / LDAP / Azure AD                        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ gRPC + mTLS (LAN planta)
┌──────────────────────────────▼───────────────────────────────────────┐
│  BACKEND RUST (Tokio)                                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐   │
│  │ pyauto-core │ │ pyauto-opc  │ │ pyauto-alarm│ │ pyauto-hist  │   │
│  │ gRPC server │ │ OPC UA Srv  │ │ ISA-18.2    │ │ TSDB writer  │   │
│  │ CVT / Tags  │ │ Client pool │ │ Evaluación  │ │ batch flush  │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘   │
│  PostgreSQL (config, users, events, alarmas)                         │
│  TimescaleDB / InfluxDB (series temporales TagValue)                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ gRPC (edge sync)
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ EDGE AGENT    │    │ EDGE AGENT    │    │ EDGE AGENT    │
│ Rust binary   │    │ Rust binary   │    │ Rust binary   │
│ OPC UA/Modbus │    │ OPC UA        │    │ MQTT/Sparkplug│
│ CVT local     │    │ CVT local     │    │ CVT local       │
│ Alarmas RT    │    │ Store-fwd     │    │ Alarmas RT      │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        ▼                    ▼                    ▼
     PLC/RTU              PLC/RTU              Sensores IIoT
```

### 18.2 Stack tecnológico v3.0 — detalle por capa

#### Backend — Rust

| Crate / herramienta | Uso |
|---|---|
| **Tokio** | Runtime async — adquisición, gRPC, workers |
| **tonic + prost** | Servidor/cliente gRPC; contratos `.proto` versionados |
| **open62541** (FFI) o **async-opcua** | Cliente y servidor OPC UA industrial |
| **tokio-modbus** | Modbus TCP (Fase 2) |
| **sqlx** + **refinery** / **sqlx-migrate** | PostgreSQL — config, usuarios, eventos, metadatos de alarmas |
| **influxdb2** o **timescaledb** (vía sqlx) | Escritura/consulta de series temporales |
| **tracing** + **opentelemetry** | Observabilidad |
| **rustls** | mTLS entre edge, backend y HMI |

**Responsabilidades del backend Rust (único runtime de proceso):**
- CVT en memoria (equivalente a `CVTEngine`)
- Pool OPC UA cliente/servidor
- Evaluación de alarmas ISA-18.2 en tiempo real
- Data logger con batch write a TSDB
- API gRPC para HMI C# y agentes edge
- Sin Flask, sin Socket.IO, sin GIL

#### HMI — C# (.NET 8)

| Componente | Uso |
|---|---|
| **WPF** (recomendado sala de control) o **Blazor Hybrid** | UI industrial nativa; renderizado GPU para sinópticos |
| **Grpc.Net.Client** | Streaming de tags (`SubscribeTags`), alarmas (`SubscribeAlarms`) |
| **LiveCharts2** / **OxyPlot** / **ScottPlot** | Tendencias históricas y strip charts RT |
| **Prism** o **CommunityToolkit.Mvvm** | MVVM — separación vista/lógica (SOLID en UI) |
| **System.DirectoryServices** / **Microsoft.Identity** | LDAP, Active Directory, Azure AD |
| **MaterialDesignInXaml** o controles industriales propios | Look & feel ISA-101 / EN 60073 |

**Por qué C# y no React para v3.0:**
- Salas de control industriales operan en **Windows** con pantallas dedicadas 24/7
- Integración nativa con **Active Directory** y políticas de grupo
- WPF permite sinópticos vectoriales con performance superior a canvas web
- Mismo ecosistema que UA-.NET, Kepware SDK, drivers Windows industriales
- Despliegue como instalador MSI/ClickOnce sin depender de navegador

**Migración desde HMI React 2.x:** el código React (`hmi/`) sirve como **especificación funcional** (rutas, pantallas, flujos); no se porta directamente.

#### Comunicación — gRPC

Contratos principales (`.proto`):

```
TagService        → GetTags, SubscribeTags (stream), WriteTag
AlarmService      → GetAlarms, Acknowledge, Shelve, SubscribeAlarms (stream)
HistoryService    → QueryTrends, QueryDownsampled
EventService      → CreateEvent, QueryEvents, SubscribeEvents
ConfigService     → Import/Export plant config
EdgeService       → RegisterAgent, SyncCVT, Heartbeat
AuthService       → Login (LDAP/local), ValidateToken
```

### 18.3 Base de datos en tiempo real — TimescaleDB vs. InfluxDB

| Criterio | **TimescaleDB** | **InfluxDB** |
|---|---|---|
| Modelo | Extensión PostgreSQL — SQL estándar | TSDB propietario — Flux/InfluxQL/SQL (v3) |
| Config + históricos unificados | ✅ Una sola BD (tags config + hypertables) | ⚠️ Requiere PostgreSQL aparte para config |
| Throughput escritura | 100k–500k puntos/seg (hardware medio) | 500k–1M+ puntos/seg |
| Consultas de tendencias | SQL + `time_bucket()`, continuous aggregates | Downsampling nativo, retention policies |
| JOINs config ↔ series | ✅ Directo (`tag_id` FK) | ❌ Denormalizar tags en tags de Influx |
| Retención / downsampling | Continuous aggregates + compression policies | Retention policies + tasks |
| HA / réplicas | Patroni, streaming replication PostgreSQL | InfluxDB Enterprise / OSS cluster limitado |
| Ecosistema industrial | Muy usado con Grafana, compatible PI-style | Estándar en IIoT, Telegraf, Kapacitor |
| Migración desde TagValue Peewee | ✅ Mapeo directo a hypertable | Requiere pipeline ETL |
| Edge offline store-forward | sqlx + SQLite local → sync | influxdb-client + bucket local |

**Recomendación para PyAutomation v3.0:**

| Escenario | Elección |
|---|---|
| Planta de proceso clásica, equipo con experiencia SQL, unificar operaciones | **TimescaleDB** ✅ (opción principal) |
| IIoT masivo, >500k tags/seg, muchos edge agents, integración Telegraf | **InfluxDB** |
| Máxima flexibilidad | **Híbrido:** PostgreSQL (config) + InfluxDB (telemetría) — mayor complejidad operativa |

**Esquema TimescaleDB propuesto (hypertable principal):**

```sql
-- Config en PostgreSQL estándar (tags, alarms, users, events...)
CREATE TABLE tag_values (
    time        TIMESTAMPTZ NOT NULL,
    tag_id      UUID NOT NULL REFERENCES tags(id),
    value       DOUBLE PRECISION,
    quality     SMALLINT DEFAULT 192,  -- OPC UA Good
    source_ts   TIMESTAMPTZ            -- timestamp de campo (SOE)
);
SELECT create_hypertable('tag_values', 'time');
CREATE INDEX ON tag_values (tag_id, time DESC);

-- Continuous aggregate: 1 minuto
CREATE MATERIALIZED VIEW tag_values_1m
WITH (timescaledb.continuous) AS
SELECT tag_id, time_bucket('1 minute', time) AS bucket,
       avg(value), min(value), max(value), count(*)
FROM tag_values GROUP BY tag_id, bucket;
```

**Esquema InfluxDB propuesto (si se elige Influx):**

```
Measurement: tag_value
Tags:   plant, area, tag_name, tag_id, unit, data_type
Fields: value, quality
Timestamp: source_ts (nanosegundos)
Retention: raw 7d → downsampled_1m 90d → downsampled_1h 2y
```

### 18.4 Justificación del stack v3.0

| Capa | Tecnología | Razón industrial |
|---|---|---|
| Backend OT + plataforma | **Rust** | Sin GIL, memoria segura, latencia predecible, binarios edge pequeños, concurrencia Tokio |
| HMI operador | **C# / .NET 8** | Estándar en salas de control Windows, LDAP nativo, WPF para SCADA ISA-101 |
| Series temporales | **TimescaleDB** (primario) o **InfluxDB** | Diseñados para millones de puntos; retención y downsampling nativos |
| Comunicación | **gRPC** | Contratos fuertes, streaming, multiplataforma Rust ↔ C# |
| Config relacional | **PostgreSQL** | Usuarios, roles, alarmas, eventos, bitácoras — ACID |
| Auth | **LDAP / AD** | Confianza empresarial; sin contraseñas locales en producción |
| Observabilidad | **OpenTelemetry + Grafana** | Integración natural con TimescaleDB e InfluxDB |

---

## 19. Scope de Refactorización v3.0

> Estimación total: **14–18 meses** con equipo de 4–6 ingenieros (2 Rust, 2 C#, 1 DevOps, 1 QA industrial).

### Fase 0 — Contratos y fundación (2 meses)

| ID | Entregable | Stack |
|---|---|---|
| 0.1 | Definir `.proto` v1 (Tag, Alarm, History, Event, Edge, Auth) | Rust + C# codegen |
| 0.2 | Monorepo: `crates/` (Rust), `src/PyAutomation.Hmi/` (C#), `proto/` | Cargo + .NET solution |
| 0.3 | Banco de pruebas OPC UA simulado en CI | Rust + docker |
| 0.4 | Decisión formal TSDB: TimescaleDB vs InfluxDB (PoC 100k puntos/seg) | Benchmark |
| 0.5 | Esquema PostgreSQL v3 (config) + migración desde Peewee (script) | sqlx + Python script |
| 0.6 | Documento de equivalencia 2.x → 3.x (cada módulo Python → crate/servicio) | Docs |

### Fase 1 — Backend Rust núcleo (3–4 meses)

| ID | Entregable | Stack |
|---|---|---|
| 1.1 | `pyauto-core`: CVT en memoria, CRUD tags, gRPC server | Rust, tonic |
| 1.2 | `pyauto-opc`: cliente OPC UA (DAQ + DAS), pool conexiones | open62541 / async-opcua |
| 1.3 | `pyauto-alarm`: motor ISA-18.2, estados, acciones, stream gRPC | Rust |
| 1.4 | `pyauto-hist`: writer batch → TimescaleDB/InfluxDB, deadband | Rust, sqlx/influxdb2 |
| 1.5 | `pyauto-edge`: agente Rust standalone, store-and-forward | Rust, gRPC |
| 1.6 | Tests integración: 5k tags sintéticos, latencia < 50 ms CVT | criterion + CI |

### Fase 2 — HMI C# MVP (3–4 meses)

| ID | Entregable | Stack |
|---|---|---|
| 2.1 | Shell WPF: login LDAP/AD, navegación, roles RBAC | C#, Grpc.Net.Client |
| 2.2 | Pantalla Tags: lista, valores RT (gRPC stream), escritura | WPF + MVVM |
| 2.3 | Pantalla Alarmas: resumen, acknowledge, shelve, stream RT | WPF |
| 2.4 | Tendencias históricas: consulta HistoryService + gráfico | ScottPlot/LiveCharts2 |
| 2.5 | Strip charts RT: SubscribeTags → buffer circular | WPF |
| 2.6 | Eventos y bitácoras operativas | WPF + PostgreSQL vía gRPC |

### Fase 3 — TSDB y migración de datos (2 meses)

| ID | Entregable | Stack |
|---|---|---|
| 3.1 | Hypertables / buckets con políticas de retención | TimescaleDB o InfluxDB |
| 3.2 | Continuous aggregates / downsampling (1s→1m→1h) | TSDB nativo |
| 3.3 | Herramienta migración TagValue 2.x → 3.x | Script Python → Rust ETL |
| 3.4 | Eliminar lógica destructiva SQLite de v2.x en migración | — |

### Fase 4 — SCADA e industrial UI (3 meses)

| ID | Entregable | Stack |
|---|---|---|
| 4.1 | Editor sinóptico WPF (ISA-101): paleta, binding a tags gRPC | C# |
| 4.2 | Colores EN 60073, estados de equipo, faceplates | WPF custom controls |
| 4.3 | OPC UA Server embebido en `pyauto-opc` | Rust |
| 4.4 | Comunicaciones: gestión clientes OPC UA desde HMI | C# + gRPC |

### Fase 5 — Seguridad, edge y despliegue (2–3 meses)

| ID | Entregable | Stack |
|---|---|---|
| 5.1 | mTLS Rust ↔ C# ↔ Edge | rustls, .NET cert store |
| 5.2 | RBAC granular por pantalla/tag/acción | PostgreSQL + gRPC middleware |
| 5.3 | Audit trail append-only (eventos, setpoints) | PostgreSQL |
| 5.4 | Docker multi-stage: `pyauto-server` (Rust), `pyauto-edge`, TSDB | Docker Compose + Helm |
| 5.5 | Instalador MSI (HMI) + servicio Windows (backend) | WiX / .NET publish |

### Fase 6 — Calidad industrial (continuo)

| ID | Entregable | Stack |
|---|---|---|
| 6.1 | Cobertura > 80% crates Rust críticos | cargo-tarpaulin |
| 6.2 | Tests soak 72h (OPC UA sim + 10k tags) | CI nightly |
| 6.3 | IQ/OQ/PQ templates para validación en planta | Docs |
| 6.4 | Pentest IEC 62443 SL-T | Externo |

### Paridad funcional 2.x → 3.0

| Módulo 2.x | Componente 3.0 | Prioridad MVP |
|---|---|---|
| `CVTEngine` | `pyauto-core` CVT | P0 |
| `AlarmManager` | `pyauto-alarm` | P0 |
| `OPCUAClientManager` | `pyauto-opc` client | P0 |
| `OPCUAServer` (state machine) | `pyauto-opc` server | P1 |
| `DataLogger` | `pyauto-hist` | P0 |
| `Events` / `Logs` | PostgreSQL + gRPC EventService | P1 |
| `Machine` / state machines | `pyauto-core` scheduler Tokio | P2 |
| HMI React (`hmi/`) | WPF C# | P0 (pantallas core) |
| `LinearReferencingGeospatial` | Módulo C# Fase 4+ | P3 |

---

## 20. Decisión Arquitectónica — v3.0

| Opción | Descripción | Decisión |
|---|---|---|
| A. Evolucionar Python 2.x | Roadmap incremental Flask/FastAPI | ❌ Solo mantenimiento |
| B. Híbrido Strangler | React + Rust parcial | ❌ Descartado — duplica esfuerzo UI |
| **C. Reescritura Rust + C# + TSDB** | Stack industrial definido | **✅ Adoptado para v3.0** |

**Criterios que motivan la decisión:**
1. **Rust** resuelve GIL, latencia y edge en un solo runtime de backend
2. **C#** es el estándar de facto para HMI industrial en Windows/AD
3. **TimescaleDB/InfluxDB** reemplazan `TagValue` en Peewee — diseñados para series temporales masivas
4. **gRPC** reemplaza REST + Socket.IO con contratos versionados entre Rust y C#
5. El HMI React 2.x no se arrastra — se usa como blueprint funcional

**Riesgo principal:** time-to-market. Mitigación: MVP en Fase 1–2 (core + alarmas + tags + trends) antes de SCADA completo.

---

## 21. Estándares Industriales de Referencia

Para alcanzar clase mundial, la refactorización debe trazar explícitamente contra:

| Estándar | Aplicación en PyAutomation |
|---|---|
| **ISA-18.2** | Gestión de alarmas — parcialmente cumplido |
| **ISA-101** | HMI design — pendiente |
| **IEC 62443** | Ciberseguridad industrial — pendiente |
| **OPC UA Parts 1-14** | Interoperabilidad — básico |
| **FDA 21 CFR Part 11** | Audit trail electrónico — pendiente |
| **IEC 61511** | Seguridad funcional — fuera de scope SCADA pero relevante en integración |
| **Sparkplug B** | IIoT — planificado v2.2.0 |
| **EN 60073** | Codificación de colores — parcial en UI |

---

## 22. Conclusiones

PyAutomation 2.x es una **base funcional sólida** como referencia de dominio (OPC UA, CVT, alarmas ISA-18.2, históricos, eventos, bitácoras). No es el cimiento sobre el que construir grado industrial.

**PyAutomation 3.0** se define con un stack cerrado:

| Capa | Tecnología |
|---|---|
| Backend / Edge / OPC UA | **Rust** |
| HMI / SCADA | **C# .NET 8** (WPF) |
| Series temporales | **TimescaleDB** (recomendado) o **InfluxDB** |
| Comunicación | **gRPC** streaming |
| Auth | **LDAP / Active Directory** |

Las brechas de 2.x que 3.0 resuelve por diseño:

1. **GIL y Python** → runtime Tokio en Rust
2. **Socket.IO / REST** → gRPC con contratos `.proto` Rust ↔ C#
3. **React web** → WPF industrial con LDAP nativo e ISA-101
4. **TagValue en Peewee** → hypertables TimescaleDB o buckets InfluxDB
5. **Monolito `core.py`** → crates Rust desacoplados + agentes edge
6. **Tests insuficientes** → CI con PLC simulado y soak 72h desde Fase 0

El programa de **6 fases** (§19) estima 14–18 meses hasta MVP industrial completo. La v2.x permanece en mantenimiento; toda inversión nueva va a la rama `v3` del monorepo Rust + .NET.

---

## 23. Referencias del Repositorio

| Recurso | Ruta |
|---|---|
| Arquitectura | `docs/architecture.md` |
| Roadmap oficial | `docs/roadmap.md` |
| Base de datos | `docs/Users_Guide/Database/index.md` |
| Core | `automation/core.py` |
| CVT | `automation/tags/cvt.py` |
| Alarmas | `automation/managers/alarms.py`, `automation/alarms/states.py` |
| OPC UA Client | `automation/managers/opcua_client.py` |
| Data Logger | `automation/logger/datalogger.py` |
| Docker | `Dockerfile`, `docker-compose.yml` |
| HMI | `hmi/` |
| Tests | `automation/tests/` |

---

*Documento de planificación v3.0 — Stack: Rust · C# · TimescaleDB/InfluxDB. Revisar con ingeniería, operaciones y ciberseguridad antes de ejecución.*
