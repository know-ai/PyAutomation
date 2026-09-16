-- SPEC-ISA18-2-PG-CLOSURE-v2 — EXPLAIN ANALYZE (GATE-30).
-- Run after scripts/seed_alarms_pg_1m.sql.

-- Q1: historial reciente (INV-24)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed ORDER BY event_time DESC LIMIT 3;

-- Q2: historial por alarma (INV-24)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed
WHERE alarm_id = 42 ORDER BY event_time DESC LIMIT 20;

-- Q3: por to_state (INV-24)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed
WHERE to_state = 'Unack Alarm' ORDER BY event_time DESC LIMIT 20;

-- Q4: footer catálogo (sin columna priority — P2). Índice state_id + last_transition_ts.
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, name, state_id, last_transition_ts
FROM alarms_seed
WHERE state_id = 1
ORDER BY last_transition_ts DESC
LIMIT 3;

-- Q5: COUNT(*) anti-patrón AP-43 / INV-27. No usar en /api/health/alarms.
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT COUNT(*) FROM alarmsummary_seed;

-- Q6: paginación OFFSET bajo carga (GATE-32-PG)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed
ORDER BY event_time DESC OFFSET 450 LIMIT 100;
