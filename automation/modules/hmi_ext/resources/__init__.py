from ....extensions.api import api
from .extensions import ns


def init_app():
    api.add_namespace(ns, path="/hmi")
