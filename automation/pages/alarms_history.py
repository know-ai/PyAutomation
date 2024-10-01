import dash
import dash_bootstrap_components as dbc
from ..pages.components.alarms_summary import AlarmSummaryComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},  # Primer nivel
                {"label": "Alarms", "href": "/alarms"},  # Segundo nivel
                {"label": "Alarms History", "active": True},  # Página actual (sin enlace)
            ],
        ),
        dash.dcc.Location(id='alarms_history_page', refresh=False),
        AlarmSummaryComponents.alarm_summary_table()
    ],
    fluid=False,
    className="my-3",
)