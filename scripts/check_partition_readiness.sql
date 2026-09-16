-- GATE-33 partition readiness for alarmsummary.

SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS type
FROM pg_index i
JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
WHERE i.indrelid = 'alarmsummary'::regclass AND i.indisprimary;

SELECT conname, contype FROM pg_constraint
WHERE conrelid = 'alarmsummary'::regclass;

SELECT
    pg_size_pretty(pg_total_relation_size('alarmsummary')) AS total,
    pg_size_pretty(pg_relation_size('alarmsummary')) AS data,
    pg_size_pretty(pg_indexes_size('alarmsummary')) AS indexes;

SELECT conname, conrelid::regclass AS from_table, confrelid::regclass AS to_table
FROM pg_constraint
WHERE confrelid = 'alarmsummary'::regclass;
