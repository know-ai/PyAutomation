from ....extensions.api import api


def init_app():
    from .history import ns

    api.add_namespace(ns, path="/history")
