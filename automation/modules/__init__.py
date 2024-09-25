# Init Resources
def init_app(app):

    from automation.modules.tags.resources import init_app as init_tags

    init_tags()