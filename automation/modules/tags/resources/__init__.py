from ....extensions.api import api


def init_app():

    from .tags import ns as ns_tags

    api.add_namespace(ns_tags, path="/tags")