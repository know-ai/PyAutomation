from ....extensions.api import api


def init_app():

    from .machines import ns as ns_machines

    api.add_namespace(ns_machines, path="/machines")