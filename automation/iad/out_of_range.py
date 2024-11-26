from ..utils.decorators import decorator
from ..buffer import Buffer

data = dict()

def __iad(data:Buffer):
    r"""
    Out Of Range Algorithm
    """
    return data.current()

@decorator
def iad_out_of_range(func, args, kwargs):
    r"""
    Documentation here
    """
    cvt = args[0]
    tag_id = kwargs["id"]
    value = kwargs["value"]
    tag = cvt.get_tag(id=tag_id)
    if tag.out_of_range_detection:
        if tag.name not in data:
            data[tag.name] = Buffer()
            
            # Create Alarm
            from automation import PyAutomation
            app = PyAutomation()
            alarm_name = f"alarm.iad.oor.{tag.name}"
            if not app.alarm_manager.get_alarm_by_name(name=alarm_name):
                if app.is_db_connected():
                    app.create_alarm(name=alarm_name, tag=f"{tag.name}", description="The measurement is out of range")
        
        data[tag.name](value)
        # Apply IAD logic
        if len(data[tag.name]) >= data[tag.name].size:
            kwargs["value"] = __iad(data[tag.name])
            return func(*args, **kwargs)

    return func(*args, **kwargs)