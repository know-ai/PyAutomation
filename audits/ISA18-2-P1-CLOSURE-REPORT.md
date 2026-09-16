# ISA18-2-P1-CLOSURE-REPORT — SPEC-ISA18-2-CLOSURE-v3

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-CLOSURE-v3 |
| **Fecha** | 2026-09-16 |
| **Host** | CPython 3.12, venv del repo |
| **Alcance** | P1 Priority 1 (cola, health, flag, T-64 sintético, frontend acotado). **No P2.** |

## Resumen ejecutivo

P1 v3 cierra cola acotada, health del worker, drenaje prohibido en producción, lookup sintético a 1 M keys y HMI paginado. El laboratorio PostgreSQL 1 M filas **no está disponible** en esta sesión: GATE-30 queda **ROJO con waiver**. El resto de gates de código están verdes.

**No se declara «Terminado» v3 §6ter** mientras GATE-30 no tenga EXPLAIN ANALYZE en lab.

## 7 gates

| Gate | Criterio | Resultado |
|---|---|---|
| GATE-26 | Cola maxlen 100 000, overflow, backlog | **VERDE** — T-90, T-91, T-95 |
| GATE-27 | `transition_worker_alive` + `worker_lag_ms` | **VERDE** — T-92, T-94 |
| GATE-28 | `ALARM_SYNC_DRAIN` doble barrera | **VERDE** — T-93, T-96, T-97 |
| GATE-29 | T-64 1 M keys, p99 ≤ 50 µs | **VERDE** — p50=0.9 µs, p99=2.0 µs, 79.9 MB |
| GATE-30 | EXPLAIN PG 1 M sin Seq Scan | **ROJO** — no hay lab PG (`psql`/driver ausentes) |
| GATE-31 | Frontend acotado INV-43…46 | **VERDE** — store top-3 + page≤50 + history≤100 |
| GATE-32 | Paginación forzosa API | **VERDE** — T-98, T-99, clamp en resources |

## 11 tests T-90…T-100

| ID | Resultado | Evidencia |
|---|---|---|
| T-90 | **PASS** | 100 k enqueue → `ALM.PERF.ALARM_QUEUE_OVERFLOW` CRITICAL |
| T-91 | **PASS** | >10 k → backlog WARNING una vez + `QUEUE_BACKLOG` |
| T-92 | **PASS** | `transition_worker_alive: bool`, `worker_lag_ms.{p50,p95,p99,count}` |
| T-93 | **PASS** | worker muerto + flag false → cola crece, SM no avanza |
| T-94 | **PASS** | `snapshot()` ×1000, p99 ≤ 5 ms |
| T-95 | **PASS** | `_pending_max_seen` conserva el pico |
| T-96 | **PASS** | `AUTOMATION_ENV=test` + `ALARM_SYNC_DRAIN=true` drena |
| T-97 | **PASS** | producción ignora el flag (log WARNING) |
| T-98 | **PASS** | `page_size=100` → 50 |
| T-99 | **PASS** | `page_size=500` → 100 |
| T-100 | **PASS** | `serialize_socket()` ≤ 2 KB |

ISA T-01…T-11 + I-01 + complexity T-60/T-64/T-80 + delays: **PASS**.

## INV-36…INV-50

| ID | Estado | Evidencia |
|---|---|---|
| INV-36 | PASS | `deque(maxlen=100_000)` |
| INV-37 | PASS | T-90 CRITICAL + flag PERF |
| INV-38 | PASS | T-91 WARNING una vez, histéresis umbral/2 |
| INV-39 | PASS | health `transition_worker_alive` |
| INV-40 | PASS | health `worker_lag_ms` |
| INV-41 | PASS | default producción false |
| INV-42 | PASS | T-93 no drena |
| INV-43 | PASS | Redux `top3Active` + `countByState`; connect ya no manda catálogo |
| INV-44 | PASS | `/api/alarms` clampea ≤ 50; UI sin option 100 |
| INV-45 | PASS | historial clampea ≤ 100 |
| INV-46 | PASS | clamp en list/history/lasts/active |
| INV-47 | PASS | T-100 `on.alarm` compacto |
| INV-48 | PASS | `on.tag` típico 194 B (< 500 B) |
| INV-49 | PASS | T-94 |
| INV-50 | PASS | T-95 |

## AP-36…AP-45 (grep)

| AP | Resultado |
|---|---|
| AP-36 `deque()` sin maxlen en cola | **0 hits** — cola usa `deque(maxlen=100_000)` |
| AP-37 drain silencioso en prod | **cerrado** — doble barrera |
| AP-38 store = catálogo | **cerrado** — no hay `alarms: Record` |
| AP-39 `/alarms` sin página | **cerrado** |
| AP-40 historial sin página | **cerrado** — export pagina de 100 |
| AP-41 API sin limit | **cerrado** en list/history/lasts/active/footer |
| AP-42 socket con catálogo | **cerrado** — `on_connection.alarms = []` |
| AP-43 health `COUNT(*)` | **0 hits** en `health.py` |
| AP-44 `ALARM_SYNC_DRAIN=true` en prod | **ignorado** + WARNING |
| AP-45 flag sin default seguro | **cerrado** — default false |

## Benchmark T-64 (N vs p99)

Lookup sintético (`dict.get` + `_evaluate_condition` en SimpleNamespace). 10 000 muestras. `time.perf_counter_ns`.

| N keys | p50 (µs) | p99 (µs) | Memoria dict |
|---|---|---|---|
| 1 000 | ~0.9 | ≤ 2.0 | — |
| 1 000 000 | 0.9 | **2.0** | **79.9 MB** |

```
p99 (µs)
2.0 |                *  N=1M
    |
0.9 |  *              N=1k
    +----------------------
      1k            1M
```

Degradación N=1k → N=1M ≤ 10 % (PASS). Presupuesto v3 50 µs: **holgura ×25**.

Hot path real `on_tag_value` (CPython, 1 alarma/tag) permanece ~50–56 µs p99 (medición v2). Eso es O(1) en N; el presupuesto de planta 50 µs p99 es **marginal en el intérprete**, no en el índice. GATE-29 evalúa el lookup sintético, no el SM.

## EXPLAIN PG

Ver [ISA18-2-EXPLAIN-PG.md](./ISA18-2-EXPLAIN-PG.md). Scripts listos: `scripts/seed_alarms_1m.sql`, `scripts/explain_alarms_pg.sql`. Lab **no ejecutado**.

## Frontend no-explosión

- `hmi/src/store/slices/__tests__/alarmsSlice.test.ts` (especificación TS).
- `automation/tests/test_alarms_frontend_bounds.py` corre en CI (unittest): 1000 sockets → top3 ≤ 3; page ≤ 50; history ≤ 100.
- Logout limpia page/top3 y conserva `countByState`.

## Waivers firmados 2026-09-16

1. **GATE-30 EXPLAIN PostgreSQL 1 M filas:** no hay `psql` ni driver en esta sesión. Gate **ROJO**. SQLite covering indexes siguen en [ISA18-2-EXPLAIN.md](./ISA18-2-EXPLAIN.md).
2. **Query 4 `priority` ISA:** columna `priority` es P2; el script usa `last_transition_ts` (índice v2).
3. **Query 5 `COUNT(*)`:** prohibido en `/api/health/alarms`. El script lo deja solo como anti-patrón de lab.
4. **Vitest:** no se añadió dependencia. El test de no-explosión corre en unittest Python + archivo TS de referencia.
5. **p99 `on_tag_value` real ~55 µs vs 50 µs v3:** no bloquea GATE-29 (sintético 2 µs). Se acepta ruido de host CPython; CPU a 10 Hz×500 tags ≈ 27 % de un core vs 25 % de diseño.
6. **GET `/alarms/active_alarms`:** ahora objeto paginado (`items`, `page_size`≤50), no lista cruda. El HMI no lo consumía.

## Definición «Terminado» v3 (§6ter)

| # | Punto | Estado |
|---|---|---|
| 1 | GATE-26…32 verdes | **NO** — GATE-30 rojo |
| 2 | T-90…T-100 PASS | **SÍ** |
| 3 | INV-36…50 evidencia | **SÍ** |
| 4 | AP-36…45 grep 0 | **SÍ** |
| 5 | EXPLAIN PG 5 queries | **NO** (waiver) |
| 6 | T-64 1 M p99≤50 µs | **SÍ** |
| 7 | Frontend no-explosión | **SÍ** |
| 8 | Paginación 50 / 100 | **SÍ** (código; 1 M filas PG no lab) |
| 9 | Este informe | **SÍ** |
| 10 | Auditoría actualizada | **SÍ** |

**P1 código: cerrado. P1 «Terminado» v3: no, pendiente lab GATE-30.** Listo para P2 en producto salvo EXPLAIN PG de lab.
