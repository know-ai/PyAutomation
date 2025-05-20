import functools, logging, sys
from ..modules.users.users import User, Users
from ..logger.events import EventsLoggerEngine


events_engine = EventsLoggerEngine()
users = Users()

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

def set_event(message:str, classification:str, priority:int, criticity:int, force:bool=False):
    @decorator
    def wrapper(func, args, kwargs):
        from automation import PyAutomation
        app = PyAutomation()
        result = func(*args, **kwargs)
        
        if result:
        
            if "user" in kwargs:

                user = kwargs.pop('user')
                if isinstance(user, User):

                    description = None

                    if isinstance(result, tuple):

                        description = result[-1]
                    
                    event, _ = events_engine.create(
                        message=message,
                        description=description,
                        classification=classification,
                        priority=priority,
                        criticity=criticity,
                        user=user
                    )
                    if app.sio:

                        app.sio.emit("on.event", data=event.serialize())
        else:
            if force:
                description = None

                if isinstance(result, tuple):

                    description = result[-1]
                user = users.get_by_username(username="intelcon")
                event, _ = events_engine.create(
                    message=message,
                    description=description,
                    classification=classification,
                    priority=priority,
                    criticity=criticity,
                    user=user
                )
                
                if app.sio:

                    app.sio.emit("on.event", data=event.serialize())

        return result

    return wrapper

@decorator
def put_alarm_state(func, args, kwargs):
    r"""
    Documentation here
    """
    from ..logger.alarms import AlarmsLoggerEngine
    from .. import TIMEZONE
    alarms_engine = AlarmsLoggerEngine()   
    result = func(*args, **kwargs)
    alarm = args[0]
    alarms_engine.put(
        id=alarm.identifier,
        state=alarm.state.state
    )
    if alarm.sio:
        if alarm.timestamp:
            timestamp = alarm.timestamp
            timestamp = timestamp.astimezone(TIMEZONE)
            alarm.timestamp = timestamp
            if alarm.ack_timestamp:
                ack_timestamp = alarm.ack_timestamp
                ack_timestamp = ack_timestamp.astimezone(TIMEZONE)
                alarm.ack_timestamp = ack_timestamp
        
        alarm.sio.emit("on.alarm", data=alarm.serialize())
        
    return result

def validate_types(**validations):
    
    if "output" in validations:

        _output = validations.pop('output')

        if _output is None:

            _output = type(None)

    def decorator(func):

        def wrapper(*args, **kwargs):
            
            for key, _data_type in kwargs.items():

                if key in validations:
                
                    if not isinstance(_data_type, validations[key]):
                        message = f"Expected Input {key} as {validations[key]}, but got {type(_data_type)} in {func}"
                        logging.error(message)
                        raise TypeError(message)
                    
                else:
                    message = f"You didn't define {key} argument to validate in {func}"
                    logger = logging.getLogger("pyautomation")
                    logger.error(message)
                    raise KeyError(message)

            # Call the wrapped function
            result = func(*args, **kwargs)

            # Validate the output type
            if _output:
                
                if isinstance(_output, tuple):
                    
                    for counter, expected in enumerate(_output):
                        
                        if not isinstance(result[counter], expected):

                            message = f"Expected output type ({counter}) {expected}, but got {type(result[counter])} in func {func}"
                            logger = logging.getLogger("pyautomation")
                            logger.error(message)
                            raise TypeError(message)
                        
                else:

                    if not isinstance(result, _output):
                        message = f"Expected output type {_output}, but got {type(result)} in func {func}"
                        logger = logging.getLogger("pyautomation")
                        logger.error(message)
                        raise TypeError(message)

            return result
        return wrapper
    return decorator

@decorator
def logging_error_handler(func, args, kwargs):
    r"""
    Documentation here
    """
    try:
                
        result = func(*args, **kwargs)
        return result

    except Exception as ex:

        trace = []
        tb = ex.__traceback__
        while tb is not None:
            trace.append({
                "filename": tb.tb_frame.f_code.co_filename,
                "name": tb.tb_frame.f_code.co_name,
                "lineno": tb.tb_lineno
            })
            tb = tb.tb_next
        msg = str({
            'type': type(ex).__name__,
            'message': str(ex),
            'trace': trace
        })
        logger = logging.getLogger("pyautomation")
        logger.error(msg=msg)

@decorator
def db_rollback(func, args, kwargs):
    try:
        self = args[0]
        result = func(*args, **kwargs)
        return result

    except Exception as e:
        _, _, e_traceback = sys.exc_info()
        e_message = str(e)
        e_line_number = e_traceback.tb_lineno
        logger = logging.getLogger("pyautomation")
        logger.warning(f"Rollback in [line {e_line_number}] {self.__class__.__name__}.{func.__name__} - {e_message}")
        conn = self._db.connection()
        conn.rollback()
        result = func(*args, **kwargs)

        return result