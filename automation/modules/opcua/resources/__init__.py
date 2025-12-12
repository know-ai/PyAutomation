from ....extensions.api import api


def init_app():

    from .clients import ns as ns_clients

    api.add_namespace(ns_clients, path="/opcua/clients")

