import dash
import dash_mantine_components as dmc
import dash_bootstrap_components as dbc
from automation.pages.components.opcua import OPCUAComponents

# Set React version to 18.2.0
dash._dash_renderer._set_react_version('18.2.0')
dash.register_page(__name__, path="/")
opcua_components = OPCUAComponents()


layout = dmc.MantineProvider([
    dash.html.Div(
        [
            dbc.Row(
                [
                    dbc.Col([
                        dash.html.H1("OPCUA")
                    ],
                    width=2),
                    dbc.Col([
                        dash.html.Div(
                            [
                                dbc.Button("Create", className="me-md-2", color="info", id="add_server_button"),   
                                dbc.Button("Remove", className="me-md-2", color="danger", disabled=True, id="remove_server_button"),   
                            ],
                            className="d-grid gap-2 d-md-flex justify-content-md-end",
                        )
                    ],
                    width={"size": 3, "offset": 7})
                ]
            )
        ]
    ),
    dash.html.Div(
            [
                dbc.Row(
                    [
                        dbc.Col([], id="server_tree",  width=2),
                        dbc.Col(opcua_components.data_access_view_table(), id="data_access_view_table", width=10),
                        # dbc.Col([dash.html.Div("One of three columns")], width=2),
                    ]
                ),
            ]
        ),
    OPCUAComponents.add_server(
        title="Add Server", 
        modal_id="add_server_modal", 
        body_id="add_server_body_modal", 
        ok_button_id="add_server_ok_button_modal", 
        cancel_button_id="add_server_cancel_button_modal"
        )
    ])