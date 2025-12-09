from .settings import ns

def init_app():
    from ....extensions.api import api
    api.add_namespace(ns, path="/settings")
