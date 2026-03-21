from ....extensions.api import api


def init_app():
    from .linear_referencing_geospatial import ns as ns_linear_referencing

    api.add_namespace(ns_linear_referencing, path="/linear-referencing-geospatial")
