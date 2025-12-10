# Alarms Models

Models responsible for storing alarm configurations and historical alarm data.

::: automation.dbmodels.alarms.AlarmTypes
    :docstring:
    :members: create
    :members: read_by_name
    :members: name_exist
    :members: serialize

::: automation.dbmodels.alarms.AlarmStates
    :docstring:
    :members: create
    :members: read_by_name
    :members: name_exist
    :members: serialize

::: automation.dbmodels.alarms.Alarms
    :docstring:
    :members: create
    :members: name_exists
    :members: read
    :members: read_by_identifier
    :members: read_by_name
    :members: serialize

::: automation.dbmodels.alarms.AlarmSummary
    :docstring:
    :members: create
    :members: read_by_name
    :members: read_by_alarm_id
    :members: read_all
    :members: read_lasts
    :members: filter_by
    :members: get_alarm_summary_comments
    :members: serialize