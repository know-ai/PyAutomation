# Current Value Table (CVT)

The CVT is PyAutomation’s real-time, in-memory data store for process variables (tags). It is designed to be thread-safe, observable, and the single source of truth for state machines, alarms, loggers, and OPC UA integrations.

## Responsibilities

- Store tag definitions and live values in memory with millisecond timestamps.
- Provide thread-safe access through `CVTEngine` (request/response locks around the underlying `CVT`).
- Notify subscribers via the observer pattern (`TagObserver`, `MachineObserver`) so alarms and machines react immediately to changes.
- Enforce uniqueness for tag names/display names/OPC UA namespaces.
- Bridge to persistence by registering tags with `DataLoggerEngine` and `DBManager` when databases are enabled.

## Tag Model

Each tag includes core metadata:
- `name`, `display_name`
- `unit`, `display_unit`, `variable` (physical quantity)
- `data_type` (`float`, `int`, `bool`, `str`)
- `opcua_address`, `node_namespace`, `scan_time`, `dead_band`
- Optional quality/conditioning flags: `process_filter`, `gaussian_filter`, `outlier_detection`, `out_of_range_detection`, `frozen_data_detection`

Serialization (`tag.serialize()`) returns a JSON-ready dictionary used by APIs and dashboards.

## Working with CVTEngine

`CVTEngine` wraps all operations with locks so workers and state machines can read/write safely:

```python
from automation.tags import CVTEngine

cvt = CVTEngine()
# Create a tag
cvt.set_tag(
    name="TankLevel",
    unit="m",
    data_type="float",
    variable="Length",
    description="Level of TK-101",
    scan_time=1000,
    dead_band=0.01,
    gaussian_filter=True,
)

# Read a tag
level = cvt.get_tag_by_name("TankLevel")
print(level.value)

# Update metadata
cvt.update_tag(level.id, display_name="Tank 101 Level", display_unit="m")
```

Common APIs include `set_tag`, `update_tag`, `delete_tag`, `get_tag_by_name`, `get_tags`, and `serialize_by_tag_name`.

## Observers and Subscriptions

- **MachineObserver**: Binds a tag to a state machine input (`ProcessType`), forwarding updates to `machine.notify` and filling the machine's rolling buffer.
- **TagObserver**: Pushes updates into a queue consumed by `LoggerWorker` and `AlarmManager`, decoupling writers from consumers.
- Use `get_subscribed_tags`/`get_not_subscribed_tags` on `StateMachineCore` to introspect inputs.

### CVT Observer Pattern

``` mermaid
graph TB
    subgraph "CVT Engine"
        CVT[CVT Tags]
    end
    
    subgraph "Observers"
        MO[MachineObserver]
        TO[TagObserver]
    end
    
    subgraph "Consumers"
        SM[State Machines]
        AM[Alarm Manager]
        LW[Logger Worker]
    end
    
    CVT -->|Notify| MO
    CVT -->|Notify| TO
    MO -->|Update Buffer| SM
    TO -->|Enqueue| AM
    TO -->|Enqueue| LW
```

### CVT Thread-Safe Access

``` mermaid
sequenceDiagram
    participant Thread1 as Worker Thread 1
    participant Thread2 as State Machine Thread
    participant CVTEngine as CVTEngine
    participant CVT as CVT (Locked)
    
    Thread1->>CVTEngine: set_tag()
    CVTEngine->>CVT: Acquire Lock
    CVTEngine->>CVT: Write Operation
    CVTEngine->>CVT: Release Lock
    
    Thread2->>CVTEngine: get_tag_by_name()
    CVTEngine->>CVT: Acquire Lock
    CVTEngine->>CVT: Read Operation
    CVTEngine->>CVT: Release Lock
    CVTEngine-->>Thread2: Return Tag
```

## Database and Logging Integration

When `Machine.create_tag_internal_process_type` or user-defined `set_tag` calls are made while a database is configured:
- Tags are registered with `DataLoggerEngine` so historical values are persisted by `LoggerWorker` (period controlled by `LOGGER_PERIOD`).
- `DBManager` attaches the tag for synchronization and backup management.
- IAD flags trigger the automatic creation of companion alarms for out-of-range, frozen, or outlier detection.

## Best Practices

- Keep tag names stable and descriptive; they are used as keys across the stack (alarms, trends, OPC UA).
- Align `unit` and `display_unit` to avoid misinterpretation in UIs and alarm thresholds.
- Use `dead_band` and filters only when the process noise warrants it; unnecessary filtering can hide real events.
- Prefer `display_name` for operator-facing labels; keep `name` concise for programmatic use.
- Avoid direct threading primitives with the raw `CVT`; always interact through `CVTEngine` for thread safety.

## Troubleshooting

- **Duplicate errors** when creating tags: check name, display_name, OPC UA address, and node namespace—all must be unique.
- **Subscribers not receiving data**: ensure observers are attached (e.g., process variables marked `read_only=True` in state machines) and the tag is present in CVT.
- **History not saved**: confirm the database is connected and `LoggerWorker` is running; `DataLoggerEngine.check_connectivity()` should return `True`.
- **Timestamp/format issues**: `CVTEngine.DATETIME_FORMAT` is used for serialization; ensure external writers respect it when injecting timestamps.
