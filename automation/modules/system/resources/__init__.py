from ....extensions.api import api
from .system import ns as system_ns


def init_app():
    api.add_namespace(system_ns, path="/system")
