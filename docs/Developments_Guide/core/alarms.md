# Alarms

PyAutomation implements an ISA‑18.2 style alarm lifecycle. The alarm core evaluates tag changes from the Current Value Table (CVT), drives state transitions, and fans out notifications to the UI and database. Everything is coordinated by the `AlarmManager` singleton so alarms stay consistent across threads and workers.

## Architecture

- **AlarmManager (singleton)**: Creates, updates, and removes alarms; validates trigger uniqueness; manages SocketIO emission; and exposes lookups such as `get_alarm_by_name`.
- **Alarm model**: Encapsulates the state machine for an individual alarm, including setpoint, current state, timestamps, and user attribution.
- **States**: Standard ISA states are implemented in `automation.alarms.states` (Normal, Unacknowledged, Acknowledged, RTN Unacknowledged, Shelved, Suppressed by Design, Out of Service).
- **Triggering**: `TagObserver` pushes CVT updates into a queue; the manager evaluates trigger conditions (BOOL/HIGH/LOW variants) and drives state transitions.
- **Persistence & telemetry**: When a database is configured, alarms are stored through `AlarmsLoggerEngine` and surfaced to the UI via SocketIO.

## Defining Alarms

Use the high-level PyAutomation API to register alarms so they are persisted and wired to CVT/SocketIO automatically:

```python
from automation import PyAutomation

app = PyAutomation()
app.create_alarm(
    name="HighPressure",
    tag="PressureTag",
    alarm_type="HIGH",   # BOOL, HIGH, LOW, HH, LL
    trigger_value=100.0,
    description="Tank pressure too high"
)
```

Key rules:
- Alarm names are unique. Duplicated names or same (tag, type) combinations are rejected.
- `trigger_value` uses the tag’s base unit; align display units if operators use different scales.
- Initial state defaults to **Normal**; timestamps can be injected when reloading from history.

## States and Actions

- **Normal**: Process condition is normal; alarm not active.
- **Unacknowledged**: Condition active and annunciated; waiting for operator acknowledgment.
- **Acknowledged**: Condition active but acknowledged.
- **RTN Unacknowledged**: Condition cleared but awaiting acknowledgment.
- **Shelved / Suppressed by Design / Out of Service**: Alarm temporarily removed from service; requires explicit reset/return-to-service.

Allowed actions per state follow ISA‑18.2 (see `ACTIONS` map in `automation/alarms/states.py`)—for example, shelving is only valid from Normal/Unacknowledged/RTN Unacknowledged.

## Data Flow

1. CVT tag value changes; `TagObserver` enqueues the update.
2. `AlarmManager` evaluates trigger conditions and updates the alarm state machine.
3. State changes emit SocketIO events (when configured) and are persisted through `AlarmsLoggerEngine`.
4. Serialized summaries feed dashboards and API responses.

### Alarm State Machine Diagram

``` mermaid
stateDiagram-v2
    [*] --> Normal: Initial State
    Normal --> Unacknowledged: Condition Active
    Unacknowledged --> Acknowledged: Operator Acknowledges
    Unacknowledged --> Shelved: Operator Shelves
    Acknowledged --> RTN_Unacknowledged: Condition Clears
    RTN_Unacknowledged --> Normal: Operator Acknowledges
    Normal --> Suppressed_By_Design: Suppress by Design
    Normal --> Out_Of_Service: Out of Service
    Shelved --> Normal: Reset
    Suppressed_By_Design --> Normal: Unsuppress
    Out_Of_Service --> Normal: Return to Service
    
    note right of Normal
        Process condition normal
        Alarm not active
    end note
    
    note right of Unacknowledged
        Condition active
        Waiting for acknowledgment
    end note
```

### Alarm Data Flow

``` mermaid
sequenceDiagram
    participant CVT as CVT Tag
    participant TO as TagObserver
    participant Queue as Tag Queue
    participant AM as AlarmManager
    participant Alarm as Alarm State Machine
    participant DB as Database
    participant UI as Web UI
    
    CVT->>TO: Value Changed
    TO->>Queue: Enqueue Update
    Queue->>AM: Process Update
    AM->>Alarm: Evaluate Trigger
    alt Trigger Condition Met
        Alarm->>Alarm: State Transition
        Alarm->>DB: Persist State
        Alarm->>UI: Emit SocketIO Event
    end
```

## Best Practices

- Name alarms consistently (`<area>.<equipment>.<condition>`) to simplify search and reporting.
- Provide concise descriptions; they propagate to UIs and logs.
- Use display units that match operator expectations to avoid misinterpretation of thresholds.
- Keep IAD flags (`out_of_range_detection`, `frozen_data_detection`, `outlier_detection`) enabled on CVT tags that feed safety-critical alarms—PyAutomation will auto-create the associated alarms.
- When reloading alarms from a database, pass `reload=True` to `create_alarm` so timestamps and identifiers are respected.

## Troubleshooting

- **Alarm never triggers**: Verify the CVT tag exists, is updating, and the alarm type/threshold are correct for the tag’s base unit.
- **Duplicate error**: Ensure the (name) and (tag + type) combinations are unique.
- **No UI updates**: Confirm SocketIO is initialized (`define_dash_app`) and the alarm has `set_socketio` set by the manager.
- **Stuck in Shelved/Out of Service**: Use the state-specific actions (unshelve/return-to-service) rather than re-creating the alarm.
