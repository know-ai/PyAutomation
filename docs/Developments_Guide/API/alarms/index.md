# Alarms API

The Alarms module implements the ISA 18.2 standard for alarm management. It handles alarm states, transitions, triggering logic, and shelving mechanisms.

## Components

*   **[Alarm](alarm.md)**: The main alarm class implementing the state machine.
*   **[States](states.md)**: Definitions of standard alarm states (Normal, Unacknowledged, Shelved, etc.).
*   **[Triggers](triggers.md)**: Logic for detecting alarm conditions (High, Low, Boolean).

## Usage

Alarms are typically created via the `PyAutomation` core instance, but they can be interacted with directly for advanced use cases.

```python
# Example of creating an alarm via PyAutomation
app.create_alarm(
    name="HighPressure",
    tag="PressureTag",
    alarm_type="HIGH",
    trigger_value=100.0,
    description="Tank pressure too high"
)
```

