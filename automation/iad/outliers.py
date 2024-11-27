from ..utils.decorators import decorator
from ..buffer import Buffer

data = dict()

def __iad(data:Buffer, tag_name:str):
    r"""
    Outliers Algorithm
    """
    from ..managers.alarms import AlarmManager
    alarm_manager = AlarmManager()
    alarm = alarm_manager.get_alarm_by_name(name=f"alarm.iad.{tag_name}")
    if alarm:
        if alarm.state.alarm_status.lower() == "not active":

            mean = sum(data) / len(data)
            # variance = sum((x - mean) ** 2 for x in data) / len(data)
            # std_dev = math.sqrt(variance)
            
            # if abs(std_dev) < 0.01:
                
            #     alarm.description = f"Outlier anomaly"
            #     alarm.abnormal_condition()
            
            # else:
                
            #     alarm.description = ""
            #     alarm.normal_condition()

@decorator
def iad_outlier(func, args, kwargs):
    r"""
    Documentation here
    """
    cvt = args[0]
    tag_id = kwargs["id"]
    value = kwargs["value"]
    tag = cvt.get_tag(id=tag_id)
    if tag.outlier_detection:
        
        if tag.name not in data:
            
            data[tag.name] = Buffer()
    
        data[tag.name](value)
        # Apply IAD logic
        if len(data[tag.name]) >= data[tag.name].size:
            
            __iad(data[tag.name], tag_name=tag.name)

    return func(*args, **kwargs)