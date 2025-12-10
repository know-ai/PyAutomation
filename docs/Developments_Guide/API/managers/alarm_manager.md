# Alarm Manager API

The `AlarmManager` is a singleton service responsible for:
1.  Creating and storing alarm instances.
2.  Validating alarm configurations (e.g., detecting conflicting thresholds).
3.  Acting as an Observer for Tag changes to trigger alarm logic.
4.  Persisting alarm states to the database.

::: automation.managers.alarms.AlarmManager
    :docstring:
    :members:

