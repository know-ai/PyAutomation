-- SPEC-ISA18-2-PG-CLOSURE-v2 — schema lab + 500 alarmas + 1M historial.
-- Contenedor local: app_db (PostgreSQL 17) database app_db, puerto host 32800.
-- Las tablas de producto no existían (DB vacía). Se crean con columnas ISA v2.

CREATE TABLE IF NOT EXISTS alarms (
    id BIGSERIAL PRIMARY KEY,
    identifier VARCHAR(64) UNIQUE,
    name VARCHAR(128) UNIQUE,
    area VARCHAR(64),
    tag_id BIGINT,
    trigger_type_id BIGINT,
    trigger_value DOUBLE PRECISION,
    description VARCHAR(256),
    state_id BIGINT,
    timestamp TIMESTAMP,
    last_transition_ts TIMESTAMP,
    last_transition_from VARCHAR(24),
    last_transition_to VARCHAR(24),
    on_delay DOUBLE PRECISION,
    off_delay DOUBLE PRECISION,
    on_delay_units VARCHAR(16),
    off_delay_units VARCHAR(16)
);

CREATE TABLE IF NOT EXISTS alarmsummary (
    id BIGSERIAL PRIMARY KEY,
    alarm_id BIGINT,
    state_id BIGINT,
    alarm_time TIMESTAMP,
    ack_time TIMESTAMP,
    area VARCHAR(64),
    sample_uuid VARCHAR(255),
    from_state VARCHAR(24),
    to_state VARCHAR(24),
    event_time TIMESTAMP,
    operator_id INTEGER,
    condition_met BOOLEAN,
    condition_value DOUBLE PRECISION,
    schema_version INTEGER
);

CREATE INDEX IF NOT EXISTS idx_alarms_tag ON alarms (tag_id);
CREATE INDEX IF NOT EXISTS idx_alarms_state_time ON alarms (state_id, last_transition_ts);
CREATE INDEX IF NOT EXISTS idx_alarmsummary_event_time ON alarmsummary (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_alarmsummary_alarm_time ON alarmsummary (alarm_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_alarmsummary_to_state ON alarmsummary (to_state, event_time DESC);

-- 500 alarmas de catálogo
INSERT INTO alarms (identifier, name, area, tag_id, trigger_type_id, trigger_value, description, state_id, last_transition_ts)
SELECT
    'alm' || lpad(i::text, 5, '0'),
    'ALM.SEED.' || lpad(i::text, 5, '0'),
    'Linea' || ((i % 5) + 1)::text,
    i,
    1,
    50.0,
    'seed',
    ((i % 5) + 1),
    NOW() - (i || ' minutes')::interval
FROM generate_series(1, 500) AS i
ON CONFLICT (name) DO NOTHING;

TRUNCATE alarmsummary;

INSERT INTO alarmsummary (
    alarm_id, state_id, alarm_time, from_state, to_state, event_time,
    operator_id, condition_met, condition_value, area, sample_uuid, schema_version
)
SELECT
    (random() * 499 + 1)::bigint,
    (random() * 4 + 1)::bigint,
    NOW() - (random() * INTERVAL '365 days'),
    (ARRAY['Normal','Unack Alarm','Ack Alarm','RTN Unack','Cleared'])[floor(random() * 5 + 1)],
    (ARRAY['Normal','Unack Alarm','Ack Alarm','RTN Unack','Cleared'])[floor(random() * 5 + 1)],
    NOW() - (random() * INTERVAL '365 days'),
    CASE WHEN random() > 0.5 THEN (random() * 10 + 1)::int ELSE NULL END,
    random() > 0.5,
    random() * 100,
    'Linea' || floor(random() * 5 + 1),
    gen_random_uuid()::text,
    2
FROM generate_series(1, 1000000);

DROP TABLE IF EXISTS alarms_seed;
DROP TABLE IF EXISTS alarmsummary_seed;
CREATE TABLE alarms_seed (LIKE alarms INCLUDING ALL);
CREATE TABLE alarmsummary_seed (LIKE alarmsummary INCLUDING ALL);
INSERT INTO alarms_seed SELECT * FROM alarms;
INSERT INTO alarmsummary_seed SELECT * FROM alarmsummary;

CREATE INDEX IF NOT EXISTS idx_summary_event_time ON alarmsummary_seed (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_summary_alarm_time ON alarmsummary_seed (alarm_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_summary_to_state ON alarmsummary_seed (to_state, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_alarms_seed_state_time ON alarms_seed (state_id, last_transition_ts);

ANALYZE alarms;
ANALYZE alarmsummary;
ANALYZE alarms_seed;
ANALYZE alarmsummary_seed;

SELECT
    (SELECT COUNT(*) FROM alarms) AS alarms_n,
    (SELECT COUNT(*) FROM alarmsummary) AS summary_n,
    (SELECT COUNT(*) FROM alarms_seed) AS alarms_seed_n,
    (SELECT COUNT(*) FROM alarmsummary_seed) AS summary_seed_n;
