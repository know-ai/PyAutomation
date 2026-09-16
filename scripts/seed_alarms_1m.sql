-- SPEC-ISA18-2-CLOSURE-v3 P1-5 — seed 1M history rows (lab only).
-- Tables are Peewee names: alarms, alarmsummary.
-- Requires PostgreSQL with gen_random_uuid() (pgcrypto or PG 13+).

CREATE TABLE IF NOT EXISTS alarms_seed (LIKE alarms INCLUDING ALL);
CREATE TABLE IF NOT EXISTS alarmsummary_seed (LIKE alarmsummary INCLUDING ALL);

INSERT INTO alarmsummary_seed (
    alarm_id, from_state, to_state, event_time, operator_id,
    condition_met, condition_value, area, sample_uuid, schema_version
)
SELECT
    (random() * 499 + 1)::bigint,
    (ARRAY['Normal','Unack Alarm','Ack Alarm','RTN Unack','Cleared'])[floor(random() * 5 + 1)],
    (ARRAY['Normal','Unack Alarm','Ack Alarm','RTN Unack','Cleared'])[floor(random() * 5 + 1)],
    NOW() - (random() * INTERVAL '365 days'),
    CASE WHEN random() > 0.5 THEN (random() * 10 + 1)::bigint ELSE NULL END,
    random() > 0.5,
    random() * 100,
    'Linea' || floor(random() * 5 + 1),
    gen_random_uuid(),
    2
FROM generate_series(1, 1000000);

CREATE INDEX IF NOT EXISTS idx_summary_event_time  ON alarmsummary_seed(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_summary_alarm_time  ON alarmsummary_seed(alarm_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_summary_to_state    ON alarmsummary_seed(to_state, event_time DESC);

ANALYZE alarmsummary_seed;
ANALYZE alarms_seed;
