import dash
import dash_bootstrap_components as dbc
from automation.pages.components import Components
from automation.pages.components.machines import MachinesComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},  # Primer nivel
                {"label": "Machines Detailed", "active": True},  # Página actual (sin enlace)
            ],
        ),
        dash.dcc.Location(id='machines_detailed_page', refresh=False),
        MachinesComponents.machines_tabs(),
        Components.modal_error(
            title="Error",
            modal_id="modal-error-subscription",
            button_close_id="close-modal-error-button-subscription",
            body_id="modal-error-body-subscription"
        ),
    ],
    fluid=False,
    className="my-3",
)