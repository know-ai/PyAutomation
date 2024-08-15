import dash
import dash_mantine_components as dmc
import dash_bootstrap_components as dbc
from automation.pages.components.opcua import FileTree, OPCUAComponents

# Set React version to 18.2.0
dash._dash_renderer._set_react_version('18.2.0')

dash.register_page(__name__, path="/")

data = [
    {
        'title': 'iDetectFugas', 'key': 'ns=2;i=1', 'children': [
            {'title': 'FI_02', 'key': 'ns=2;i=2', 'children': [], 'NodeClass': 'Variable'},
            {'title': 'PI_02', 'key': 'ns=2;i=3', 'children': [], 'NodeClass': 'Variable'},
            {'title': 'ROHL_02', 'key': 'ns=2;i=4', 'children': [], 'NodeClass': 'Variable'},
            {'title': 'TI_02', 'key': 'ns=2;i=5', 'children': [], 'NodeClass': 'Variable'}
        ], 'NodeClass': 'Object'
    }
]

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
                        dbc.Col([
                            FileTree(data).render(),
                            FileTree(data).render()
                        ],
                        width=2),
                        dbc.Col([
                            dash.html.Div("One of three columns")
                        ],
                        width=8),
                        dbc.Col([
                            dash.html.Div("One of three columns")
                        ],
                        width=2),
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