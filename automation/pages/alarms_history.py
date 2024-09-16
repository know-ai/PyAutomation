import dash
import dash_bootstrap_components as dbc

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},  # Primer nivel
                {"label": "Alarms", "href": "/alarms"},  # Segundo nivel
                {"label": "Alarms History", "active": True},  # Página actual (sin enlace)
            ],
        )
    ],
    fluid=False,
    className="my-3",
)