from ..utils.decorators import decorator
from ..buffer import Buffer

data = dict()

def __filter(data:Buffer):
    r"""
    Wavelet filter noise
    """
    return data.current()

@decorator
def gaussian_noise_filter(func, args, kwargs):
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
    # Apply filter logic
    if len(data[tag.name]) >= data[tag.name].size:
        
        kwargs["value"] = __filter(data[tag.name])
        return func(*args, **kwargs)

    return func(*args, **kwargs)