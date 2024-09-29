import functools, logging
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


def validate_types(**validations):
    
    if "output" in validations:

        _output = validations.pop('output')

        if _output is None:

            _output = type(None)

    def decorator(func):
        from ..alarms.alarms import Alarm
        from ..managers.alarms import AlarmManager
        from ..workers.logger import LoggerWorker
        def wrapper(*args, **kwargs):
            
            for key, _data_type in kwargs.items():

                if key in validations:
                
                    if not isinstance(_data_type, validations[key]):
                        message = f"Expected {validations[key]}, but got {type(_data_type)} in {func}"
                        logging.error(message)
                        raise TypeError(message)
                    
                else:
                    message = f"You didn't define {key} argument to validate in {func}"
                    logging.error(message)
                    raise KeyError(message)

            # Call the wrapped function
            result = func(*args, **kwargs)

            # Validate the output type
            if _output:
                if not isinstance(result, _output):
                    message = f"Expected output type {_output}, but got {type(result)} in func {func}"
                    logging.error(message)
                    raise TypeError(message)

            return result
        return wrapper
    return decorator