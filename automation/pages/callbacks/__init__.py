import dash
from .tags import init_callback as init_callback_tags


def init_callbacks(app:dash.Dash):
    r"""
    Documentation here
    """

    init_callback_tags(app=app)