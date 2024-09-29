import functools
from ..modules.users.users import User
from ..logger.events import EventsLoggerEngine


events_engine = EventsLoggerEngine()


def decorator(declared_decorator):
    """
    Create a decorator out of a function, which will be used as a wrapper
    """

    @functools.wraps(declared_decorator)
    def final_decorator(func=None, **kwargs):
        # This will be exposed to the rest of your application as a decorator
        def decorated(func):
            # This will be exposed to the rest of your application as a decorated
            # function, regardless how it was called
            @functools.wraps(func)
            def wrapper(*a, **kw):
                # This is used when actually executing the function that was decorated

                return declared_decorator(func, a, kw, **kwargs)
            
            return wrapper
        
        if func is None:
            
            return decorated
        
        else:
            # The decorator was called without arguments, so the function should be
            # decorated immediately
            return decorated(func)

    return final_decorator

def set_event(message:str, classification:str, priority:int, criticity:int):

    @decorator
    def wrapper(func, args, kwargs):
        
        result = func(*args, **kwargs)

        if result:
        
            if "user" in kwargs:

                user = kwargs.pop('user')
                if isinstance(user, User):

                    description = None

                    if isinstance(result, tuple):

                        description = result[-1]

                    events_engine.create(
                        message=message,
                        description=description,
                        classification=classification,
                        priority=priority,
                        criticity=criticity,
                        user=user
                    )

        return result

    return wrapper