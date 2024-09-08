import dash
from .tags import init_callback as init_callback_tags
from .opcua import init_callback as init_callback_opcua
from .alarms import init_callback as init_callback_alarms


def init_callbacks(app:dash.Dash):
    r"""
    Documentation here
    """

    init_callback_tags(app=app)
    init_callback_opcua(app=app)
    init_callback_alarms(app=app)