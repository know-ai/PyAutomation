# Auditoría: Operación «Conexiones Estables»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/`) |
| **Alcance** | Conteo óptimo de backends PostgreSQL en idle (1 worker gunicorn + gevent) |
| **Evidencia de planta** | 7–8 conexiones `idle` estables en `idetect_db` tras ciclos de desconexión/reconexión (2026-08-17 18:28, host app `192.168.1.106`) |
| **Fecha** | 2026-08-17 |
| **Complementa** | `AUDIT_DB_CONNECTIONS.md`, `AUDIT_DB_CONNECTIONS_ETERNAL.md`, `AUDIT_DB_RECONNECT.md` |
| **Veredicto** | 8 no es un leak (el conteo no crece). Tampoco es óptimo. Cuatro sockets son hilos **async** de LDS/PPA/NPW/PFM que hicieron `Alarms.read_by_name('alarm.*.leak')` y no cerraron. Uno es un `SELECT` de `opcua` huérfano de hidratación. Dos son `SELECT 1` (LoggerWorker + residual). Objetivo idle: **1** (LoggerWorker). Techo: **≤ 4** |
| **Clasificación** | Auditoría de arquitectura · conexiones · Confidencialidad interna |

---

## 0. Respuesta directa

| Pregunta | Respuesta |
|---|---|
| ¿Es 8 el número óptimo? | **No.** Con 1 worker, idle persistente debe ser **1–3**. 8 indica sockets de arranque/ciclo de máquina que no se cierran |
| ¿Hay fuga (crecimiento)? | **No.** Tras reconectar, el censo vuelve a ~8. Eso es un **conjunto fijo de greenlets** que reabren y se quedan |
| ¿`application_name` ya estaba? | **Sí**, `PyAutomationIO`. No bastaba para atribuir: todos los sockets compartían el mismo nombre |
| ¿Quién debe vivir? | Solo **LoggerWorker** (replicación SAF). HTTP, SM, OPC, health y auditores son efímeros |
| ¿Cómo se baja a 2–3? | Cerrar el socket al salir de `machine.loop()`, de `journal_then_remote` y de las cargas de arranque. Etiquetar `PyAutomationIO:<hilo>` |

---

## 1. Captura de `pg_stat_activity` (planta, 2026-08-17 18:28)

Consulta (excluye el probe de esta auditoría):

```sql
SELECT pid, usename, application_name, client_addr, state,
       query, backend_start, state_change
FROM pg_stat_activity
WHERE datname = 'idetect_db'
  AND backend_type = 'client backend'
ORDER BY backend_start;
```

| pid | `application_name` | state | Última query (resumen) | `backend_start` | Atribución |
|---|---|---|---|---|---|
| 50966 | `PyAutomationIO` | idle | `SELECT … FROM "opcua"` | 18:15:17 | Hidratación OPC UA; greenlet que no cerró |
| 51050 | `PyAutomationIO` | idle | `Alarms` `name = 'alarm.LDS.leak'` | 18:15:23 | Hilo async **LDS** |
| 51053 | `PyAutomationIO` | idle | `Alarms` `name = 'alarm.PPA.leak'` | 18:15:23 | Hilo async **PPA** |
| 51056 | `PyAutomationIO` | idle | `Alarms` `name = 'alarm.NPW.leak'` | 18:15:23 | Hilo async **NPW** |
| 51060 | `PyAutomationIO` | idle | `Alarms` `name = 'alarm.PFM.leak'` | 18:15:24 | Hilo async **PFM** |
| 52115 | `PyAutomationIO` | idle | `SELECT 1` | 18:17:44 | Probe ligado residual (no LoggerWorker) |
| 52659 | `PyAutomationIO` | idle | `SELECT 1` | 18:21:44 | **LoggerWorker** (`ensure_bound` / watchdog) |

Agrupado: **7 idle `PyAutomationIO`** + 1 active de esta auditoría. El operador que cuenta `datname = idetect_db` sin filtrar `backend_type` puede ver **8**.

Ninguna fila estaba en `idle in transaction`.

Módulos activos en `app/configs/modules.yml`: LDS, PPA, NPW, PFM, Observer. Observer no dejó socket (no hace ese `read_by_name` al arrancar). `opcua_server` no aparece como `alarm.*.leak`.

---

## 2. Mapa: qué debe persistir

`append_machine(..., mode='async')` es el **default**. Cada máquina tiene un `SchedThread`. Peewee guarda el TCP en `threading.local` (greenlet-local). Un `SELECT` en ese hilo = 1 backend idle eterno.

| Componente | ¿Persistente? | Antes | Ahora |
|---|---|---|---|
| LoggerWorker (SAF) | **Sí** | 1 | 1 |
| LDS / PPA / NPW / PFM (`SchedThread`) | No | 4 idle (`alarm.*.leak`) | 0 — `ephemeral_historian` al salir de `loop()` |
| Observer / otras SM | No | 0–1 | 0 — mismo wrap |
| Carga OPC UA | No | 1 idle (`opcua`) | 0 — `connection_context` / `ephemeral_historian` |
| HTTP / Flask | No | 0 si hay teardown | 0 (`teardown_request`) |
| Health `/db`, censo | No | throwaway | throwaway `PyAutomationIO:probe` |
| Auditores (`persist_system_event`) | No | ya cerraban | sin cambio |
| `journal_then_remote` (alarma/evento/log) | No | escribía en el caller y dejaba el socket | cierra si no es LoggerWorker |
| DatabaseConnectionAuditor | No | no abre socket propio | 0 |

**Total idle esperado:** 1 (LoggerWorker). Pico 2–3 con un request o un ciclo de máquina in-flight. **CA-OPT-1: ≤ 4.**

---

## 3. Implementación

### 3.1 `application_name` descriptivo

`TrackedPostgresqlDatabase._connect` pone `PyAutomationIO:<thread.name>` (máx. 63). Hilos SM: `SM-LDS`, `SM-PPA`, … Probes: `PyAutomationIO:probe`.

```sql
SELECT application_name, state, count(*)
FROM pg_stat_activity
WHERE datname = 'idetect_db' AND backend_type = 'client backend'
GROUP BY 1, 2;
```

Tras el deploy se debe ver `PyAutomationIO:LoggerWorker` (1 idle) y, como mucho, picos `PyAutomationIO:SM-LDS` que desaparecen.

`DB_NAMED_CONNECTIONS` cuenta `application_name LIKE 'PyAutomationIO%'` en el `datname` actual.

### 3.2 Context managers / cierre efímero

| Sitio | Mecanismo |
|---|---|
| `SchedThread` / `StateMachineWorker.loop` | `with ephemeral_historian(...)` alrededor de `machine.loop()` |
| `journal_then_remote` | `close` en `finally` si no es LoggerWorker |
| `load_db_tags_to_machine` | `ephemeral_historian` |
| `create_system_user` | `ephemeral_historian` |
| `Machine.start` → `load_db_machines_config` | `ephemeral_historian` |
| Hidratación (`_hydrate_runtime_from_db`) | `connection_context` si no es LoggerWorker (ya existía) |
| `PyAutomation.run` | `release_ephemeral_historian()` (ya existía) |

`ephemeral_historian` no cierra el socket de `LoggerWorker` / `SafJournalFlusher`.

### 3.3 Techos

| Métrica | Antes | Ahora |
|---|---|---|
| `DB_CONNECTIONS_EXPECTED_MAX` | `(workers×2)+5` → 7 | `(workers×2)+2` → **4** |
| Alerta por defecto | 10 | **6** (`AUTOMATION_DB_CONNECTIONS_ALERT`) |

---

## 4. Pruebas

```bash
cd github/PyAutomation
/home/crivero/repo/gitlab/intelcon/idetectfugas/venv/bin/python3 -m unittest \
  automation.tests.test_db_io \
  automation.tests.test_database_health \
  automation.tests.test_connection_alarms -v
```

Nuevos: `historian_application_name` con prefijo, `ephemeral_historian` cierra / conserva LoggerWorker, `journal_then_remote` cierra el caller.

**Arranque en planta (pendiente de este wheel):**

1. Desplegar. Esperar 2 min idle (HMI abierta, sin navegar).
2. SQL §1: `count(*)` de `PyAutomationIO%` idle **≤ 4**, idealmente **1** (`:LoggerWorker`).
3. Cero `idle in transaction`.
4. Un ciclo outage/restore: el conteo idle vuelve al mismo número (CA-OPT-5).
5. Soak 24 h: el conteo no crece (CA-OPT-4).

---

## 5. Criterios de aceptación

| ID | Criterio | Estado |
|---|---|---|
| **CA-OPT-1** | Idle `pg_stat_activity` ≤ 4 tras arranque | Código listo. Planta: repetir SQL §1 con el nuevo wheel |
| **CA-OPT-2** | `application_name` `PyAutomationIO` o descriptivo | `PyAutomationIO:<rol>` en cada `_connect` |
| **CA-OPT-3** | Cero `idle in transaction` | Confirmado en la captura; no se abren transacciones largas |
| **CA-OPT-4** | Estable 24 h | Pendiente soak |
| **CA-OPT-5** | Reconnect no aumenta el conteo | `close_all` por owner + cierre efímero; validar en planta |

---

## 6. Runbook

Ver `PERFORMANCE_RUNBOOK.md` §11.

Si tras el deploy siguen apareciendo `PyAutomationIO:SM-*` idle más de un periodo de máquina: ese módulo consulta Peewee **fuera** de `loop()` (p. ej. un hilo propio). Cazar por `application_name` + `query`.

---

## 7. Conclusión

Ocho conexiones estables eran el censo de **quién tocó Peewee y no soltó el socket**, no un pool ni un leak. La evidencia (`alarm.LDS.leak` … `alarm.PFM.leak`) apunta a los hilos async de las máquinas de fugas.

Con cierre al final de cada `loop()`, escritura SAF que no deja el handle en el caller, y nombres de aplicación por hilo, el idle de planta debe quedar en el LoggerWorker. Eso es el conteo óptimo: el mínimo que la replicación necesita, y nada más.
