from automation.extensions.api import api


def init_app():

    from .events import ns as ns_events

    api.add_namespace(ns_events, path="/events")