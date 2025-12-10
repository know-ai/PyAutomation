# WebSocket Events API

PyAutomation uses Socket.IO to broadcast real-time updates to connected clients. This allows for reactive UIs and third-party integrations.

## Connection

To connect to the WebSocket server, use a standard Socket.IO client.

**Endpoint:** `ws://<HOST>:<PORT>/socket.io/`

**Event:** `on_connection`

On successful connection, the server emits an initial payload containing the current state of the system.

**Payload Structure:**

```json
{
    "tags": [ ... ],              // List of serialized Tag objects
    "alarms": [ ... ],            // List of serialized Alarm objects
    "machines": [ ... ],          // List of serialized Machine objects
    "last_alarms": [ ... ],       // List of recent historical Alarm records
    "last_active_alarms": [ ... ],// List of currently active Alarm records
    "last_events": [ ... ],       // List of recent Event objects
    "last_logs": [ ... ]          // List of recent Log objects
}
```

---

## Real-time Updates

The system emits the following events when state changes occur.

### `on.tag`

Triggered when a tag's value changes (deadband logic applies).

**Payload:** `Tag` object serialization.

```json
{
    "id": "c4a760a8",
    "name": "Pressure_01",
    "value": 45.2,
    "timestamp": "10/27/2023, 10:00:00.123456",
    "values": [45.1, 45.2, ...],      // Buffer of recent values
    "timestamps": ["...", ...],       // Buffer of recent timestamps
    "unit": "bar",
    "display_unit": "bar",
    "data_type": "float",
    "variable": "Pressure",
    "description": "Main Line Pressure",
    "display_name": "Main Pressure",
    "opcua_address": "opc.tcp://localhost:4840",
    "node_namespace": "ns=2;i=12",
    "scan_time": 1000,                // ms
    "dead_band": 0.1,
    "segment": "Line1",
    "manufacturer": "Siemens",
    "process_filter": false,
    "gaussian_filter": false,
    "out_of_range_detection": false,
    "frozen_data_detection": false,
    "outlier_detection": false
}
```

### `on.alarm`

Triggered when an alarm configuration changes or its state updates in memory.

**Payload:** `Alarm` object serialization.

```json
{
  "id": "b1c2d3e4",
  "name": "HighPressure",
  "tag": "Pressure_01",
  "description": "Pressure exceeded limit",
  "trigger_type": "HIGH",
  "trigger_value": 80.0,
  "identifier": "b1c2d3e4",
  "alarm_setpoint": {
    // Dynamic setpoint configuration
    "setpoint": 80.0,
    "hysteresis": 0.0
  },
  "state": {
    // Current state details
    "state": "Active", // "Normal", "Active", "Acknowledged"
    "timestamp": "...",
    "ack_timestamp": null,
    "ack_user": null
  }
}
```

### `on.log`

Triggered when a new log entry is created.

**Payload:** `Log` object serialization.

```json
{
  "id": 123,
  "timestamp": "10/27/2023, 10:05:00.000000",
  "user": {
    // User who triggered/created the log
    "identifier": "u1",
    "username": "admin",
    "role": { "name": "superuser", "level": 0 },
    "email": "admin@example.com",
    "name": "Admin",
    "lastname": "User"
  },
  "message": "User admin logged in",
  "description": "Successful login from IP...",
  "classification": "Authentication",
  "event": null, // Linked Event object (if any)
  "alarm": null, // Linked Alarm object (if any)
  "segment": "Global",
  "manufacturer": "Intelcon"
}
```

### `on.event`

Triggered when a system event occurs.

**Payload:** `Event` object serialization.

```json
{
    "id": 45,
    "timestamp": "10/27/2023, 10:10:00.000000",
    "user": { ... },                  // Serialized User object
    "message": "System Shutdown Initiated",
    "description": "Manual override triggered",
    "classification": "System",
    "priority": 1,
    "criticity": 5,
    "segment": "Line1",
    "manufacturer": "Intelcon",
    "has_comments": false
}
```

### `on.machine`

Triggered when a state machine changes state or properties.

**Payload:** `Machine` object serialization.

```json
{
    "state": "Running",               // Current State: Start, Wait, Run, etc.
    "actions": ["stop", "pause"],     // Allowed transitions from current state
    "manufacturer": "Intelcon",
    "segment": "Line1",
    "name": "MainProcess",
    "description": "Main control loop",
    "classification": "Automation",
    "machine_interval": 1.0,          // Execution interval in seconds
    "buffer_size": 10,
    "criticity": 1,
    "priority": 1,
    // ... plus any dynamic ProcessVariables attached to the machine
    "temperature_in": {               // Example ProcessVariable
        "tag": { ... },               // Full Tag object
        "value": 25.4,
        "read_only": true
    }
}
```

### `on.machine.property`

Triggered when a specific property of a machine changes (lightweight update).

**Payload:**

```json
{
  "machine_name": "MainProcess",
  "property": "speed",
  "value": 1500
}
```

### `on.opcua.connected` / `on.opcua.disconnected`

Triggered when an OPC UA client connection status changes.

**Payload:**

```json
{
  "message": "Connected to opc.tcp://localhost:4840"
}
```
