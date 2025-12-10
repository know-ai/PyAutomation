# Alarm Manager API

The `AlarmManager` is a singleton service responsible for:
1.  Creating and storing alarm instances.
2.  Validating alarm configurations (e.g., detecting conflicting thresholds).
3.  Acting as an Observer for Tag changes to trigger alarm logic.
4.  Persisting alarm states to the database.

::: automation.managers.alarms.AlarmManager
    :docstring:
    :members: get_queue
    :members: append_alarm
    :members: put
    :members: delete_alarm
    :members: get_alarm
    :members: get_alarm_by_name
    :members: get_alarm_by_tag
    :members: get_alarms
    :members: get_lasts_active_alarms
    :members: serialize
    :members: get_tag_alarms
    :members: tags
    :members: filter_by
    :members: get_lasts
    :members: summary
    :members: attach
    :members: execute

