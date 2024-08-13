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
    :members: on_enter_starting
    :members: on_enter_waiting
    :members: on_enter_running
    :members: on_enter_testing
    :members: on_enter_sleeping
    :members: on_enter_resetting
    :members: on_enter_restarting
    :members: on_start_to_wait
    :members: on_wait_to_run
    :members: on_wait_to_restart
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
    :members: get_state_interval
    :members: get_subscribed_tags
    :members: subscribe_to
    :members: notify
    :members: unsubscribe_to
    :members: get_interval
    :members: set_interval
    :members: loop
    :members: info
    :members: get_states
    :members: get_serialized_models
    :members: serialize