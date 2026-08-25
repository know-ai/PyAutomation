from ....extensions.api import api
from .admin import ns as admin_ns


def init_app():
    api.add_namespace(admin_ns, path="/admin")
