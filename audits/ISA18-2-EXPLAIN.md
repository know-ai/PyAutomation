# ISA18-2-EXPLAIN — índices de alarmas (GATE-22)

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **Motor** | SQLite `:memory:` (Peewee). PostgreSQL 1 M filas **pendiente lab**. |
| **Tabla real** | `alarms`, `alarmsummary` (Peewee no usa snake_case `alarm_summary`) |

`AlarmSummary.ensure_schema()` crea:

- `idx_alarmsummary_event_time (event_time)`
- `idx_alarmsummary_alarm_time (alarm_id, event_time)`
- `idx_alarmsummary_to_state (to_state, event_time)`
- `idx_alarms_tag (tag_id)`
- `idx_alarms_state_time (state_id, last_transition_ts)`

## Query 1 — historial reciente (INV-24)

```sql
SELECT id FROM alarmsummary ORDER BY event_time DESC LIMIT 3;
```

```
SCAN alarmsummary USING COVERING INDEX idx_alarmsummary_event_time
```

Sin SCAN de heap. LIMIT 3.

## Query 2 — historial por alarma (INV-24)

```sql
SELECT id FROM alarmsummary WHERE alarm_id = 1 ORDER BY event_time DESC LIMIT 20;
```

```
SEARCH alarmsummary USING COVERING INDEX idx_alarmsummary_alarm_time (alarm_id=?)
```

## Query 3 — por `to_state`

```sql
SELECT id FROM alarmsummary WHERE to_state = 'Unack Alarm' ORDER BY event_time DESC LIMIT 20;
```

```
SEARCH alarmsummary USING COVERING INDEX idx_alarmsummary_to_state (to_state=?)
```

## Query 4 — footer catálogo por estado (INV-25)

```sql
SELECT id FROM alarms WHERE state_id = 1 ORDER BY last_transition_ts DESC LIMIT 3;
```

```
SEARCH alarms USING COVERING INDEX idx_alarms_state_time (state_id=?)
```

El footer de runtime **no** ejecuta este SQL: usa `AlarmRuntime._annunciated` O(A).

## Nota PostgreSQL

GATE-22 con 1 M filas y `EXPLAIN ANALYZE` (Seq Scan = rojo) queda para el lab. Esta evidencia cubre el contrato de índices en el dialecto de tests.
