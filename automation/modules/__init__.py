from .users import Role, Roles, Users

# Init Resources
def init_app(app):

    from automation.modules.tags.resources import init_app as init_tags
    from automation.modules.alarms.resources import init_app as init_alarms

    init_tags()
    init_alarms()