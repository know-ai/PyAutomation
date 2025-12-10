# Alarm Class

The `Alarm` class is a `StateMachine` that manages the lifecycle of a specific alarm instance. It observes a Tag and transitions between states (e.g., Normal -> Unacknowledged -> Acknowledged) based on the tag's value and operator actions.

::: automation.alarms.Alarm
    :docstring:
    :members: set_socketio
    :members: notify
    :members: abnormal_condition
    :members: normal_condition
    :members: acknowledge
    :members: shelve
    :members: unshelve
    :members: designed_suppression
    :members: designed_unsuppression
    :members: remove_from_service
    :members: return_to_service
    :members: attach
    :members: put
    :members: get_operator_actions
    :members: serialize
