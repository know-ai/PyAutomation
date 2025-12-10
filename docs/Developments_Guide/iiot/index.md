# IIoT Integrations

PyAutomation ships with built-in Industrial IoT connectivity so control logic, alarms, and logging can run on live plant data. Today the stack includes an embedded OPC UA Server plus an OPC UA client manager; Modbus support is on the roadmap.

## What’s Included

- **OPC UA (server and clients)**: Expose CVT tags, alarms, and state machines as an OPC UA address space, and subscribe to external OPC UA servers to drive CVT inputs.
- **Data plumbing**: CVT stays the single source of truth. Subscribed field values flow into state machines, alarms, and the DataLogger without extra wiring.
- **Observability**: SocketIO surfaces live values and alarm changes while the OPC UA server mirrors them for third-party tools.
- **Roadmap: Modbus**: TCP client/server planned to bring Modbus registers into the same CVT/alarm/logger pipeline.

## When to Use

- Bridge field devices to state machines or dashboards via OPC UA.
- Provide a standards-based endpoint (OPC UA) for historians or SCADA to consume PyAutomation data.
- Plan Modbus connectivity where OPC UA is not available.

See the protocol-specific pages:
- [OPC UA](opcua.md)
- [Modbus](modbus.md)
