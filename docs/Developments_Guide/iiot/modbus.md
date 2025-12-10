# Modbus

Modbus connectivity is planned for PyAutomation but is not yet available in this release. The goal is to offer both TCP client and server roles so registers and coils can flow into the same CVT/alarm/logger pipeline used by OPC UA.

## Planned Scope

- **Modbus TCP client**: Poll holding/input registers and coils; map to CVT tags with unit conversion and deadband handling.
- **Modbus TCP server**: Expose selected CVT tags as holding/input registers for external systems.
- **Retry and health checks**: Backoff-based reconnects and telemetry so the LoggerWorker can skip writes when comms are down.
- **One wiring model**: Once mapped to CVT, data would be available to state machines, AlarmManager, DataLogger, and dashboards without protocol-specific code.

## Current Workarounds

- If your devices support OPC UA, use the OPC UA client manager today to ingest data and the embedded server to expose it.
- For Modbus-only devices, consider a lightweight gateway (e.g., OpenPLC UA bridge, Kepware, or a simple Python gateway) to convert Modbus to OPC UA until native support ships.

## Tracking Progress

See `docs/roadmap.md` and `TODO.md` entries for “Modbus TCP (Client - Server)” to follow implementation status.
