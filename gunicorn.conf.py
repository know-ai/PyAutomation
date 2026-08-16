import os, logging

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


def post_worker_init(worker):  # noqa: ARG001
    """Silencia handshakes TLS de cliente que no son fallos de la app."""
    import ssl

    try:
        from gevent.hub import Hub
    except ImportError:
        return

    noisy = frozenset({
        "HTTP_REQUEST",
        "HTTPS_PROXY_REQUEST",
        "UNEXPECTED_EOF_WHILE_READING",
    })
    original = Hub.handle_error

    def handle_error(self, context, type_, value, tb):
        if isinstance(value, ssl.SSLZeroReturnError):
            return
        if isinstance(value, ssl.SSLError):
            reason = getattr(value, "reason", None)
            reason_s = str(reason or value)
            if reason in noisy or any(token in reason_s for token in noisy):
                return
        return original(self, context, type_, value, tb)

    Hub.handle_error = handle_error