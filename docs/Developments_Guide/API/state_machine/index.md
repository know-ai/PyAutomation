# State Machine API

The State Machine module is the core of the logic processing in PyAutomation. It allows you to define sequential logic, control loops, and data acquisition tasks.

## Key Classes

- **[Machine](machine.md)**: The manager singleton that handles the lifecycle of all state machines.
- **[AutomationStateMachine](automation_state_machine.md)**: The base class for user-defined logic.
- **DAQ**: A specialized state machine for Data Acquisition.
- **OPCUAServer**: A state machine that manages an embedded OPC UA Server.

## Creating a Custom State Machine

To create your own logic, inherit from `AutomationStateMachine` and define your states and transitions.

```python
from automation import AutomationStateMachine, State

class MyProcess(AutomationStateMachine):

    # Define States
    idle = State('idle', initial=True)
    processing = State('processing')

    # Define Transitions
    start_process = idle.to(processing)
    finish_process = processing.to(idle)

    def while_processing(self):
        # Your logic here
        pass
```
