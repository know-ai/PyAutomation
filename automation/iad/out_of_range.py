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
        
        data[tag.name](value)
        # Apply IAD logic
        if len(data[tag.name]) >= data[tag.name].size:
            
            __iad(data[tag.name])

    return func(*args, **kwargs)