import dash
import dash_bootstrap_components as dbc
from ..pages.components.machines import MachinesComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},  # Primer nivel
                {"label": "Machines", "active": True},  # Página actual (sin enlace)
            ],
        ),
        dash.dcc.Location(id='machines_page', refresh=False),
        MachinesComponents.machines_table()
    ],
    fluid=False,
    className="my-3",
)