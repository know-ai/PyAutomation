# Data Logger API

The Data Logger module is responsible for persisting historical data to the configured database (SQLite, PostgreSQL, etc.).

## Components

- **[DataLoggerEngine](datalogger_engine.md)**: The core engine that processes logging tasks.
- **DataLogger**: The worker thread that periodically triggers logging actions.

## Configuration

The logging behavior is controlled by:

- **Logger Period**: How often the logger runs (default 10s).
- **Database Config**: Connection details in `db/db_config.json`.
