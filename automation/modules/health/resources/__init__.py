from ....extensions.api import api
from .health import ns as health_ns


def init_app():
    """
    Register healthcheck resources with the global API instance.
    """
    api.add_namespace(health_ns, path="/health")


