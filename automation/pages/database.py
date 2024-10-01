import dash
import dash_bootstrap_components as dbc
from ..pages.components import Components
from ..pages.components.database import DatabaseComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},
                {"label": "Database", "active": True},
            ],
        ),
        DatabaseComponents.create_db_config_form(),
        Components.modal_error(
            title="Database Connection",
            modal_id="modal-db-connection",
            button_close_id="close-model-db-connection",
            body_id="modal-body-db-connection"
        )
    ],
    fluid=False,
    className="my-3"
)
