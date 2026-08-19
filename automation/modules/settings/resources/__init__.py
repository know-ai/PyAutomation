from .settings import ns
from .clock import ns as clock_ns

def init_app():
    from ....extensions.api import api
    api.add_namespace(ns, path="/settings")
    api.add_namespace(clock_ns, path="/settings")
