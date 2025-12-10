# OPC UA

PyAutomation embeds an OPC UA server and an OPC UA client manager so you can both expose your automation data and ingest values from external controllers. Everything flows through the CVT, keeping a single source of truth for state machines, alarms, and logging.

## Architecture

- **Embedded OPC UA Server (`OPCUAServer`)**: Runs as a state machine. It publishes folders for CVT tags, alarms, and engines (state machines), updating values continuously. Endpoint defaults to `opc.tcp://0.0.0.0:53530/OPCUAServer/` (override via `OPCUA_SERVER_PORT`).
- **OPC UA Client Manager**: Manages multiple outbound client sessions to external OPC UA servers. It handles reconnects and subscriptions, pushing updates into CVT tags via `MachineObserver` so downstream components stay in sync.
- **Address space mapping**: CVT tags carry `opcua_address`, `node_namespace`, and `scan_time` metadata, making it straightforward to bind external nodes or expose internal values.
- **Logging & alarms**: Once a tag is in CVT, DataLogger and AlarmManager can persist and protect it without protocol-specific code.

### OPC UA Integration Architecture

``` mermaid
graph TB
    subgraph "External Systems"
        PLC[PLC/Field Device]
        SCADA[SCADA System]
    end
    
    subgraph "PyAutomation OPC UA"
        Client[OPC UA Client Manager]
        Server[OPC UA Server]
    end
    
    subgraph "PyAutomation Core"
        CVT[CVT]
        SM[State Machines]
        AM[Alarm Manager]
        DL[Data Logger]
    end
    
    PLC -->|OPC UA Subscribe| Client
    Client -->|Update Tags| CVT
    CVT -->|Expose| Server
    Server -->|OPC UA Read| SCADA
    CVT --> SM
    CVT --> AM
    CVT --> DL
```

### OPC UA Data Flow

``` mermaid
sequenceDiagram
    participant PLC as External PLC
    participant Client as OPC UA Client
    participant CVT as CVT
    participant Server as OPC UA Server
    participant SCADA as SCADA System
    
    Note over PLC,CVT: Inbound Data Flow
    PLC->>Client: Node Value Change
    Client->>CVT: Update Tag Value
    CVT->>CVT: Notify Observers
    
    Note over CVT,SCADA: Outbound Data Flow
    CVT->>Server: Tag Value Update
    Server->>SCADA: OPC UA Notification
    SCADA->>Server: Read Request
    Server-->>SCADA: Current Value
```

## Common Flows

### Expose PyAutomation data through OPC UA

1) Make sure your tags, alarms, and machines are registered in PyAutomation.
2) Start the embedded OPC UA server (PyAutomation entrypoints wire it as a state machine).
3) Connect third-party clients (SCADA, historians) to the endpoint and browse folders `CVT/`, `Alarms/`, and `Engines/`.

### Subscribe to an external OPC UA server

```python
from automation import PyAutomation

app = PyAutomation()
# Define a tag with OPC UA metadata
app.create_tag(
    name="TankLevel",
    unit="m",
    data_type="float",
    variable="Length",
    description="Level from PLC",
    opcua_address="opc.tcp://plc1:4840",  # server URL
    node_namespace="ns=2;i=2",            # node identifier
    scan_time=1000                         # polling period (ms)
)

# Register an OPC UA client and subscribe the tag
app.add_opcua_client(url="opc.tcp://plc1:4840", client_name="PLC1")
tag = app.get_tag_by_name("TankLevel")
app.subscribe_opcua(
    tag=tag,
    opcua_address=tag.get_opcua_address(),
    node_namespace=tag.get_node_namespace(),
    scan_time=tag.get_scan_time(),
)

app.run()  # launches workers; LoggerWorker will log the tag if history is enabled
```

### Mirror CVT changes to OPC UA clients

Any CVT updates (including values written by state machines) are reflected by the embedded server, so external consumers see current values without extra glue code.

## Best Practices

- Use meaningful `display_name`/`display_unit` for operator-facing clients; keep `name` concise for programmatic access.
- Set realistic `scan_time` per tag; avoid over-polling PLCs while keeping control loops responsive.
- Keep `dead_band` tuned to reduce churn on noisy signals that feed into OPC UA and logging.
- Align security with your deployment: place the OPC UA endpoint behind TLS termination if needed; rotate credentials on external servers.
- Reuse namespaces consistently (`node_namespace`) so mappings remain stable after controller updates.

## Troubleshooting

- **No data on clients**: Ensure the OPC UA server state machine is running and the endpoint is reachable on `OPCUA_SERVER_PORT`.
- **Subscriptions silent**: Verify `opcua_address` and `node_namespace` match the external node, and that the client is added via `add_opcua_client` before calling `subscribe_opcua`.
- **Reconnections**: The client manager attempts reconnects; check network and server certificates if reconnect storms appear.
- **Mismatched units**: OPC UA values are written using tag `display_unit`; normalize units across field devices and PyAutomation to avoid incorrect trends.
