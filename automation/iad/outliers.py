from ..utils.decorators import decorator
from ..buffer import Buffer

data = dict()

def __iad(data:Buffer):
    r"""
    Outliers Algorithm
    """
    return data.current()

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
            
            kwargs["value"] = __iad(data[tag.name])

    return func(*args, **kwargs)