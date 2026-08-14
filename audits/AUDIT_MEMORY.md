# Auditoría de memoria — Operación «Memoria Eterna»

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Revisión estática de ciclo de vida: CVT/observers, DAS/OPC, SAF/Journal, workers, logs, HMI (hooks/Redux/sockets) |
| **Fecha** | 2026-08-14 (Ciclo de Vida Perfecto: detach en delete_tag / unsubscribe_to + métricas health) |
| **Clasificación** | Auditoría de fugas residuales · confidencialidad interna |
| **Metodología** | Revisión estática + corrección de ciclo de vida. Soak 24 h / 7 d, tracemalloc y objgraph **no ejecutados** en esta entrega |
| **Complementa** | `audits/AUDIT_DB_CONNECTION_MEMORY.md`, `audits/AUDIT_BACKEND_PERFORMANCE.md`, `audits/AUDIT_HMI_PERFORMANCE.md`, `audits/AUDIT_RT_TRENDS.md`, `audits/STORE_AND_FORWARD.md`, `audits/PERFORMANCE_RUNBOOK.md` |
| **Veredicto estático** | **A−** (ciclo de vida). `delete_tag` y `unsubscribe_to` son simétricos a attach. Health expone `TAG_OBSERVER_COUNT` / `MACHINE_OBSERVER_COUNT`. `tagHistory` acotado es **política de producto**, no un hallazgo. Certificado A+ de RSS 24 h (**CA-MEM-1**) sigue pendiente de soak. |

---

## 1. Resumen ejecutivo

Una aplicación industrial no se degrada por un `list.append` obvio: se degrada por un observer que nadie `detach`, un greenlet que retiene el request, o un heap de FiPy que el GC no compacta. En PyAutomationIO el diseño de régimen estable es **acotado**:

- `Buffer` → `deque(maxlen)`.
- DAS: buffer por tag de ~600 s / `scan_time`, se `pop` al borrar el tag.
- SAF: ring `50_000`, `max_pending_rows=5_000_000`, `CycleSampleCache` con TTL 2 s.
- Alarm/DB managers: `Queue(maxsize=1)`.
- Logs: `DedupeFilter` LRU `max_entries=1000`.
- HMI: historial 720 puntos × 64 tags; `useSocket` limpia maps e intervalos al logout/unmount.
- Health: `/api/health/system` expone `RSS_MB`, `CVT_TAG_COUNT`, `ALARM_COUNT`, `PENDING_ROWS`, `THREAD_COUNT`, `OPC_MONITORED_COUNT`, `TAG_OBSERVER_COUNT`, `MACHINE_OBSERVER_COUNT`.

El riesgo residual **en régimen de catálogo fijo** no es crecimiento monotónico. El hueco de ciclo de vida (MEM-PY-1 / MEM-PY-2) está **cerrado**: `delete_tag` hace `detach_all_observers()`; `unsubscribe_to` hace `tag.detach_machine(self)`. `tagHistory` acotado 720×64 es política de producto.

El crecimiento de RSS de cientos de MB/día **no se explica** por Peewee (ver `AUDIT_DB_CONNECTION_MEMORY.md`). Si aparece en planta, correlacionar `RSS_MB` con `PENDING_ROWS`, `CVT_TAG_COUNT`, `TAG_OBSERVER_COUNT` y, en iDetectFugas, con la malla FiPy de RTTM.

```
  Operador / API
        │
        ▼
  Tag / Alarm / Machine  ──attach──► Observer (_subject = Tag) ──► Queue / Machine
        │                              ▲
        │                              └── ciclo Tag ↔ Observer (GC de ciclos, sin __del__)
        ▼
  delete_tag / unsubscribe_to
        │
        ├── OPC unsubscribe          SÍ
        ├── CVT pop + DAS pop        SÍ
        ├── Alarm detach             SÍ (delete_alarm)
        └── Observer detach          SÍ (detach_all / detach_machine)
```

---

## 2. Alcance por capa

| Capa | Componentes | Riesgo típico | Estado estático |
|---|---|---|---|
| Adquisición OPC UA | DAS, `subscription`, `monitored_items`, `Buffer` | Handlers OPC, Node retenidos, buffer sin limpieza | **OK**. `unsubscribe` / `reset_client` / `unsubscribe_all` vacían `monitored_items`. `delete_tag` llama `unsubscribe_opcua` y `das.buffer.pop`. Buffer circular con `maxlen`. |
| CVT / estado | `CVTEngine`, `Tag`, `Alarm`, `Machine` | Observers sin detach, ciclos, dicts que crecen | **OK**. `delete_tag` → `detach_all_observers`. `unsubscribe_to` → `detach_machine`. `delete_alarm` detach. Conteos en health. |
| SAF / Journal | `JournalWriter`, `PersistenceGateway`, `CycleSampleCache` | PENDING eterno, cache sin poda | **OK acotado**. Ring + cap PENDING. Cache TTL 2 s (no comprueba `tag.exists`; ver MEM-PY-3). |
| Logs / auditores | `RotatingFileHandler`, `DedupeFilter` | Handlers no liberados, filtros con objetos | **OK**. LRU + ventanas `deque` podadas. Singleton del filtro = vida del proceso. |
| Workers / hilos | `LoggerWorker`, `AsyncStateMachineWorker`, `SchedThread` | Zombies, colas sin vaciar, `finally` | **OK con matices**. `stop_event` / `_stop` se respetan. `drop()` no saca la máquina de `_machines` (MEM-PY-4). |
| HMI React/Redux | `tagHistory`, alarms, `socketService`, `useSocket` | Historial sin logout, listeners, `setInterval` | **OK acotado**. Cleanup de intervalos/listeners. `tagHistory` **no** se vacía en logout: política de producto (720×64). |
| Gevent / Gunicorn | 1 worker, greenlets | Request retenido, ciclos | Fuera de esta capa de código; ver `AUDIT_DB_CONNECTION_MEMORY.md`. 1 worker sin pool Peewee. |

iDetectFugas (LDS, PPA, NPW, PFM, Observer, RTTM) se audita en `gitlab/intelcon/idetectfugas/audits/AUDIT_MEMORY.md`.

---

## 3. Principios SOLID aplicados a memoria

| Letra | Aplicación | Evidencia | Hueco |
|---|---|---|---|
| **S** | Cada componente libera lo suyo | `Tag.detach_all_observers` desde `delete_tag`; `detach_machine` desde `unsubscribe_to`; `Alarm.detach_from_tag` | — |
| **O** | Colecciones con máximo / TTL | `Buffer.maxlen`, SAF ring/cap, `DedupeFilter.max_entries`, `CycleSampleCache` TTL 2 s, HMI 720×64 | `CycleSampleCache._last` no tiene `maxsize` duro (sí TTL) |
| **L** | Liberación consistente entre implementaciones | TagObserver, MachineObserver y alarmas: `detach` pone `_subject = None`; MachineObserver.`release()` suelta `machine` | — |
| **I** | No retener lo que no se necesita | `delete_tag` itera observers sin discriminar tipo | — |
| **D** | Ciclo de vida, no el usuario | El tag/máquina/alarma que hizo attach hace detach | Si una máquina sigue con `ProcessType.tag` tras `delete_tag`, esa raíz es de configuración, no del observer |

No hay `__del__` en `Tag` / observers: los ciclos Tag ↔ Observer **sí** son recolectables por el GC cíclico de CPython, **si** no queda una raíz (CVT, máquina, alarma). El problema es la raíz, no el ciclo.

---

## 4. Hallazgos

| ID | Sev. | CA | Hallazgo | Evidencia | Impacto en 24/7 |
|---|---|---|---|---|---|
| **MEM-PY-1** | ~~Media~~ **Cerrado** | CA-MEM-3 | `delete_tag` no `detach` observers | `Tag.detach_all_observers()` antes del `pop`. Tests: `test_observer_lifecycle`. | — |
| **MEM-PY-2** | ~~Media~~ **Cerrado** | CA-MEM-3 | `unsubscribe_to` no detach `MachineObserver` | `tag.detach_machine(self)` + `MachineObserver.release()`. Rama `default_tag_name` corregida. | — |
| **MEM-PY-3** | Baja | CA-MEM-4 | `CycleSampleCache._prune_locked` solo por TTL, no por tag eliminado | `persistence/cycle_dedupe.py`: borra si `seen < now - 2s`. | Tras `delete_tag`, la entrada muere en ≤ 2 s. No es fuga; el criterio literal «verificar `tag.exists`» no se cumple. |
| **MEM-PY-4** | Baja | CA-MEM-6 | `AsyncStateMachineWorker.drop` no quita de `_machines` | `drop()` hace `pop` de `_schedulers` + `sched.stop()`. `_machines` conserva la referencia. | Solo si se usa `drop()` en caliente. `stop()` de todos los schedulers **sí** setea `_stop`. Hilos `daemon=True`. |
| **MEM-PY-5** | Política | CA-MEM-8 | `tagHistory` se persiste en logout; no se vacía | **Decisión de producto** (2026-08-14): acotado 720×64, no se vacía. Documentado en `PERFORMANCE_RUNBOOK.md` §9. | No es unbounded. |
| **MEM-PY-6** | Baja | CA-MEM-5 | Listeners de módulo en `store.ts` | `beforeunload` + `visibilitychange` sin `removeEventListener`. | Vida = pestaña. Aceptable en singleton de store. |
| **MEM-PY-7** | Baja | CA-MEM-5 | `setTimeout` sin cleanup en Login/Signup | Login: 500 ms post-conexión BD; Signup: `navigate` en 0 ms. | Timer de milisegundos. No soak. |
| **MEM-PY-8** | Info | CA-MEM-6 | `LoggerWorker.run` es `while True` | Comprueba `stop_event` **después** de `replicate_once` + `sleep(_period)`. | `stop()` funciona; latencia de parada = periodo del worker. Mensaje de log dice «Alarm worker» (cosmético). |

### Lo que está bien (no son hallazgos)

- `Tag.attach` / `detach` ponen `_subject` / `None` — contrato correcto si alguien lo llama.
- DAS: `reset_client` hace `pop` del cliente y `unsubscribe` de cada monitored item.
- `Buffer`: `deque(maxlen)`; resize recrea el deque.
- SAF ring y cap PENDING: backpressure, no crecimiento silencioso.
- `DedupeFilter`: `OrderedDict` LRU + poda de ventanas de tasa.
- `LoggerWorker` y `MachineScheduler.run`: salen por `stop_event` / `_stop`.
- HMI: `useSocket`, `Machines`, `MachinesDetailed`, `Communications` polling, `StripChart`, `useMemoryWatchdog`, `useDatabaseStatus`, `RealTimeTrends`, `MainLayout`, `Header`, `SCADA` drag — cleanup presente.
- `useSocket` en logout: `disconnect`, `clearInterval`, `Map.clear()` de pending tags/history/alarms/machines.

---

## 5. Ciclo de vida de objetos críticos

| Objeto | Nace | Vive | Debe morir | ¿Muere? |
|---|---|---|---|---|
| `Tag` | `create_tag` / carga BD | CVT `_tags`, DAS buffer, `ProcessType.tag` | `delete_tag` | Sale del CVT y DAS; observers detach. Vive si una máquina **sigue** suscrita (`ProcessType.tag`) — eso es config, no observer huérfano. |
| `TagObserver` | `DBManager.attach` (un observer por tag) | `tag._observers` | `detach_all_observers` / `delete_tag` | **Sí.** |
| `MachineObserver` | `StateMachine.attach` | `tag._observers` + `machine` | `unsubscribe_to` → `detach_machine` + `release()` | **Sí.** |
| `Alarm` | `create_alarm` | `_alarms` + observer en tag | `delete_alarm` | **Sí**: `detach_from_tag` + detach queue observer. |
| `Buffer` (tag/DAS) | create / subscribe OPC | deque fijo | `pop` / GC del tag | Sí en `delete_tag`. |
| Subscription OPC | `subscribe` | `monitored_items[client][key]` | `unsubscribe` / `reset_client` | Sí. |
| Journal PENDING | `enqueue` | SQLite + ring RAM | ACK replicación / cap | Acotado. No es leak; es backlog. |
| Hilo `SchedThread` | `AsyncStateMachineWorker.run` | daemon | `scheduler.stop()` → `_stop` | Sí, al acabar `run()`. |

Referencias circulares **esperadas**: `Tag` → `_observers` → `Observer._subject` → `Tag`; `MachineObserver.machine` → `ProcessType.tag` → `Tag`. Sin `__del__`, el GC cíclico las recoge **cuando no hay raíz**. objgraph en soak (CA-MEM-7) debe listar cuántos `Tag` vivos vs `CVT_TAG_COUNT`.

---

## 6. Criterios de aceptación (CA-MEM)

| ID | Criterio | Resultado | Notas |
|---|---|---|---|
| **CA-MEM-1** | RSS < 5 % en 24 h en régimen estable | **Pendiente soak** | `/api/health/system` → `RSS_MB`. |
| **CA-MEM-2** | Conteo Tag / Alarm / Machine / Buffer estable | **Pendiente soak** / **OK estático** | `CVT_TAG_COUNT`, `ALARM_COUNT`, `TAG_OBSERVER_COUNT`, `MACHINE_OBSERVER_COUNT`. |
| **CA-MEM-3** | TagObserver y MachineObserver detach al eliminar | **PASS** | Tests `test_observer_lifecycle`. |
| **CA-MEM-4** | CycleSampleCache poda tags eliminados | **PASS práctico / FAIL literal** | TTL 2 s. No hay `tag.exists`. |
| **CA-MEM-5** | Todo `setInterval` / `addEventListener` con cleanup | **PASS** con excepciones documentadas | MEM-PY-6, MEM-PY-7. |
| **CA-MEM-6** | `LoggerWorker` y `SchedThread` paran en `stop()` | **PASS** | MEM-PY-4/8 menores. |
| **CA-MEM-7** | Sin ciclos huérfanos en objgraph (objetos de negocio) | **Pendiente soak** | Tras detach, el recuento de `Tag` vivos debe coincidir con el catálogo. |
| **CA-MEM-8** | Política `tagHistory` | **PASS (política)** | Acotado 720×64; **no** se vacía en logout. Ver runbook §9. |
| **CA-MEM-9** | Observers vs catálogo | **Instrumentado** | `TAG_OBSERVER_COUNT` es la **suma** de observers (puede ser > `CVT_TAG_COUNT`). Invariante: estable si el catálogo es fijo. |
| **CA-MEM-10** | `MACHINE_OBSERVER_COUNT` estable sin cambio de config | **Instrumentado** | Soak. |

**Certificado «memoria estable A+»:** ciclo de vida **cerrado**. RSS 24 h (**CA-MEM-1**) pendiente de soak.

---

## 7. Métricas ya expuestas vs Fase 6

`GET /api/health/system` hoy:

| Campo | Útil para memoria |
|---|---|
| `RSS_MB` | CA-MEM-1 |
| `THREAD_COUNT` | hilos zombies |
| `OPC_MONITORED_COUNT` / `OPC_SUBSCRIPTION_COUNT` | DAS |
| `CVT_TAG_COUNT` | catálogo |
| `ALARM_COUNT` | alarmas |
| `PENDING_ROWS` / `SAF_PENDING_CAP_HITS` | journal RAM+disco |
| `CVT_LOCK_CONTENTION` | no es leak; es CPU |
| `POOL_CONNECTIONS_USED` | 0 sin pool (ver auditoría BD) |
| `TAG_OBSERVER_COUNT` | suma de observers (CA-MEM-9); puede ser > `CVT_TAG_COUNT` |
| `MACHINE_OBSERVER_COUNT` | CA-MEM-10 |

Opcional aún no expuesto: `DAS_BUFFER_KEYS` vs `CVT_TAG_COUNT`, `CYCLE_CACHE_SIZE`, `ASYNC_SCHEDULER_COUNT`.

Alertar si `TAG_OBSERVER_COUNT` o `MACHINE_OBSERVER_COUNT` crecen con catálogo fijo.

---

## 8. Plan de soak (Fase 4 / 7) — no ejecutado

Régimen: gunicorn `GeventWebSocketWorker`, 1 worker, catálogo real, HMI abierta con RT Trends.

1. Arranque: snapshot `tracemalloc`, `RSS_MB`, conteos health, `gc.get_count()`.
2. t=0 / 1 h / 24 h / 48 h: mismos snapshots; `objgraph.most_common_types(30)` y `objgraph.by_type('Tag')`.
3. Criterio CA-MEM-1: `(RSS_24h - RSS_1h) / RSS_1h < 0.05` (descartar la primera hora de warmup: numpy, OPC, FiPy del producto).
4. Criterio CA-MEM-2: `|Tag|_24h ≈ CVT_TAG_COUNT`; `|Alarm|` estable salvo altas reales.
5. Prueba de ciclo de vida (corta): crear tag → attach → `delete_tag` → `gc.collect()` → el `Tag` no debe quedar vivo si no hay `ProcessType.tag`. Cubierto en unit test con `weakref`.
6. HMI Chrome: heap snapshot al login, a las 4 h, logout, re-login. `tagHistory` ≤ 720×64.

Herramientas: `tracemalloc`, `objgraph`, `gc`, `/api/health/system`, Chrome DevTools (HMI). Valgrind/libpq solo si RSS crece y `PENDING_ROWS`/`CVT` están planos (entonces no es Python de negocio).

---

## 9. Correcciones aplicadas / residuales

**Aplicado (2026-08-14):** MEM-PY-1, MEM-PY-2, métricas health, política CA-MEM-8 documentada.

**Residual P2:**

1. `drop()`: `self._machines.remove(machine)`.
2. `CycleSampleCache.invalidate(tag_name)` desde `delete_tag` (higiene; el TTL ya cubre).
3. Opcional: rechazar `delete_tag` si alguna máquina tiene `ProcessType.tag is tag` (simétrico a «tag tiene alarma»).

---

## 10. Archivos clave

| Área | Ruta |
|---|---|
| Tag observers | `automation/tags/tag.py` (`detach_all_observers` / `detach_machine` / `release`) |
| Tests ciclo de vida | `automation/tests/test_observer_lifecycle.py` |
| CVT delete | `automation/tags/cvt.py` `delete_tag` |
| API delete tag | `automation/core.py` `delete_tag` / `unsubscribe_opcua` |
| Alarmas | `automation/managers/alarms.py` `delete_alarm` |
| DB attach | `automation/managers/db.py` `attach` |
| Máquina attach/unsub | `automation/state_machine.py` |
| DAS | `automation/opcua/subscription.py` |
| Buffer | `automation/buffer.py` |
| SAF cache | `automation/persistence/cycle_dedupe.py` |
| Journal caps | `automation/persistence/config.py` |
| Workers | `automation/workers/logger.py`, `automation/workers/state_machine.py` |
| Logs | `automation/utils/log_filters.py` |
| Health | `automation/modules/health/resources/health.py` |
| HMI socket | `hmi/src/hooks/useSocket.ts` |
| HMI historial | `hmi/src/store/slices/tagsSlice.ts` |
| HMI store listeners | `hmi/src/store/store.ts` |

---

## 11. Conclusión

El ciclo de vida de observers está **cerrado**: cada attach tiene su detach. Las colecciones calientes siguen acotadas. `tagHistory` acotado sin vaciar en logout es política de producto.

Lo que falta para firmar A+ de memoria estable es el **soak 24 h** (CA-MEM-1/2/7/10): RSS plano y conteos de observers estables con catálogo fijo.

Si el RSS de planta sube cientos de MB/día con `TAG_OBSERVER_COUNT` plano, no es este gap: mirar SAF, fragmentación o RTTM/FiPy en el producto.
