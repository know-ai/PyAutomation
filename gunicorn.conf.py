import os
import logging

# Long-lived WebSocket/Socket.IO sessions must not be cut by the default 30s worker timeout.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

log_folder = os.path.join(".", "logs")
if not os.path.exists(log_folder):
    os.makedirs(log_folder)

log_file = os.path.join(log_folder, "app.log")
log_format = "%(asctime)s:%(levelname)s:%(message)s"
level = logging.WARNING

if not log_file:
    logging.basicConfig(level=level, format=log_format)
else:
    logging.basicConfig(filename=log_file, level=level, format=log_format)


def post_worker_init(worker):  # noqa: ARG001
    """Silencia handshakes TLS de cliente; telemetría en Events (debounced por IP)."""
    try:
        from automation.utils.gevent_tls_quiet import install_gevent_tls_quiet_hooks

        install_gevent_tls_quiet_hooks()
    except Exception:
        logging.getLogger("pyautomation").debug(
            "Gevent TLS quiet hooks skipped",
            exc_info=True,
        )
