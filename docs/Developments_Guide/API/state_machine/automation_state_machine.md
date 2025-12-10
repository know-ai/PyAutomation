# Automation State Machine API

The `AutomationStateMachine` is the base class for implementing custom automation logic. It extends the `statemachine` library with PyAutomation-specific features like data buffering, tag subscription, and database logging.

::: automation.state_machine.StateMachineCore
    :docstring:
    :members: while_starting
    :members: while_waiting
    :members: while_running
    :members: while_resetting
    :members: while_restarting
    :members: set_socketio
    :members: put_attr
    :members: add_process_variable
    :members: get_process_variables
    :members: get_process_variable
    :members: set_buffer_size
    :members: restart_buffer
    :members: get_subscribed_tags
    :members: get_not_subscribed_tags
    :members: subscribe_to
    :members: unsubscribe_to
    :members: process_type_exists
    :members: get_internal_process_type_variables
    :members: get_read_only_process_type_variables
    :members: notify
    :members: attach
    :members: transition
    :members: get_interval
    :members: set_interval
    :members: get_allowed_actions
    :members: loop
    :members: get_states
    :members: get_serialized_models
    :members: serialize
    :members: on_start_to_wait
    :members: on_wait_to_run
    :members: on_wait_to_restart
    :members: on_wait_to_reset
    :members: on_run_to_restart
    :members: on_run_to_reset
    :members: on_reset_to_start
    :members: on_restart_to_wait
    :members: on_enter_starting
    :members: on_enter_waiting
    :members: on_enter_running
    :members: on_enter_restarting
    :members: on_enter_resetting

::: automation.state_machine.DAQ
    :docstring:
    :members: while_waiting
    :members: while_running
    :members: set_opcua_client_manager

::: automation.state_machine.OPCUAServer
    :docstring:
    :members: while_starting
    :members: while_waiting
    :members: while_running
    :members: while_resetting

::: automation.state_machine.AutomationStateMachine
    :docstring:
    :members: while_testing
    :members: while_sleeping
    :members: on_test_to_restart
    :members: on_test_to_reset
    :members: on_sleep_to_restart
    :members: on_sleep_to_reset
    :members: on_enter_sleeping
    :members: on_enter_testing
