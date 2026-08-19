from ....extensions.api import api
from .system import ns as system_ns
from .clock import ns as clock_ns


def init_app():
    api.add_namespace(system_ns, path="/system")
    api.add_namespace(clock_ns, path="/system")
