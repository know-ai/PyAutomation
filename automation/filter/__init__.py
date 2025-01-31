from ..utils.decorators import decorator


@decorator
def filter(func, args, kwargs):
    r"""
    Documentation here
    """
    cvt = args[0]
    tag_id = kwargs["id"]
    value = kwargs["value"]
    tag = cvt.get_tag(id=tag_id)
    if tag.gaussian_filter:
        
        kwargs["value"] = tag.filter(value, threshold=tag.gaussian_filter_threshold, r_value=tag.gaussian_filter_r_value)
        return func(*args, **kwargs)
    
    return func(*args, **kwargs)
