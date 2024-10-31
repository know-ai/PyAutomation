from .users import Role, Roles, Users

# Init Resources
def init_app(app):

    from ..modules.tags.resources import init_app as init_tags
    from ..modules.alarms.resources import init_app as init_alarms
    from ..modules.users.resources import init_app as init_users
    from ..modules.events.resources import init_app as init_events

    init_tags()
    init_alarms()
    init_users()
    init_events()