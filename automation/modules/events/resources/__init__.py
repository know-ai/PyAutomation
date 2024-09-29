from automation.extensions.api import api


def init_app():

    from .events import ns as ns_events
    from .logs import ns as ns_logs

    api.add_namespace(ns_events, path="/events")
    api.add_namespace(ns_logs, path="/logs")