# Version 1.1.5

> **Note:** The official project roadmap has moved to the documentation. Please see [Roadmap](docs/roadmap.md) for the most up-to-date status.

## Completed Features

- [x] State Machines
  - [x] Sync Machines
  - [x] Async Machines
- [x] CVT (Current Value Tables, Tags Repository)
- [x] Alarms (Alarm repository)
- [x] DataLogger (Data Persistency)
- [x] Workers
  - [x] DataLogger
  - [x] Alarms
  - [x] State Machines
- [x] Engines (Thread Safe Mechanisms)
  - [x] CVT
  - [x] DataLogger
  - [x] Alarms
- [x] Alarm Management System
  - [x] DBModels (Persistency)
- [x] Industrial Protocols
  - [x] OPCUA (Client - Server)
- [x] State Machine for each Tags, to separate scan time.
- [x] Data Filtering
- [x] Instrument Anomaly Detection
  - [x] Outliers
  - [x] Out of Range
  - [x] Data Frozen

## In Progress / Planned (See docs/roadmap.md)

- [ ] Industrial Protocols
  - [ ] Modbus TCP (Client - Server)
  - [ ] OPC DA (Client - Server)
- [ ] Instrument Anomaly Detection
  - [ ] Sensor Drift
- [ ] Configuration Page with React
- [ ] Migrate Flask to FastAPI
