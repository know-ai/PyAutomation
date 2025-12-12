from ....extensions.api import api


def init_app():

    from .database import ns as ns_database

    api.add_namespace(ns_database, path="/database")

