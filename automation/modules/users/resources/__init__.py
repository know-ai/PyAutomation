from ....extensions.api import api


def init_app():

    from .users import ns as ns_users
    from .roles import ns as ns_roles

    api.add_namespace(ns_users, path="/users")
    api.add_namespace(ns_roles, path="/users/roles")