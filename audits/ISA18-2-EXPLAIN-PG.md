# ISA18-2-EXPLAIN-PG — GATE-30 (SPEC-ISA18-2-CLOSURE-v3 P1-5)

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **Lab** | **No disponible** (sin `psql`, sin `psycopg`, sin instancia PG en la sesión) |
| **Scripts** | `scripts/seed_alarms_1m.sql`, `scripts/explain_alarms_pg.sql` |
| **Veredicto** | GATE-30 **FAIL / ROJO** — waiver de laboratorio |

## Output crudo EXPLAIN ANALYZE

No hay. Las cinco queries no se ejecutaron.

## pg_stat_statements

No hay captura antes/después.

## Veredicto por query

| Query | Plan esperado | Resultado |
|---|---|---|
| Q1 historial reciente LIMIT 3 | Index Only / Index Scan | **FAIL** — no corrido |
| Q2 por `alarm_id` LIMIT 20 | Index Scan `idx_summary_alarm_time` | **FAIL** — no corrido |
| Q3 por `to_state` LIMIT 20 | Index Scan `idx_summary_to_state` | **FAIL** — no corrido |
| Q4 footer | Index Scan (sin columna `priority`; P2) | **FAIL** — no corrido |
| Q5 `COUNT(*)` | N/A en runtime (AP-43) | **N/A** — prohibido en `/api/health/alarms` |

SQLite equivalente (índices covering) permanece **PASS** en [ISA18-2-EXPLAIN.md](./ISA18-2-EXPLAIN.md).

## Waiver

Firmado 2026-09-16: GATE-30 no puede ponerse verde sin lab. Re-ejecutar los scripts contra un PostgreSQL con esquema Peewee (`alarms`, `alarmsummary`) y pegar el JSON de `EXPLAIN (ANALYZE, BUFFERS)` en este archivo para cerrar el gate.
