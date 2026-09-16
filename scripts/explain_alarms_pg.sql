-- SPEC-ISA18-2-CLOSURE-v3 P1-5 — EXPLAIN ANALYZE (lab only).
-- Run after scripts/seed_alarms_1m.sql.

-- Query 1: historial reciente (INV-24)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed ORDER BY event_time DESC LIMIT 3;

-- Query 2: historial por alarma (INV-24)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed
WHERE alarm_id = 42 ORDER BY event_time DESC LIMIT 20;

-- Query 3: por to_state (INV-24)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM alarmsummary_seed
WHERE to_state = 'Unack Alarm' ORDER BY event_time DESC LIMIT 20;

-- Query 4: footer por estado + last_transition_ts (priority ISA is P2; not in schema)
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, name, state_id, last_transition_ts
FROM alarms_seed
ORDER BY last_transition_ts DESC
LIMIT 3;

-- Query 5: COUNT(*) is forbidden on /api/health/alarms (INV-27 / AP-43).
-- Do not execute COUNT(*) in the runtime health path.
-- This statement is lab-only to document the anti-pattern.
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT COUNT(*) FROM alarms_seed;
