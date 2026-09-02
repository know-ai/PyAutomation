import functools, inspect, logging, re, sys
from ..modules.users.users import User, Users
from ..logger.events import EventsLoggerEngine

_logger = logging.getLogger("pyautomation")


events_engine = EventsLoggerEngine()
users = Users()

_HOST_PORT_RE = re.compile(
    r'(?:server at |host[= ]+)["\']?([\w.\-:]+)["\']?(?:,?\s*port\s+(\d+))?',
    re.IGNORECASE,
)


def _humanize_logged_exception(ex: BaseException, func) -> tuple[str, int] | None:
    """Operator-facing line + log level for common infra failures; None = use default dump.

    Returns ``(message, level)``. Stale handles after reconnect are INFO (no data loss);
    real outages are WARNING (edge continues on local catalog/SAF).
    """
    from .db_io import is_stale_historian_handle

    name = type(ex).__name__
    msg = str(ex).strip()
    msg_lower = msg.lower()
    where = getattr(func, "__qualname__", None) or getattr(func, "__name__", "call")

    host = port = None
    match = _HOST_PORT_RE.search(msg)
    if match:
        host, port = match.group(1), match.group(2)

    if is_stale_historian_handle(ex):
        return (
            f"Historian socket replaced during reconnect (in {where}). "
            f"No data loss — local catalog/SAF keep the truth; retry uses the new link.",
            logging.INFO,
        )

    if name in {"OperationalError", "InterfaceError", "DatabaseError"} or any(
        key in msg_lower
        for key in (
            "connection refused",
            "could not connect",
            "connection timed out",
            "server closed the connection",
            "password authentication failed",
            "could not translate host name",
        )
    ):
        endpoint = ""
        if host:
            endpoint = f" at {host}" + (f":{port}" if port else "")
        if "connection refused" in msg_lower:
            reason = "connection refused (server down or port closed)"
        elif "timed out" in msg_lower or "timeout" in msg_lower:
            reason = "connection timed out"
        elif "password authentication failed" in msg_lower or "access denied" in msg_lower:
            reason = "authentication failed (check user/password)"
        elif "could not translate host name" in msg_lower or "name or service not known" in msg_lower:
            reason = "hostname could not be resolved"
        else:
            reason = msg.split("\n", 1)[0][:180]
        return (
            f"Remote historian unreachable{endpoint}: {reason}. "
            f"Edge keeps running on local catalog/SAF; will retry. "
            f"No historical loss while journaled. (in {where})",
            logging.WARNING,
        )
    return None


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

def set_event(message:str, classification:str, priority:int, criticity:int, description:str="", force:bool=False, plant_wide:bool=False):
    @decorator
    def wrapper(func, args, kwargs):
        from automation import PyAutomation
        from .event_scope import resolve_event_area
        from .system_event_audit import clip as _clip
        app = PyAutomation()
        result = func(*args, **kwargs)
        area = resolve_event_area(
            plant_wide=plant_wide,
            source=(result, kwargs.get("machine"), kwargs.get("tag")),
        )
        
        if result:
        
            if "user" in kwargs:

                user = kwargs.pop('user')
                if isinstance(user, User):

                    _description = None

                    if isinstance(result, tuple):

                        _description = result[-1]
                    event, _ = events_engine.create(
                        message=message,
                        description=_clip(_description, 256),
                        classification=classification,
                        priority=priority,
                        criticity=criticity,
                        user=user,
                        area=area,
                        plant_wide=plant_wide,
                    )
                    if app.sio:

                        app.sio.emit("on.event", data=event.serialize())
        else:
            if force:
                user = users.get_by_username(username="system")
                event, _ = events_engine.create(
                    message=message,
                    description=_clip(description, 256),
                    classification=classification,
                    priority=priority,
                    criticity=criticity,
                    user=user,
                    area=area,
                    plant_wide=plant_wide,
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
    alarms_engine = AlarmsLoggerEngine()   
    result = func(*args, **kwargs)
    alarm = args[0]
    if getattr(alarm, "_defer_persist", False):
        return result
    alarms_engine.put(
        id=alarm.identifier,
        state=alarm.state.state
    )
    if alarm.sio:
        alarm.sio.emit("on.alarm", data=alarm.serialize())
        
    return result

def validate_types(**validations):
    
    if "output" in validations:

        _output = validations.pop('output')

        if _output is None:

            _output = type(None)

    else:

        _output = None

    def decorator(func):
        try:
            signature = inspect.signature(func)
            accepted = set(signature.parameters)
            has_var_keyword = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
        except (TypeError, ValueError):
            accepted = None
            has_var_keyword = False

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            
            for key, value in kwargs.items():

                if key in validations:
                
                    if not isinstance(value, validations[key]):
                        message = f"Expected Input {key} as {validations[key]}, but got {type(value)} in {func}"
                        _logger.error(message)
                        raise TypeError(message)

                elif accepted is not None and (key in accepted or has_var_keyword):
                    continue

                else:
                    message = f"You didn't define {key} argument to validate in {func}"
                    _logger.error(message)
                    raise KeyError(message)

            # Call the wrapped function
            result = func(*args, **kwargs)

            # Validate the output type
            if _output:
                
                if isinstance(_output, tuple):
                    
                    for counter, expected in enumerate(_output):
                        
                        if not isinstance(result[counter], expected):

                            message = f"Expected output type ({counter}) {expected}, but got {type(result[counter])} in func {func}"
                            _logger.error(message)
                            raise TypeError(message)
                        
                else:

                    if not isinstance(result, _output):
                        message = f"Expected output type {_output}, but got {type(result)} in func {func}"
                        _logger.error(message)
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

        human = _humanize_logged_exception(ex, func)
        if human:
            message, level = human
            _logger.log(level, message)
            _logger.debug(
                "Historian/DB exception detail type=%s message=%s",
                type(ex).__name__,
                str(ex),
                exc_info=True,
            )
            return None

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
        _logger.error(msg)
        return None

@decorator
def db_rollback(func, args, kwargs):
    try:
        self = args[0]
        result = func(*args, **kwargs)
        return result

    except Exception as e:
        from .db_io import is_stale_historian_handle, log_historian_link_issue
        from ..catalog.partition import CrossAreaBindError

        if isinstance(e, CrossAreaBindError):
            raise

        _, _, e_traceback = sys.exc_info()
        e_message = str(e)
        e_line_number = e_traceback.tb_lineno
        where = f"{self.__class__.__name__}.{func.__name__}:L{e_line_number}"
        if is_stale_historian_handle(e):
            log_historian_link_issue(_logger, e, where=where, action="rollback")
        else:
            _logger.warning(
                "Rollback in [line %s] %s.%s - %s",
                e_line_number,
                self.__class__.__name__,
                func.__name__,
                e_message,
            )
        try:
            conn = self._db.connection()
            conn.rollback()
        except Exception:
            _logger.debug("db_rollback could not roll back connection", exc_info=True)
        if isinstance(e, (AttributeError, TypeError, ValueError, KeyError)):
            raise
        result = func(*args, **kwargs)

        return result