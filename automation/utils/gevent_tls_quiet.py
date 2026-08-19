# -*- coding: utf-8 -*-
"""Suppress benign client-side TLS noise from gevent/gunicorn workers.

Remote browsers reconnecting with self-signed certificates must not flood
app.log with greenlet tracebacks. Audit events are emitted via
``hmi_tls_telemetry`` (debounced per IP).
"""
from __future__ import annotations

import logging
import ssl


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


def _handle_client_side_tls(exc, origin: str = "") -> bool:
    try:
        from .hmi_tls_telemetry import (
            is_quiet_client_tls_error,
            record_client_tls_failure,
        )
    except Exception:
        return False
    if not is_quiet_client_tls_error(exc):
        return False
    record_client_tls_failure(exc, origin=origin)
    return True


def _patch_gevent_hub() -> None:
    try:
        from gevent.hub import Hub
    except ImportError:
        return

    if getattr(Hub.handle_error, "_pyautomation_tls_quiet", False):
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

    handle_error._pyautomation_tls_quiet = True  # type: ignore[attr-defined]
    Hub.handle_error = handle_error


def _patch_wsgi_handler() -> None:
    try:
        from gevent.pywsgi import WSGIHandler
    except ImportError:
        return

    if getattr(WSGIHandler.handle_error, "_pyautomation_tls_quiet", False):
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

    handle_error._pyautomation_tls_quiet = True  # type: ignore[attr-defined]
    WSGIHandler.handle_error = handle_error


def _patch_stream_server() -> None:
    """TLS handshake fails in StreamServer before WSGIHandler exists."""
    try:
        from gevent.server import StreamServer
    except ImportError:
        return

    if getattr(StreamServer.wrap_socket_and_handle, "_pyautomation_tls_quiet", False):
        return

    original = StreamServer.wrap_socket_and_handle

    def wrap_socket_and_handle(self, client_socket, address):
        origin = str(address[0]) if address and address[0] else ""
        try:
            return original(self, client_socket, address)
        except ssl.SSLError as err:
            if _handle_client_side_tls(err, origin=origin):
                try:
                    client_socket.close()
                except Exception:
                    pass
                return
            raise

    wrap_socket_and_handle._pyautomation_tls_quiet = True  # type: ignore[attr-defined]
    StreamServer.wrap_socket_and_handle = wrap_socket_and_handle


def install_gevent_tls_quiet_hooks() -> None:
    """Idempotent: call from gunicorn ``post_worker_init``."""
    _patch_gevent_hub()
    _patch_wsgi_handler()
    _patch_stream_server()
    logging.getLogger("pyautomation").debug("Gevent TLS quiet hooks installed")
