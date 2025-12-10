# Workers API

Workers are the execution units of PyAutomation. They run in background threads to perform tasks such as data logging and state machine execution.

## Available Workers

- **[BaseWorker](worker.md)**: Abstract base class for all workers.
- **[LoggerWorker](logger.md)**: Handles data persistence and database maintenance.
- **[StateMachineWorker](state_machine.md)**: Coordinates the execution of all state machines.
