from ..utils.decorators import decorator
from ..buffer import Buffer

data = dict()

def __iad(data:Buffer):
    r"""
    Frozen Data Algorithm
    """
    return data.current()

@decorator
def iad_frozen_data(func, args, kwargs):
    r"""
    Documentation here
    """
    cvt = args[0]
    tag_id = kwargs["id"]
    value = kwargs["value"]
    tag = cvt.get_tag(id=tag_id)
    if tag.name not in data:
        data[tag.name] = Buffer()
    data[tag.name](value)
    print(f"[{tag.name}]: {value}")
    print(f"Data: {data[tag.name]}")
    # Apply IAD logic
    if len(data[tag.name]) >= data[tag.name].size:
        kwargs["value"] = __iad(data[tag.name])
        return func(*args, **kwargs)

    return func(*args, **kwargs)