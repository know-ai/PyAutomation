import dash
import dash_bootstrap_components as dbc
from automation.pages.components import Components
from automation.pages.components.database import DatabaseComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},
                {"label": "Database", "active": True},
            ],
        ),
        DatabaseComponents.create_db_config_form()
    ],
    fluid=False,
    className="my-3"
)