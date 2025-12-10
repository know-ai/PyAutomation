# Logger Worker

The `LoggerWorker` manages the persistence of historical data (tags, alarms, events) into the database. It handles batch writing, database maintenance (backups/vacuum), and reconnection logic.

::: automation.workers.logger.LoggerWorker
    :docstring:
    :members:
