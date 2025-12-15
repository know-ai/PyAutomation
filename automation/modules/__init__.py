from .users import Role, Roles, Users

# Init Resources
def init_app(app):

    from ..modules.tags.resources import init_app as init_tags
    from ..modules.alarms.resources import init_app as init_alarms
    from ..modules.users.resources import init_app as init_users
    from ..modules.events.resources import init_app as init_events
    from ..modules.settings.resources import init_app as init_settings
    from ..modules.opcua.resources import init_app as init_opcua
    from ..modules.database.resources import init_app as init_database
    from ..modules.machines.resources import init_app as init_machines
    from ..modules.health.resources import init_app as init_health

    init_tags()
    init_alarms()
    init_users()
    init_events()
    init_settings()
    init_opcua()
    init_database()
    init_machines()
    init_health()