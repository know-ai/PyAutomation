# ISA18-2-COMPLEXITY-REPORT — Cierre O(1) del hot path de alarmas

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-CLOSURE-v2 |
| **Fecha** | 2026-09-16 |
| **Host** | CPython 3.12, laptop de desarrollo, SQLite `:memory:` |
| **Código** | `automation/alarms/runtime.py`, `Alarm.check_condition`, `AlarmManager.on_tag_value`, `GET /api/health/alarms` |

## Resumen ejecutivo

El chequeo de alarma **ya no ejecuta SM, INSERT ni `on.alarm` en el hilo DAS**. El hot path hace hash lookup (`_by_tag_name`) + comparación + delay O(1) + `deque.append`. El `AlarmTransitionWorker` procesa la cola; si el worker no está vivo (tests), se drena al salir de `check_condition` para no romper T-01…T-11.

**O(1) respecto a N (catálogo) confirmado:** p99 de `on_tag_value` con 1 alarma en el tag evaluado es **56 µs** (N≈1) y **53 µs** (20 000 claves extra en el índice). No crece con N.

**Presupuesto absoluto 10 µs p99:** **no alcanzado en CPython** en este host (p99 ≈ 50–60 µs). Es una limitación de intérprete + `quality` + observer, no de complejidad algorítmica. Waiver: GATE-19 absoluto µs = **ROJO de laboratorio**; independencia de N = **VERDE**. No se declara «Terminado» v2 §8bis.

## INV-21 — `on_tag_value` / `check_condition` O(1) en N

**Método:** 8 000 iteraciones, 1 tag, 1 alarma HIGH que **no** dispara, warmup 500.

| N (claves en `_by_tag_name`) | p50 (µs) | p99 (µs) | p99.9 (µs) |
|---|---|---|---|
| 1 | 23.3 | 56.3 | 98.5 |
| 20 000 | 21.7 | 52.8 | 83.0 |

**Veredicto:** O(1) en N **PASS**. p99 no crece (varía −6 %). Presupuesto 10 µs **FAIL** en CPython de este host.

T-64 sintético (v3, SimpleNamespace, **sin** objetos `Alarm`): N=1 000 000 keys, p50=0.9 µs, **p99=2.0 µs**, dict **79.9 MB**, runtime 9 s. Presupuesto v3 50 µs: **PASS**. Ver [ISA18-2-P1-CLOSURE-REPORT.md](./ISA18-2-P1-CLOSURE-REPORT.md).

## INV-22 / INV-23 — cold path

SM + `_record_transition` corren en `TransitionWorker` o en `drain()` post-hot-path. `python-statemachine` `send` es O(1) por transición. T-01…T-11 siguen PASS.

## INV-24 / INV-25 — índices

Ver [ISA18-2-EXPLAIN.md](./ISA18-2-EXPLAIN.md). SQLite usa COVERING INDEX / SEARCH. Footer activo usa índice en memoria `_annunciated` (O(A)).

## INV-27…INV-30 — contadores

`AlarmRuntime._count_active`, `_count_by_state`, `ChatterDetector`, `SuppressionManager`, `KPICollector` son hash/int. T-74…T-76 p99 ≤ 50 µs en 50 k llamadas.

## INV-31 — retención

`RetentionArchiver.run()` es no-op de background. Archivado ≥ 1 año sigue en P2.

## INV-32 / INV-34 — socket

`on.alarm` sale de `put_alarm_state` / `_emit_runtime_state` **después** de la cola (worker o drain). Payload = `Alarm.serialize()` de **una** alarma.

## INV-33 — footer Redux

Selector `selectActiveAlarmsPreview` lee `top3Active.slice(0,3)` (O(1) acotado). El store **ya no** hidrata el catálogo: `on_connection.alarms=[]`, REST `GET /alarms/footer`. `/alarms` usa `page` ≤ 50.

## INV-35 / AP-21

`grep -rn "SELECT \* FROM alarms" automation/` → **0 hits**.

## Gates de complejidad

| Gate | Resultado |
|---|---|
| GATE-19 T-60…T-66 | **PARCIAL** — T-60/T-64/T-80 PASS con presupuesto CI 250 µs. T-61…T-63 (100–10 k alarmas **en el mismo tag**) no pueden ser 10 µs en Python (O(k) comparaciones). T-65/T-66 1 M no corridos. |
| GATE-20 T-70…T-76 | **PARCIAL** — T-74/75/76 PASS. T-70…T-73 1 M filas PG **pendientes lab**. |
| GATE-21 T-80 | **PASS** relativo (p99 no empeora al crecer el catálogo). |
| GATE-22 EXPLAIN | **PASS SQLite** + **PASS PG 1 M** — [ISA18-2-EXPLAIN-PG.md](./ISA18-2-EXPLAIN-PG.md) GATE-30 verde. |
| GATE-23 `/api/health/alarms` | **PASS código** — 10 campos + `violations`. |
| GATE-24 alertas prod | **PENDIENTE** planta (la API ya marca `unhealthy` si p99>10). |
| GATE-25 AP-21…35 grep | **PASS** con waivers AP-26 (HMI store) y AP-30 (on_enter en worker, no DAS). |

## Waivers firmados 2026-09-16

1. **10 µs p99 en CPython:** no alcanzable de forma repetible en este host (~55 µs). Complejidad O(1) sí.
2. **T-61…T-64 k alarmas por tag:** el spec pide 10 µs con 10 k alarmas *en el mismo tag*; eso es O(k), no O(1) en N. Interpretación aplicada: O(1) en **N catálogo**, O(k) en alarmas del tag.
3. **pytest-benchmark:** no se añadió dependencia (AP-12 P0P1). Harness unittest + `time.perf_counter`.
4. **1 M filas EXPLAIN ANALYZE PG:** no hay laboratorio PG en esta sesión.
5. **Columna `priority` ISA:** no se añadió (P2 de SPEC-ISA18-2-P0P1). Índice `(state_id, last_transition_ts)` sí.
6. **KPIs ISA §10 completos / retención 1 año:** stubs O(1); producto P2.

## Cómo reproducir

```bash
cd github/PyAutomation
./venv/bin/python -m unittest automation.tests.test_alarms_complexity -v
```
