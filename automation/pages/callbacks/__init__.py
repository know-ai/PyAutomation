import dash
from .tags import init_callback as init_callback_tags
from .opcua import init_callback as init_callback_opcua
from .alarms import init_callback as init_callback_alarms
from .alarms_summary import init_callback as init_callback_alarms_summary
from .trends import init_callback as init_callback_trends
from .db import init_callback as init_callback_db


def init_callbacks(app:dash.Dash):
    r"""
    Documentation here
    """

    init_callback_tags(app=app)
    init_callback_opcua(app=app)
    init_callback_alarms(app=app)
    init_callback_alarms_summary(app=app)
    init_callback_trends(app=app)
    init_callback_db(app=app)