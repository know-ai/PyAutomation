# State Machines

PyAutomation’s state-machine runtime executes all control logic, sequencing, and supervisory workflows. It is built on top of the `statemachine` library and wrapped by the `Machine` singleton so every machine shares the same scheduler, database connections, and observability layer.

## Architecture at a Glance

- **Machine (singleton)**: Owns the `StateMachineManager`, loads persisted configuration, wires alarm/logging engines, and exposes `append_machine`, `start`, `join`, and `drop`.
- **Scheduler**: `StateMachineWorker` runs machines on a fixed interval. Default mode is asynchronous; synchronous mode is available for tightly coupled cycles.
- **Base classes**: `StateMachineCore` defines the standard lifecycle (start → wait → run → reset/restart). `AutomationStateMachine` extends it with extra `test` and `sleep` states for simulation/low-power modes.
- **Data plane**: Process variables are `ProcessType` instances. Read-only variables subscribe to CVT tags; writable variables can be exposed as tags automatically via `create_tag_internal_process_type`, enabling logging and alarming.
- **Observability**: Each machine can emit state changes through SocketIO, is persisted by `MachinesLoggerEngine`, and can be serialized for UIs or tests with `.serialize()`.
- **Interop**: Machines interact with `CVTEngine` for data, `AlarmManager` for protection logic, `DataLoggerEngine` for history, and the OPC UA server/client stack for field connectivity.

## Lifecycle

1. **Define** a class deriving from `AutomationStateMachine` (or `StateMachineCore` if you only need the core lifecycle).
2. **Declare states and transitions** as class attributes using the `statemachine.State` DSL.
3. **Implement behaviors** in `while_<state>` handlers and transition hooks (e.g., `on_run_to_reset`).
4. **Register** the instance with the `Machine` singleton via `append_machine(machine, interval, mode)`.
5. **Start** scheduling with `machine.start()` (PyAutomation calls this from higher-level entry points).
6. **Operate**: The scheduler cycles through states, buffering subscribed inputs until the machine is ready to run.
7. **Stop**: Call `machine.stop()` for a safe shutdown.

### State Machine Lifecycle Diagram

``` mermaid
stateDiagram-v2
    [*] --> start: Initialize
    start --> wait: start_to_wait
    wait --> run: wait_to_run (buffers ready)
    run --> reset: run_to_reset
    run --> restart: run_to_restart
    reset --> start: reset_to_start
    restart --> wait: restart_to_wait
    wait --> reset: wait_to_reset
    wait --> restart: wait_to_restart
    [*] --> test: Testing mode
    [*] --> sleep: Sleep mode
    test --> restart: test_to_restart
    test --> reset: test_to_reset
    sleep --> restart: sleep_to_restart
    sleep --> reset: sleep_to_reset
```

### State Machine Core Architecture

``` mermaid
graph TB
    subgraph "StateMachineCore"
        Start[Start State]
        Wait[Wait State]
        Run[Run State]
        Reset[Reset State]
        Restart[Restart State]
    end
    
    subgraph "AutomationStateMachine"
        Test[Test State]
        Sleep[Sleep State]
    end
    
    subgraph "Data Flow"
        CVT[CVT Tags]
        Buffer[Input Buffers]
        PV[Process Variables]
    end
    
    Start --> Wait
    Wait -->|Buffers Full| Run
    Run --> Reset
    Run --> Restart
    Reset --> Start
    Restart --> Wait
    Run --> Test
    Run --> Sleep
    
    CVT -->|Subscribe| Buffer
    Buffer -->|Fill| Wait
    Run -->|Read| PV
    PV -->|Write| CVT
```

## Implementing a Machine

```python
from automation import PyAutomation
from automation.state_machine import AutomationStateMachine, State
from automation.models import FloatType

class Mixer(AutomationStateMachine):
    idle = State('idle', initial=True)
    running = State('running')

    start = idle.to(running)
    stop = running.to(idle)

    def while_running(self):
        # Main logic loop
        level = self.get_process_variables().get("tank_level")
        if level and level["value"] > 80:
            self.send('stop')

app = PyAutomation()
mixer = Mixer(name="Mixer", interval=1.0)
app.machine.append_machine(mixer, interval=FloatType(1.0), mode="async")
app.machine.start()
```

### Scheduling and Inputs

- **Interval & mode**: `append_machine` accepts `interval` (seconds) and `mode` (`async` or `sync`). Intervals are persisted when a database is configured.
- **Buffers**: Each subscribed tag keeps a rolling buffer (`buffer_size`, `buffer_roll_type`) managed by `StateMachineCore`. The default behavior waits for buffers to fill before entering `run`.
- **Process variables**: Use `add_process_variable(name, tag, read_only=True)` to bind CVT tags as inputs. Internal process variables are exposed as CVT tags to make diagnostics, alarms, and logging first-class.

### Interaction with the Rest of the Stack

- **Alarms**: Machines can raise alarms via `PyAutomation.create_alarm` or rely on IAD alarms auto-created for out-of-range, frozen data, and outliers.
- **Data logging**: When CVT tags are bound to a machine, `DataLoggerEngine` persists values through the `LoggerWorker` without extra code.
- **OPC UA**: Machines can expose or consume OPC UA nodes through the embedded server/client managers (`OPCUAServer`, `OPCUAClientManager`).

## Best Practices

- Keep `while_*` handlers short and non-blocking; prefer timers or counters over `time.sleep`.
- Treat CVT as the single source of truth for inputs and outputs—avoid hidden globals.
- Use explicit state transitions (`send(...)`) instead of conditionally mutating state flags.
- Version your machine configuration (name, classification, priority, threshold/on-delay) in the database so restarts restore the expected behavior.
- Emit meaningful descriptions for process variables; they surface in the UI, logs, and OPC UA address space.

## Troubleshooting Checklist

- Machine never enters `run`: confirm subscribed tag buffers are filling and that `wait_to_run` is reachable.
- No state changes in UI: ensure SocketIO is configured (`define_dash_app`) and the machine has `set_socketio` set.
- Scheduler idle: verify `machine.start()` was called and there is at least one registered machine in `StateMachineManager`.
- Unexpected restarts: check `while_running` exceptions—decorators (`logging_error_handler`) capture and log them, but long blocking work can trigger resets.
