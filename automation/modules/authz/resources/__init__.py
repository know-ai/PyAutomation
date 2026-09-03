from ....extensions.api import api


def init_app():
    from .authz import ns

    api.add_namespace(ns, path="/authz")
