# State Machine Manager API

The `StateMachineManager` acts as a registry for all State Machines running in the application. It allows for dynamic addition/removal of machines and provides access to their configuration.

::: automation.managers.state_machine.StateMachineManager
    :docstring:
    :members: get_queue
    :members: append_machine
    :members: get_machines
    :members: serialize_machines
    :members: get_machine
    :members: drop
    :members: unsubscribe_tag
    :members: summary
    :members: exist_machines
