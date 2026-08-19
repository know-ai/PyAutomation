import os
import logging

log_folder = os.path.join(".", "logs")
if not os.path.exists(log_folder):
    
    os.makedirs(log_folder)

log_file = os.path.join(log_folder, 'app.log')
log_format = "%(asctime)s:%(levelname)s:%(message)s"
level = logging.WARNING

if not log_file:
    
    logging.basicConfig(level=level, format=log_format)

else:

    logging.basicConfig(filename=log_file, level=level, format=log_format)


def _client_origin_from_handler(handler) -> str:
    try:
        address = getattr(handler, "client_address", None)
        if address and address[0]:
            return str(address[0])
        environ = getattr(handler, "environ", None) or {}
        forwarded = environ.get("HTTP_X_FORWARDED_FOR") or ""
        if forwarded:
            return forwarded.split(",")[0].strip()
        remote = environ.get("REMOTE_ADDR") or ""
        return str(remote)
    except Exception:
        return ""


def _handle_client_side_tls(exc, origin: str = ""):
    try:
        from automation.utils.hmi_tls_telemetry import (
            is_quiet_client_tls_error,
            record_client_tls_failure,
        )
    except Exception:
        return False
    if not is_quiet_client_tls_error(exc):
        return False
    record_client_tls_failure(exc, origin=origin)
    return True


def post_worker_init(worker):  # noqa: ARG001
    """Silencia handshakes TLS de cliente que no son fallos de la app."""
    import ssl

    try:
        from gevent.hub import Hub
    except ImportError:
        return

    original = Hub.handle_error

    def handle_error(self, context, type_, value, tb):
        if _handle_client_side_tls(value):
            return
        if isinstance(value, ssl.SSLError):
            reason_s = str(getattr(value, "reason", None) or value)
            if "EOF occurred in violation of protocol" in reason_s:
                return
        return original(self, context, type_, value, tb)

    Hub.handle_error = handle_error
    _silence_wsgi_client_disconnects()


def _silence_wsgi_client_disconnects() -> None:
    """pywsgi imprime traceback cuando el navegador cierra el TLS a media respuesta."""
    import ssl

    try:
        from gevent.pywsgi import WSGIHandler
    except ImportError:
        return

    original = WSGIHandler.handle_error
    quiet_types = (ssl.SSLEOFError, ssl.SSLZeroReturnError, BrokenPipeError, ConnectionResetError)

    def handle_error(self, type, value, tb):  # noqa: A002
        origin = _client_origin_from_handler(self)
        if isinstance(value, quiet_types):
            try:
                self.close_connection = True
            except Exception:
                pass
            if origin:
                _handle_client_side_tls(value, origin=origin)
            return
        if _handle_client_side_tls(value, origin=origin):
            try:
                self.close_connection = True
            except Exception:
                pass
            return
        return original(self, type, value, tb)

    WSGIHandler.handle_error = handle_error
