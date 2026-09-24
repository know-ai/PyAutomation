# OPC UA

PyAutomation embeds an OPC UA server and an OPC UA client manager so you can both expose your automation data and ingest values from external controllers. Everything flows through the CVT, keeping a single source of truth for state machines, alarms, and logging.

## Architecture

- **Embedded OPC UA Server (`OPCUAServer`)**: State machine in `automation/opcua_server/`. The address space is always `Objects/PyAutomationIO/{Site}/{Area}/{Process,Alarms,Engines}` with NodeIds `ns=<idx>;s=t|a|e:<name>`. `AUTOMATION_MANUFACTURER` and `AUTOMATION_SEGMENT` are the `{Site}` and `{Area}` folders. They are not fields of the NodeId. The qualified name already contains the segment. An analog tag keeps `unit`, `EURange` and `variable` as properties. `unit` is the display symbol as plain text. Scan, deadband and filter settings are JSON in `runtime_config` and `filter_config` (at most 5 properties, 6 nodes). There is no `area` property. Endpoint `opc.tcp://{AUTOMATION_OPCUA_SERVER_HOST}:{AUTOMATION_OPCUA_SERVER_PORT}/OPCUAServer/` (defaults `0.0.0.0` and `53530`). See `specs/opcua-server-address-space.md`.
- **OPC UA Client Manager**: Manages multiple outbound client sessions to external OPC UA servers. It handles reconnects and subscriptions, pushing updates into CVT tags via `MachineObserver` so downstream components stay in sync.
- **Address space mapping**: CVT tags carry `opcua_address`, `node_namespace`, and `scan_time` metadata, making it straightforward to bind external nodes or expose internal values.
- **Logging & alarms**: Once a tag is in CVT, DataLogger and AlarmManager can persist and protect it without protocol-specific code.

The embedded server runs on `asyncua` inside a dedicated operating-system thread with its own asyncio loop. The gevent thread only enqueues snapshots on a bounded queue. It does not call `add_variable` or `start`. The NodeId contract in the next section does not change. Outbound field sessions use a second thread, `opcua-asyncua-client`, also on `asyncua`. That thread does the Read and the subscription. Gevent only waits and writes the CVT.

## NodeId Contract

Syntax: `ns=<idx>;s=<t|a|e>:<canonical_name>`.

Example: business name `Supe.Linea1.FI_01` becomes `ns=2;s=t:supe.linea1.fi_01`.

`AUTOMATION_MANUFACTURER` is the `{Site}` folder and `AUTOMATION_SEGMENT` is the `{Area}` folder, so a person can browse the plant. Neither is a structural field. Changing those environment variables does not change the NodeId of a tag whose stored name already includes the segment. A new tag that omits the prefix is still stored as `{MANUFACTURER}.{SEGMENT}.{short}`.

Canonicalization, in order: NFC, strip control characters, collapse whitespace, `casefold`, spaces become dots, `;` and `,` become `_`, drop dots at the ends only, cut the result at 256 characters. Empty input becomes `_`. The function is idempotent. `FI..01` stays `fi..01`. A roman numeral `Ⅰ` is not folded into ASCII `I`, so those two names stay different NodeIds.

New manual tags that omit the prefix are stored as `{MANUFACTURER}.{SEGMENT}.{short}` (`Default` and `Global` when those settings are empty). Names that start with `PyAutomationIO.`, `SYS.`, `ALM.PERF.` or `alarm.SYS.` are rejected. Two different business names that canonicalize to the same string are rejected. Reloading a tag from storage does not rename it.

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
