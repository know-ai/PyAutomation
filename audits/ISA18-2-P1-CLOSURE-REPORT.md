# ISA18-2-P1-CLOSURE-REPORT — v3 + SPEC-ISA18-2-PG-CLOSURE-v2

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-CLOSURE-v3 + SPEC-ISA18-2-PG-CLOSURE-v2 |
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Host** | CPython 3.12, venv del repo |
| **Lab** | `app_db` PG17 :32800 · Redis `compose-redis-session-1` · `opcua_simulator` :4840 |
| **Alcance** | P1 cola/health/HMI + cierre GATE-30 lab + E2E local. **No P2.** |

## Resumen ejecutivo

GATE-30 (EXPLAIN ANALYZE 1 M filas, 0 Seq Scan) está **VERDE**. Eso desbloqueaba el P1 v3 de código.

El ciclo ISA A→B→D→B→C→E produce **5 filas** con `check_condition` real. El simulador OPC **no permite escribir** PV. Redis **no** está en el hot path de alarmas (INV-64). Restart de `app_db` conserva el seed. Paginación OFFSET 450 = 2.92 ms.

**Terminado v3 pleno: NO** (gates E2E OPC-write / SAF-replay / Playwright / PK `event_time` no verdes).
**Terminado v3 con waivers firmados: SÍ** (§15 punto 1: verde o waiver con evidencia de intento).

## Gates GATE-22…GATE-38

| Gate | Descripción | Resultado |
|---|---|---|
| GATE-22-PG | Índices en PG real | **VERDE** — 5+ índices en `alarms`/`alarmsummary` |
| GATE-26 | Cola maxlen 100 000 | **VERDE** — T-90, T-91, T-95 |
| GATE-27 | worker alive + lag | **VERDE** — T-92, T-94 |
| GATE-28 | `ALARM_SYNC_DRAIN` | **VERDE** — T-93, T-96, T-97 |
| GATE-29 | T-64 1 M keys p99 ≤ 50 µs | **VERDE** — p99=2.0 µs |
| GATE-29b | T-64b N=500 Alarm reales | **VERDE** — p99=23.7 µs max=42.6 µs |
| GATE-30 | EXPLAIN PG 1 M sin Seq Scan | **VERDE** — Q1 0.10 ms … Q6 2.67 ms |
| GATE-31 | Frontend acotado | **VERDE** — store + unittest (Playwright waiver) |
| GATE-32 | Paginación API | **VERDE** — T-98/T-99 |
| GATE-32-PG | Paginación 1 M | **VERDE** — OFFSET 450 = 2.92 ms |
| GATE-33 | Partition readiness | **PARCIAL / waiver W-PG-06** — PK bigint, 0 FK; PK sin `event_time` |
| GATE-34 | E2E OPC ciclo | **PARCIAL / waiver W-PG-01** — read OK, write denied |
| GATE-35 | Hot path 100/500/1000 ms | **PARCIAL / waiver W-PG-02** — INV-55 PASS; CA-F6 50 µs FAIL |
| GATE-36 | Multiworker Redis | **VERDE (INV-64)** — 0 redis en runtime; 2 drainers 0 dup |
| GATE-37 | Restart PG | **PARCIAL / waiver W-PG-04** — seed sobrevive; SAF replay no |
| GATE-38 | Ciclo ISA 5 filas | **VERDE** SQLite; PG lab INSERT. SAF vivo waiver W-PG-05 |

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
| T-98 | **PASS** | `page_size=100` → 50 (también contra PG lab) |
| T-99 | **PASS** | `page_size=500` → 100 |
| T-100 | **PASS** | `serialize_socket()` ≤ 2 KB |

T-64b **PASS**. ISA T-01…T-11 + I-01 + T-60/T-64/T-80: **PASS** (sesión v3).

## INV-36…INV-65

INV-36…INV-50: **PASS** (cierre v3). INV-51…INV-65: tabla en [ISA18-2-E2E-REPORT.md](./ISA18-2-E2E-REPORT.md). Destacados: INV-54/55/57/62/64 **PASS**; INV-53/58/60/63 waiver.

## AP-36…AP-45 (grep) y AP-46…AP-65

AP-36…AP-45: **0 hits** (cierre v3). AP-46…AP-55 no están enumerados en el cuerpo de PG-CLOSURE-v2; los anti-patrones ejecutables de esta entrega son AP-56…AP-65:

| AP | Verificación |
|---|---|
| AP-56 E2E sin OPC | **evitado** — simulador healthy, lectura `FI_01=0.0` |
| AP-57 Redis DB compartida | **evitado** — `redis-cli -n 15` + FLUSHDB |
| AP-58 restart sin reconexión | **evitado** — wait ≤ 45 s; reconectó en 1.8 s |
| AP-59 hot path sin warmup | **parcial** — 50 muestras @ 100 ms; p99 estable vs p50 |
| AP-60 ignorar Seq Scan | **evitado** — analizador FAIL si Seq Scan |
| AP-61 E2E PASS sin PG | **evitado** — round-trip PG documentado; SAF vivo no se declara PASS |
| AP-62 multiworker sin aislamiento | **evitado** — runtime reset + db15 |
| AP-63 frontend sin eventos | **parcial** — 1000 eventos en reducer unittest; no Playwright |
| AP-64 waiver sin intento | **evitado** — cada waiver cita comando/error |
| AP-65 Terminado con gate rojo | **respetado** — no se declara Terminado pleno |

## Benchmarks

```
T-64  N=1M keys     p50=0.9µs  p99=2.0µs   mem=79.9MB
T-64b N=500 Alarm   p50=12.3µs p99=23.7µs  max=42.6µs
on_tag_value+OPC    100ms p99=106.4µs  500ms p99=68.8µs  1000ms p99=100.2µs
EXPLAIN Q1–Q4/Q6    0.10 / 0.22 / 0.18 / 0.06 / 2.67 ms   0 Seq Scan
OFFSET 450          2.92 ms
```

## Informes

- [ISA18-2-EXPLAIN-PG.md](./ISA18-2-EXPLAIN-PG.md) + dump [ISA18-2-EXPLAIN-PG-raw.txt](./ISA18-2-EXPLAIN-PG-raw.txt)
- [ISA18-2-E2E-REPORT.md](./ISA18-2-E2E-REPORT.md)
- [ISA18-2-PARTITION-PLAN.md](./ISA18-2-PARTITION-PLAN.md)
- [AUDIT_ISA18_2_ALARMS.md](./AUDIT_ISA18_2_ALARMS.md)

## Definición «Terminado» v3 (§15)

| # | Punto | Estado |
|---|---|---|
| 1 | GATE-26…38 verdes o waiver | **SÍ** — verdes + waivers W-PG-01…10 |
| 2 | T-90…T-100 PASS | **SÍ** |
| 3 | T-64b PASS o waiver | **SÍ** PASS |
| 4 | INV-36…65 evidencia | **SÍ** |
| 5 | AP-36…45 grep 0 | **SÍ** |
| 6 | AP-46…55 / 56…65 documentados | **SÍ** |
| 7 | EXPLAIN-PG.md output crudo | **SÍ** |
| 8 | E2E-REPORT.md | **SÍ** |
| 9 | Este informe | **SÍ** |
| 10 | PARTITION-PLAN.md | **SÍ** |
| 11 | AUDIT veredicto ≥ A−/A/A | **SÍ** — hot path **A−** / health **A** / frontend **A** |
| 12 | Waivers fecha+SHA+razón | **SÍ** |

**Declaración:** Terminado v3 **con waivers firmados**. No Terminado v3 pleno.
