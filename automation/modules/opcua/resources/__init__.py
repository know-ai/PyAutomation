from ....extensions.api import api


def init_app():

    from .clients import ns as ns_clients
    from .server import ns as ns_server

    api.add_namespace(ns_clients, path="/opcua/clients")
    api.add_namespace(ns_server, path="/opcua/server")

