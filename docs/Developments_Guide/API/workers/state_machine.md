# State Machine Worker API

The `StateMachineWorker` coordinates the execution of all registered state machines. It decides whether to run a machine synchronously (in the main loop) or asynchronously (in a separate thread).

::: automation.workers.state_machine.StateMachineWorker
    :docstring:
    :members: run
    :members: stop
