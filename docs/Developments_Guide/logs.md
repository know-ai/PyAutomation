# PyAutomation Error Logs

PyAutomation implements a robust error handling and logging system that captures exceptions, runtime errors, and system events. This system ensures that critical issues are recorded for diagnosis without crashing the application.

## Logging System Overview

The framework uses the standard Python `logging` module, enhanced with custom decorators and a database persistence layer.

- **File Logging**: Logs are written to `logs/app.log` (configurable).
- **Database Logging**: Critical events and errors are stored in the `Logs` table for historical query.
- **Error Handling Decorator**: A unified decorator catches exceptions across the application.

## Configuration

Logging behavior is controlled via the `db/app_config.json` file or environment variables.

### Key Parameters

- `logger_period` (float): Interval in seconds for the Logger Worker.
- `log_level` (int): Logging level (e.g., 20 for INFO, 30 for WARNING, 40 for ERROR).
- `log_max_bytes` (int): Maximum size of the log file before rotation.
- `log_backup_count` (int): Number of backup log files to keep.

You can update these settings dynamically using the API or `PyAutomation` methods:

```python
app.update_log_level(30) # Set to WARNING
app.update_log_config(max_bytes=5242880, backup_count=5)
```

## Logging Error Handler

The `@logging_error_handler` decorator wraps critical methods to catch unhandled exceptions.

**Features:**

1.  **Captures Exception**: Catches any `Exception` raised within the decorated function.
2.  **Traceback Analysis**: Extracts filename, function name, and line number where the error occurred.
3.  **Formatting**: Formats the error as a JSON-like string containing type, message, and trace.
4.  **Logging**: Writes the formatted message to the application logger (`pyautomation`) and prints to `stderr`.
5.  **Non-Blocking**: Prevents the thread/worker from crashing, allowing the system to continue running (where appropriate).

### Usage

```python
from automation.utils.decorators import logging_error_handler

@logging_error_handler
def risky_operation(data):
    # If this raises an error, it will be logged, and the function will return None
    result = data['missing_key']
    return result
```

## Database Logs (LogsLoggerEngine)

While `app.log` stores text logs, the `LogsLoggerEngine` persists structured log data to the database. This allows for querying logs by user, severity, or time range via the API.

- **API Endpoint**: `/api/logs`
- **Attributes**: Message, User, Description, Classification, Alarm ID, Event ID, Timestamp.

## Log Rotation

PyAutomation uses `RotatingFileHandler`. When `app.log` reaches `log_max_bytes`, it is renamed to `app.log.1`, and a new log file is created. Old backups are rotated out based on `log_backup_count`.
