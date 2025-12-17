# PyAutomation Error Logs

<div align="center" style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #bf360c; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); font-weight: 700;">
  📝 Robust Error Handling & Logging
</h2>

<p style="color: #a02800; font-size: 1.4em; margin-top: 1em; font-weight: 500;">
  PyAutomation implements a robust error handling and logging system that captures exceptions, runtime errors, and system events. This system ensures that critical issues are recorded for diagnosis without crashing the application.
</p>

</div>

## Logging System Overview

<div style="background: #f8f9fa; border-left: 5px solid #ff9800; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
The framework uses the standard Python <code>logging</code> module, enhanced with custom decorators and a database persistence layer.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>File Logging</strong>: Logs are written to <code>logs/app.log</code> (configurable).</li>
<li><strong>Database Logging</strong>: Critical events and errors are stored in the <code>Logs</code> table for historical query.</li>
<li><strong>Error Handling Decorator</strong>: A unified decorator catches exceptions across the application.</li>
</ul>

</div>

## Configuration

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #ff9800;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Logging behavior is controlled via the <code>db/app_config.json</code> file or environment variables.
</p>

### Key Parameters

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><code>logger_period</code> (float): Interval in seconds for the Logger Worker.</li>
<li><code>log_level</code> (int): Logging level (e.g., 20 for INFO, 30 for WARNING, 40 for ERROR).</li>
<li><code>log_max_bytes</code> (int): Maximum size of the log file before rotation.</li>
<li><code>log_backup_count</code> (int): Number of backup log files to keep.</li>
</ul>

</div>

You can update these settings dynamically using the API or `PyAutomation` methods:

```python
app.update_log_level(30) # Set to WARNING
app.update_log_config(max_bytes=5242880, backup_count=5)
```

---

## Logging Error Handler

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #f44336;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
The <code>@logging_error_handler</code> decorator wraps critical methods to catch unhandled exceptions.
</p>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Features:</strong>
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Captures Exception</strong>: Catches any <code>Exception</code> raised within the decorated function.</li>
<li><strong>Traceback Analysis</strong>: Extracts filename, function name, and line number where the error occurred.</li>
<li><strong>Formatting</strong>: Formats the error as a JSON-like string containing type, message, and trace.</li>
<li><strong>Logging</strong>: Writes the formatted message to the application logger (<code>pyautomation</code>) and prints to <code>stderr</code>.</li>
<li><strong>Non-Blocking</strong>: Prevents the thread/worker from crashing, allowing the system to continue running (where appropriate).</li>
</ol>

</div>

### Usage

```python
from automation.utils.decorators import logging_error_handler

@logging_error_handler
def risky_operation(data):
    # If this raises an error, it will be logged, and the function will return None
    result = data['missing_key']
    return result
```

---

## Database Logs (LogsLoggerEngine)

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
While <code>app.log</code> stores text logs, the <code>LogsLoggerEngine</code> persists structured log data to the database. This allows for querying logs by user, severity, or time range via the API.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>API Endpoint</strong>: <code>/api/logs</code></li>
<li><strong>Attributes</strong>: Message, User, Description, Classification, Alarm ID, Event ID, Timestamp.</li>
</ul>

</div>

---

## Log Rotation

<div style="background: #f8f9fa; border-left: 5px solid #ff9800; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
PyAutomation uses <code>RotatingFileHandler</code>. When <code>app.log</code> reaches <code>log_max_bytes</code>, it is renamed to <code>app.log.1</code>, and a new log file is created. Old backups are rotated out based on <code>log_backup_count</code>.
</p>

</div>
