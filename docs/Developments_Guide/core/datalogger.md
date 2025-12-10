# PyAutomation DataLogger

The DataLogger persistently records tag values from the CVT into the configured database (SQLite, MySQL, or PostgreSQL). It is built for continuous operation in multi-threaded environments and is orchestrated by the `LoggerWorker` background thread.

## Components

- **DataLogger**: Low-level API that performs CRUD on tag definitions and writes time-series values (`TagValue`).
- **DataLoggerEngine**: Thread-safe wrapper used by workers and state machines to call the logger without race conditions.
- **LoggerWorker**: Periodically drains the tag queue, writes batches to the database, handles backups for SQLite, and monitors OPC UA client connectivity.
- **DBManager**: Supplies connections and health checks; the logger short-circuits writes if connectivity is down.

## How It Works

1. CVT updates enqueue tag changes through `TagObserver`.
2. `LoggerWorker` runs on a fixed period (defaults to the `LOGGER_PERIOD` environment variable, 10s if unset).
3. The worker filters tags by `segment`/`manufacturer` (if configured) and bulk-inserts records via `TagValue.insert_many`.
4. When SQLite grows beyond 1 GB, the worker triggers a backup, vacuums the DB, and resumes logging.

### Data Logger Workflow

``` mermaid
flowchart TD
    A[CVT Tag Update] -->|TagObserver| B[Tag Queue]
    B -->|Periodic Check| C{LoggerWorker}
    C -->|Every LOGGER_PERIOD| D{DB Connected?}
    D -->|No| E[Reconnect Attempt]
    E -->|Success| D
    E -->|Fail| F[Skip Cycle]
    D -->|Yes| G[Filter by Segment/Manufacturer]
    G -->|Apply Deadband| H{Bulk Insert}
    H -->|Success| I[Database]
    H -->|Fail| J[Log Error]
    
    subgraph "SQLite Maintenance"
        I -->|Size > 1GB| K[Backup DB]
        K --> L[Vacuum DB]
        L --> M[Clear Historical Tables]
    end
```

### Data Logger Architecture

``` mermaid
graph LR
    subgraph "Data Sources"
        CVT[CVT Tags]
    end
    
    subgraph "Logger Engine"
        DLE[DataLoggerEngine]
        DL[DataLogger]
    end
    
    subgraph "Worker"
        LW[LoggerWorker]
        Queue[Tag Queue]
    end
    
    subgraph "Persistence"
        DB[(Database)]
    end
    
    CVT -->|TagObserver| Queue
    Queue -->|Drain| LW
    LW -->|Thread-safe| DLE
    DLE -->|CRUD Operations| DL
    DL -->|Bulk Insert| DB
```

## Configuring and Using the Logger

```python
from automation import PyAutomation

app = PyAutomation()
app.set_db(db_path="./db/app.db", db_type="sqlite")  # or postgres/mysql
app.set_log(history=True)  # enable history logging
app.run()  # starts LoggerWorker among other services

# Tags created in CVT are automatically registered for logging
```

Key settings:
- **LOGGER_PERIOD**: Interval (seconds) between logging cycles.
- **dead_band** on tags: Skip writes when changes are below the configured threshold.
- **display_unit**: Used for storage; ensure it matches operator-facing units to keep trends consistent.

## Reading Historical Data

`DataLogger` provides convenience methods to fetch trends and aggregates. Example:

```python
from automation.logger.datalogger import DataLogger

logger = DataLogger()
trend = logger.read_tags(tags=["TankLevel"], start="2024-10-01", end="2024-10-02")
```

Aggregation helpers (e.g., `group_by`) return averaged buckets with timestamps normalized to the configured timezone.

## Reliability and Maintenance

- The worker retries database connectivity (`reconnect_to_db`) and logs critical messages when reconnection succeeds or fails.
- SQLite installations get automatic backups under `db/backups/` when size > 1 GB; historical tables are pruned to keep the DB lean after backup.
- OPC UA client health is checked each cycle to keep field links alive.

## Best Practices

- Enable history only for tags that need trending; unnecessary logging increases storage and IO.
- Set meaningful `dead_band` values for noisy signals to reduce churn.
- Keep `display_unit` stable—changing it mid-stream complicates downstream analytics.
- Prefer batching tag writes (`write_tags`) if you log from custom code; it mirrors the worker’s efficient path.

## Troubleshooting

- **No data written**: Verify `set_log(history=True)` is called and `DBManager.check_connectivity()` returns True.
- **Deadband drops expected points**: Lower the tag’s `dead_band` or disable it for critical signals.
- **SQLite growth**: Check backup folder for recent dumps; ensure the worker has permission to write to `db/backups`.
- **Stale OPC UA data**: Inspect `LoggerWorker.check_opcua_connection`; reconnect logic depends on clients being registered in `OPCUAClientManager`.
