from ....extensions.api import api


def init_app():

    from .alarms import ns as ns_alarms
    from .summary import ns as ns_summary

    api.add_namespace(ns_alarms, path="/alarms")
    api.add_namespace(ns_summary, path="/alarms/summary")
    from . import p2_api  # noqa: F401  — registers P2 routes on ns_alarms