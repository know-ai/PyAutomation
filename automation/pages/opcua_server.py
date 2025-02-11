import dash
import dash_bootstrap_components as dbc
from automation.pages.components import Components
from automation.pages.components.opcua_server import OPCUAServerComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dash.dcc.Location(id='opcua_server', refresh=False),
        dbc.Breadcrumb(
            items=[
                {"label": "Communications", "href": "/"},
                {"label": "OPCUA Server", "active": True},
            ],
        ),
        Components.modal_error(
            title="Error",
            modal_id="modal-opcua-server",
            button_close_id="close-opcua-server",
            body_id="modal-body-opcua-server"
        ),
        Components.modal_error(
            title="Success",
            modal_id="modal-success-opcua-server",
            button_close_id="close-success-opcua-server",
            body_id="modal-success-body-opcua-server"
        ),
        Components.modal_confirm(
            title="Confirmation",
            modal_id="modal-update-opcua-server-centered",
            body_id="modal-update-opcua-server-body",
            yes_button_id="update-opcua-server-yes",
            no_button_id="update-opcua-server-no"
        ),
        OPCUAServerComponents.opcua_server_table()
    ],
    fluid=False,
    className="my-3"
)