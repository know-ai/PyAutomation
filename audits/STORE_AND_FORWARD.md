# Auditoría Store-and-Forward (Core ↔ Base de Datos)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Durabilidad de datos ante desconexión / caída del servidor de base de datos |
| **Clasificación** | Auditoría de arquitectura de datos · Confidencialidad interna |
| **Fecha** | 2026-08-13 |
| **Metodología** | Revisión estática de código, trazabilidad de rutas de persistencia, contraste con prácticas industriales (ISA-95 / edge historian / outbox pattern) |
| **Veredicto global** | **C+ / B−** — hay desacoplamiento asíncrono para históricos de tags; **no** hay Store-and-Forward de clase mundial |
| **Objetivo declarado** | Garantizar que adquisición, modelos y cualquier dato destinado a BD **no se pierdan** durante outages, sin degradar el desempeño de adquisición |

---

## 1. Resumen ejecutivo

PyAutomation implementa un **desacoplamiento productor–consumidor en memoria** para el histórico de tags (`TagValue`): el CVT notifica a un `TagObserver`, que encola muestras en `DBManager._tag_queue`; el `LoggerWorker` solo drena esa cola cuando `check_connectivity()` es verdadero. Esa pieza es el núcleo de lo que hoy se percibe como “buffer ante caída de BD”.

Eso **no** equivale a una estrategia Store-and-Forward (SAF) industrial:

1. La cola es **solo RAM**, **sin límite** y **sin spill a disco**.
2. El drenado es **antes del ACK** de escritura: si el `insert_many` falla tras vaciar la cola, las muestras se **pierden**.
3. Alarmas (`AlarmSummary`), eventos (`Events`), logs operativos (`Logs`), máquinas y configuración OPC UA **no tienen cola SAF**: ante BD caída el motor retorna y el dato se **descarta**.
4. Un reinicio del proceso (OOM, crash, deploy) **borra** todo lo buffered.
5. El mantenimiento SQLite (>1 GB) **borra** históricos en vivo tras copiar un backup.

**Conclusión para la dirección técnica:** la adquisición en memoria (CVT / OPC UA / state machines) puede seguir operando con BD caída — eso es positivo para el *hot path* — pero la **promesa de “no se pierde nada que deba ir a BD” no está cumplida**. Hoy el sistema ofrece **best-effort buffering de tags**, no **garantía de entrega durable**.

Para alcanzar **A+** se requiere un journal durable en disco, ACK post-commit, colas acotadas con backpressure explícito, SAF unificado para alarmas/eventos/logs, métricas de salud y eliminación del purge destructivo.

---

## 2. Criterio de clase mundial (benchmark)

Un Store-and-Forward de clase mundial, en el borde industrial, debe satisfacer como mínimo:

| ID | Capacidad | Definición operativa | ¿Hoy? |
|---|---|---|---|
| SAF-01 | **No bloquear adquisición** | El *hot path* (CVT / OPC UA / modelos) nunca espera a la BD remota | ✅ Parcial (tags) |
| SAF-02 | **Memoria acotada** | Cola con `maxsize` + política de drop/alerta explícita | ❌ |
| SAF-03 | **Spill a disco** | Cuando la RAM llega al umbral, journal local append-only | ❌ |
| SAF-04 | **Durabilidad ante reinicio** | Lo buffered sobrevive crash / restart / OOM recovery | ❌ |
| SAF-05 | **At-least-once con ACK** | Solo se elimina del journal tras commit confirmado | ❌ (hoy: at-most-once tras drain) |
| SAF-06 | **Idempotencia / exactly-once lógico** | Clave de deduplicación `(tag_id, timestamp)` o UUID de muestra | ❌ |
| SAF-07 | **Cobertura multi-path** | Tags, alarmas, eventos, logs, configs críticas | ❌ (solo tags + audit DB ≤8) |
| SAF-08 | **Flush eficiente** | Batches ordenados, rate-limited, sin saturar el servidor al volver | ⚠️ Un batch por ciclo; sin throttle |
| SAF-09 | **Métricas y salud** | `queue_depth`, `flush_lag`, `dropped`, `replay_backlog` + alertas | ❌ |
| SAF-10 | **Retención segura** | Archive-before-purge; nunca DELETE masivo sin política | ❌ (backup SQLite destructivo) |

**Nota metodológica:** “eficiente y sin afectar adquisición” (SAF-01) y “garantizar que no se pierda” (SAF-04/05) son objetivos en tensión. La solución de clase mundial los resuelve con **desacoplamiento + journal local + backpressure gradual**, no con cola infinita en RAM.

---

## 3. Arquitectura observada (as-is)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         HOT PATH (adquisición)                           │
│  OPC UA / DAQ / State Machines / Modelos                                 │
│            │                                                             │
│            ▼                                                             │
│         CVTEngine (valores actuales en memoria)                          │
└────────────┬─────────────────────────────────────────────────────────────┘
             │ notify observers
     ┌───────┴────────┬────────────────────┬──────────────────────────────┐
     ▼                ▼                    ▼                              ▼
 TagObserver     Alarm FSM /           @set_event /                  DB auditor
 (DBManager)     AlarmManager          Logs / Machines               (pending ≤8)
     │                │                    │                              │
     ▼                ▼                    ▼                              ▼
┌────────────┐   check_connectivity   check_connectivity            Events
│ queue.Queue│   → write or DROP      → write or DROP               (flush on
│  unbounded │                                                    reconnect)
│  (RAM)     │
└─────┬──────┘
      │ LoggerWorker (~10 s)
      │ if connectivity OK:
      │   drain ALL → write_tags → insert_many(TagValue)
      │ else:
      │   reconnect_to_db(); queue grows
      ▼
 PostgreSQL / MySQL / SQLite
```

### Componentes clave

| Componente | Ubicación | Rol real |
|---|---|---|
| `DBManager._tag_queue` | `automation/managers/db.py` | Única cola de persistencia histórica de tags |
| `TagObserver.update` | `automation/tags/tag.py` | `put(..., block=False)` hacia la cola |
| `LoggerWorker.run` | `automation/workers/logger.py` | Watchdog BD + drenado + backup SQLite + OPC UA |
| `DataLogger.write_tags` | `automation/logger/datalogger.py` | `TagValue.insert_many` batch |
| `Buffer` | `automation/buffer.py` | Buffer circular para HMI/DAS — **no** es capa SAF de BD |
| `DatabaseConnectionAuditor` | `automation/utils/db_audit.py` | Único buffer fail-safe documentado (lifecycle BD) |

---

## 4. Inventario de rutas de persistencia

| Ruta de datos | Destino BD | ¿Buffer ante outage? | Comportamiento si BD caída | Riesgo |
|---|---|---|---|---|
| Histórico de tags | `TagValue` | Sí — cola RAM ilimitada | BUFFERED (mientras proceso vivo) | OOM; LOST en crash o drain+fail |
| Estado / definición de alarmas | `Alarms` | No | LOST / no persistido | Alto (auditoría ISA) |
| Histórico de alarmas | `AlarmSummary` | No | LOST (`check_connectivity` → return) | Crítico |
| Eventos de sistema / CRUD | `Events` | No* | LOST | Crítico |
| Logs operativos | `Logs` | No | LOST | Alto |
| Máquinas / tags-máquina | `Machines`, `TagsMachines` | No | LOST | Medio |
| Config OPC UA server/client | tablas OPC UA | No | LOST | Medio |
| Auditoría conexión BD | `Events` | Sí — pending ≤8 | BUFFERED → flush | Bajo (acotado) |
| Auditoría conexión OPC UA | `Events` | No | DROPPED | Medio |
| Strip-chart / DAS `Buffer` | — | Circular overwrite | Irrelevante para SAF BD | Info |

\*Excepto el auditor de conexión BD, que no cubre `@set_event` ni el resto del dominio Events.

---

## 5. Hallazgos (evidencia → impacto → remediación)

### CRITICAL

#### C-01 — No existe Store-and-Forward durable para `TagValue`

- **Evidencia:** `DBManager.__init__` crea `queue.Queue()` sin `maxsize` (`managers/db.py`). `TagObserver` hace `put(result, block=False)` (`tags/tag.py`). No hay journal en disco.
- **Impacto:** Outages largos → crecimiento ilimitado de RAM → riesgo de OOM. Reinicio del proceso → pérdida total del backlog. La promesa “no se pierde la data adquirida” **no se cumple**.
- **Remediación A+:** Journal local append-only (SQLite spill / segment files) + cola RAM acotada + spill automático al umbral.

#### C-02 — Drain-before-ACK (pérdida silenciosa post-drenado)

- **Evidencia:** `LoggerWorker` hace `get_tags_from_queue` (vacía la cola) y luego `write_tags`. Si `check_connectivity` cambia o `insert_many` falla, `write_tags` retorna `None` (`datalogger.py`) y `BaseEngine` captura excepciones sin reencolar.
- **Impacto:** Condición de carrera / fallo transitorio tras “reconexión aparente” → muestras ya sacadas de la cola **se pierden** sin traza de negocio.
- **Remediación A+:** Semántica *peek → commit → ack*. Solo eliminar del journal / cola tras commit exitoso. Ante fallo: requeue o dejar en journal.

#### C-03 — Backup SQLite destructivo de históricos

- **Evidencia:** `sqlite_db_backup` si tamaño > 1 GB: copia a `db/backups/`, luego `TagValue.delete()`, `AlarmSummary.delete()`, `Events.delete()`, `Logs.delete()`, `VACUUM` (`workers/logger.py`).
- **Impacto:** Pérdida operativa de histórico “en caliente” aunque exista copia; ventana de inconsistencia; incompatible con retención/auditoría industrial.
- **Remediación A+:** Archive-before-purge con verificación de integridad; particiones / TTL; nunca DELETE masivo como mantenimiento implícito sin política y confirmación.

---

### HIGH

#### H-01 — Alarmas, eventos y logs: drop inmediato

- **Evidencia:** `EventsLogger.create` / `AlarmsLogger.*` / `LogsLogger.create` retornan si `not check_connectivity()`.
- **Impacto:** Durante outage se pierde exactamente lo que más se necesita para forense: transiciones de alarma, eventos de sistema, logs operativos.
- **Remediación A+:** Outbox / journal unificado (o colas SAF por dominio) con misma semántica ACK que tags.

#### H-02 — Cobertura asimétrica de auditoría de conexión

- **Evidencia:** `db_audit.py` bufferiza ≤8 eventos; `opcua_audit.py` hace fail-open drop si Events no escribe.
- **Impacto:** Traza incompleta del ciclo de vida OPC UA precisamente cuando la BD está inestable.
- **Remediación:** Extender el patrón de pending+flush (o journal) a OPC UA y otros eventos de sistema.

#### H-03 — `disconnect_to_db` incompleto

- **Evidencia:** Solo llama `db_manager._logger.logger.stop_db()` (DataLogger). Otros engines (alarms, events, logs, machines, opcua) pueden conservar `_db` / flags inconsistentes.
- **Impacto:** Estados “medio desconectados”, escrituras parciales o errores opacos.
- **Remediación:** Propagar `stop_db` / `set_is_history_logged(False)` a **todos** los engines vía `DBManager`.

#### H-04 — `is_db_connected()` no valida liveness

- **Evidencia:** `bool(db_manager.get_db())` — no ejecuta ping.
- **Impacto:** El core puede creerse conectado con socket muerto; la UI/API reportan estado incorrecto.
- **Remediación:** Exponer liveness vía `check_connectivity()` (o equivalente) en el health/status público.

---

### MEDIUM

#### M-01 — Sin métricas ni alertas de profundidad de cola / drop rate

- Health actual es esencialmente ping HTTP; no hay `queue_depth`, `flush_lag`, `dropped_samples`.
- Sin telemetría no hay forma de demostrar SAF ni de alertar antes del OOM.

#### M-02 — Filtro `manufacturer` / `segment` descarta muestras al drenar

- `get_tags_from_queue` puede omitir tags aunque la BD esté sana (`workers/logger.py`). Drop silencioso si la configuración de filtrado no es la esperada.

#### M-03 — `AlarmManager._tag_queue` aparentemente sin consumidor SAF/DB

- Patrón de cola presente; documentación/auditorías previas señalan posible código muerto / fuga si se usa `attach` sin consumidor.

#### M-04 — Flush al reconectar sin throttle

- Un `insert_many` con backlog enorme (horas de outage) puede saturar Postgres/MySQL y alargar la recuperación (“thundering herd”).
- A+: batches acotados (N filas / M ms), backoff, prioridad (alarmas > eventos > tags).

#### M-05 — `UsersLogger` sin el mismo gate de connectivity

- Inconsistencia de defensas entre engines.

#### M-06 — Retry ciego (`db_rollback`)

- Un reintento sin requeue estructurado puede producir duplicados o fallos silenciosos.

---

### LOW / INFO

#### L-01 — `Buffer` DAS/HMI no debe confundirse con SAF

- Es un circular overwrite para visualización / ventanas cortas. Cumple otro propósito. Documentar explícitamente la distinción evita falsas garantías.

#### L-02 — SQLite WAL ayuda al crash del archivo local, no al outage de red hacia Postgres/MySQL

- `journal_mode=wal` en `set_db` es buena práctica local; **no** sustituye SAF de aplicación.

#### L-03 — Roadmap documentado ya menciona SAF futuro

- `docs/resumen-auditoria-industrial-pyautomation.md` lista `pyauto-edge` / store-and-forward como ítem de roadmap. Confirma que el gap es conocido a nivel de visión, no implementado en el core Python actual.

#### L-04 — Documentación de usuario puede sobreprometer

- Guías que afirman que el logging “se reanuda al reconectar” sin matizar qué se perdió generan expectativa incorrecta en operaciones.

---

## 6. Matriz de garantía (lo que hoy se puede / no se puede afirmar)

| Afirmación | ¿Soportada por el código? |
|---|---|
| “La adquisición CVT sigue aunque la BD caiga” | **Sí** (hot path desacoplado) |
| “Los tags históricos se acumulan un rato en memoria y se escriben al volver” | **Sí, best-effort**, si el proceso no muere y el write no falla tras drenar |
| “Nada destinado a BD se pierde durante un outage” | **No** |
| “Sobrevive reinicio del core / contenedor” | **No** |
| “Alarmas y eventos quedan auditados aunque la BD esté caída” | **No** |
| “El flush al reconectar es controlado y no tumba el servidor de datos” | **No garantizado** |
| “Hay telemetría para demostrar que el SAF está sano” | **No** |

---

## 7. Evaluación de madurez (scorecard)

| Dimensión | Peso | Nota (0–5) | Comentario |
|---|---|---|---|
| Desacoplamiento del hot path | 15% | **4.0** | Buena separación CVT ↔ logger para tags |
| Durabilidad (disco / restart) | 20% | **0.5** | Solo RAM; audit DB ≤8 en memoria |
| Semántica de entrega (ACK / idempotencia) | 15% | **1.0** | Drain-before-ACK; sin claves de dedupe |
| Cobertura multi-path | 15% | **1.0** | Tags sí; alarmas/eventos/logs no |
| Protección de recursos (bounds / backpressure) | 10% | **0.5** | Cola ilimitada = anti-patrón |
| Eficiencia de replay | 10% | **2.0** | Batch insert existe; sin throttle ni prioridades |
| Observabilidad | 10% | **0.5** | Sin métricas SAF |
| Retención / higiene de histórico | 5% | **1.0** | Backup destructivo SQLite |

**Nota ponderada ≈ 1.4 / 5 → C+ / B−.**  
**Gap a A+ (≈ 4.5+):** requiere las remediaciones CRITICAL + HIGH de la sección 5 y el programa de la sección 8.

---

## 8. Arquitectura objetivo (to-be) — Store-and-Forward A+

### 8.1 Principios de diseño

1. **Hot path sagrado:** CVT / OPC UA / modelos nunca bloquean por I/O de BD remota.
2. **Journal local first:** toda escritura durable pasa por un *outbox* local antes (o en paralelo controlado) al remoto.
3. **ACK post-commit:** solo entonces se marca el registro como enviado.
4. **Bounds everywhere:** RAM capped; disco capped; alertas antes del hard limit.
5. **At-least-once + idempotencia** = exactly-once de negocio.
6. **Un contrato, muchos productores:** tags, alarmas, eventos, logs comparten el mismo framework SAF.

### 8.2 Diseño propuesto

```
Producers (CVT, Alarms, Events, Logs, Audits)
        │  non-blocking enqueue
        ▼
┌─────────────────────────────────────────┐
│  SAF Memory Ring (bounded, per priority)│
│   P0 alarms | P1 events | P2 tags       │
└───────────────┬─────────────────────────┘
                │ spill on threshold / timer
                ▼
┌─────────────────────────────────────────┐
│  Local Durable Journal (SQLite/WAL or   │
│  append-only segments under db/saf/)    │
│  fields: id, domain, payload, ts, state │
└───────────────┬─────────────────────────┘
                │ LoggerWorker / SafFlusher
                │ batch ≤ N, rate ≤ R
                ▼
        Remote DB (Postgres/MySQL/SQLite)
                │ commit OK
                ▼
        ACK → mark journal SENT → truncate/GC
```

### 8.3 Contratos de rendimiento (recomendados)

| Parámetro | Valor inicial sugerido | Motivo |
|---|---|---|
| RAM ring tags | 50k–200k muestras o 64–256 MB | Evitar OOM; spill temprano |
| Spill threshold | 70% del ring | Anticipar picos |
| Journal max disk | configurable (ej. 2–10 GB) | Política operativa |
| Batch flush | 500–5000 filas / ciclo | Balance throughput / lock time |
| Flush rate limit | configurable | Proteger servidor al reconectar |
| Prioridad | Alarms > Events > Logs > Tags | Valor de negocio |
| Idempotency | UUID de muestra o `(tag_id, timestamp_us)` UNIQUE | Replay seguro |

### 8.4 Roadmap de implementación (impacto × esfuerzo)

| Fase | Entrega | Cierra hallazgos | Esfuerzo relativo |
|---|---|---|---|
| **F0 — Contención** | `maxsize` + métricas `queue_depth` + alerta Events; no drenar sin éxito (requeue) | C-02 parcial, M-01 | Bajo |
| **F1 — Journal tags** | Spill disco + replay + ACK; sobrevive restart | C-01, C-02, SAF-03/04/05 | Medio |
| **F2 — Multi-path** | Outbox para AlarmSummary / Events / Logs | H-01, H-02 | Medio–Alto |
| **F3 — Replay inteligente** | Throttle, prioridades, idempotencia DB | M-04, M-06 | Medio |
| **F4 — Retención** | Sustituir DELETE masivo SQLite por archive verificado | C-03, SAF-10 | Medio |
| **F5 — Observabilidad** | Health SAF + dashboards + pruebas de caos (kill DB 30 min) | M-01, scorecard | Bajo–Medio |

**Criterio de aceptación A+:** prueba de caos documentada — BD caída ≥ 30 min con adquisición continua; reinicio del core a mitad; al recuperar, 100% de muestras/eventos esperados presentes (tolerancia 0 pérdida), lag de flush acotado, sin OOM, sin saturación del servidor de datos.

---

## 9. Pruebas recomendadas (suite de certificación SAF)

| ID | Escenario | Resultado esperado A+ |
|---|---|---|
| T-01 | BD down 10 min, adquisición 10 Hz × N tags | 0 pérdida; journal crece; hot path estable |
| T-02 | Kill -9 del proceso con backlog | Tras restart, replay completo |
| T-03 | Reconnect con fallo intermitente en `insert_many` | Requeue; sin huecos; sin duplicados de negocio |
| T-04 | Outage + transiciones de alarma | AlarmSummary completo al volver |
| T-05 | Outage + eventos de sistema / OPC UA audit | Events completos al volver |
| T-06 | Backlog 1M filas al reconectar | Flush rate-limited; CPU/IO de adquisición dentro de SLA |
| T-07 | Journal disk full | Alerta + política explícita (reject/drop oldest documentado) — nunca silencio |
| T-08 | SQLite > umbral de retención | Archive verificado **antes** de purge |

---

## 10. Lo que sí está bien (fortalezas a preservar)

No todo es gap. Estas piezas son cimientos correctos y deben **conservarse** en el rediseño:

1. **Observer + cola** para no acoplar CVT al I/O de BD (base de SAF-01).
2. **`LoggerWorker` periódico** como punto natural de flusher / replay.
3. **`write_tags` + `insert_many`** como primitiva eficiente de inyección batch.
4. **Watchdog de reconexión BD** (`reconnect_to_db` / `db_reconnection`) ya existe y está cableado.
5. **Auditor de conexión BD** (`db_audit.py`): patrón fail-safe, buffer acotado, flush con timestamps — **referencia de diseño** a generalizar.
6. **Engines thread-safe** (`BaseEngine` locks): base sólida; conviene no romper el contrato al introducir el journal.

---

## 11. Dictamen final

| Pregunta del negocio | Respuesta auditora |
|---|---|
| ¿Hay estrategia Store-and-Forward hoy? | **Parcial y frágil** — buffer RAM de tags, no SAF industrial |
| ¿Se garantiza que no se pierde data hacia BD? | **No** |
| ¿La adquisición se ve afectada por la BD caída? | **En general no** (hot path OK) — el riesgo es el **OOM** por cola ilimitada |
| ¿El flush al reconectar es eficiente y seguro? | **Batch sí; control de carga e idempotencia no** |
| ¿Nivel actual vs A+? | **C+ / B− → requiere programa F0–F5** |

**Recomendación:** tratar el Store-and-Forward como **capacidad de producto de primer nivel**, no como detalle del logger. Hasta cerrar C-01/C-02/C-03 y H-01, la documentación de usuario y cualquier afirmación comercial sobre “no pérdida de datos ante desconexión de BD” deben **calificarse** explícitamente (best-effort tags en memoria; pérdida de alarmas/eventos/logs; no sobrevivencia a reinicio).

---

## 12. Referencias de código (índice de evidencia)

| Tema | Archivo |
|---|---|
| Cola de tags | `automation/managers/db.py` |
| Encolado desde CVT | `automation/tags/tag.py` (`TagObserver`) |
| Drenado / reconnect / backup | `automation/workers/logger.py` |
| Batch write | `automation/logger/datalogger.py` (`write_tags`) |
| Gate connectivity | `automation/logger/core.py` (`check_connectivity`) |
| Events drop | `automation/logger/events.py` |
| Alarms history drop | `automation/logger/alarms.py` |
| Buffer HMI (no SAF) | `automation/buffer.py` |
| Auditor BD (único SAF parcial) | `automation/utils/db_audit.py` |
| Connect / reconnect / disconnect | `automation/core.py` |
| Roadmap SAF (visión) | `docs/resumen-auditoria-industrial-pyautomation.md` |
| Guía datalogger | `docs/Developments_Guide/core/datalogger.md` |

---

*Documento generado como auditoría técnica independiente sobre el código fuente de PyAutomation. No constituye certificación de producto; constituye un gap analysis accionable hacia Store-and-Forward A+.*
