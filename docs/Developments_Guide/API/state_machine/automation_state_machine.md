# API Documentation

Escribir un preambulo de contenido de la API

::: automation.state_machine.AutomationStateMachine
    :docstring:
    :members: while_starting
    :members: while_waiting
    :members: while_running
    :members: while_testing
    :members: while_sleeping
    :members: while_resetting
    :members: while_restarting
    :members: on_start_to_wait
    :members: on_wait_to_reset
    :members: on_run_to_restart
    :members: on_run_to_reset
    :members: on_test_to_restart
    :members: on_test_to_reset
    :members: on_sleep_to_restart
    :members: on_sleep_to_reset
    :members: on_reset_to_start
    :members: on_restart_to_wait
    :members: set_buffer_size
    :members: get_subscribed_tags
    :members: subscribe_to
    :members: notify
    :members: unsubscribe_to
    :members: get_interval
    :members: set_interval
    :members: _get_active_transitions
    :members: _activate_triggers
    :members: loop
    :members: get_states
    :members: serialize
    