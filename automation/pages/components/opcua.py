import dash
import dash_mantine_components as dmc
import dash_bootstrap_components as dbc
from dash_iconify import DashIconify


class OPCUAComponents:

    @classmethod
    def add_server(cls, title:str, modal_id:str, body_id:str, ok_button_id:str, cancel_button_id:str):

        return dash.html.Div(
            [
                dbc.Modal(
                    [
                        dbc.ModalHeader(dbc.ModalTitle(title), close_button=True),
                        dbc.ModalBody(
                            dash.html.Div(
                                [
                                    dash.html.H6('Server Information'),  # This is the title
                                    dash.html.Div([
                                        dbc.InputGroup([dbc.InputGroupText("Name"), dbc.Input(placeholder="Server 1", id="opcua_client_name_input")], size="sm"),
                                        dbc.InputGroup([dbc.InputGroupText("Host"), dbc.Input(placeholder="127.0.0.1", id="opcua_client_host_input")], size="sm"),
                                        dbc.InputGroup([dbc.InputGroupText("Port"), dbc.Input(placeholder="4840", id="opcua_client_port_input")], size="sm"),
                                    ], style={'border': '1px solid black', 'padding': '10px'}),

                                    dash.html.H6('Security Settings'),  # This is the title
                                    dash.html.Div([
                                        dbc.InputGroup(
                                            [
                                                dbc.InputGroupText("Security Policy"),
                                                dbc.Select(
                                                    options=[
                                                        {"label": "None", "value": None},
                                                        {"label": "Basic128Rsa15", "value": "Basic128Rsa15"},
                                                        {"label": "Basic256Sha256", "value": "Basic256Sha256"},
                                                        {"label": "Aes128Sha256RsaOaep", "value": "Aes128Sha256RsaOaep"},
                                                        {"label": "Aes256Sha256RsaPss", "value": "Aes256Sha256RsaPss"},
                                                    ]
                                                ),
                                                
                                            ]
                                        ),
                                        dbc.InputGroup(
                                            [
                                                dbc.InputGroupText("Message Security Mode"),
                                                dbc.Select(
                                                    options=[
                                                        {"label": "None", "value": None},
                                                        {"label": "Sign", "value": "Sign"},
                                                        {"label": "Sign & Encrypt", "value": "Sign & Encrypt"},
                                                    ]
                                                )
                                            ]
                                        )
                                    ], style={'border': '1px solid black', 'padding': '10px'}),

                                    dash.html.H6('Authentication Settings'),  # This is the title
                                    dash.html.Div([
                                        dbc.InputGroup([
                                            dbc.RadioItems(
                                                id="radio-1",
                                                options=[{"label": "Anonymous", "value": 1}],
                                            ),
                                        ], className="mb-3"),
                                        dash.html.Hr(),
                                        dbc.InputGroup([
                                            dbc.Row([
                                                dbc.Col([
                                                    dbc.RadioItems(
                                                        id="radio-2",
                                                        options=[{"label": "", "value": 2}]
                                                    ),
                                                ],
                                                width=1),
                                                dbc.Col([
                                                    dbc.InputGroup([dbc.InputGroupText("Username"), dbc.Input(disabled=True)], size="sm"),
                                                    dbc.InputGroup([dbc.InputGroupText("Password"), dbc.Input(disabled=True)], size="sm"),
                                                ],
                                                width=11)
                                            ])                                            
                                        ], className="mb-3"),
                                        dash.html.Hr(),
                                        dbc.InputGroup([
                                            dbc.Row([
                                                dbc.Col([
                                                    dbc.RadioItems(
                                                        id="radio-2",
                                                        options=[{"label": "", "value": 2}]
                                                    ),
                                                ],
                                                width=1),
                                                dbc.Col([
                                                    dbc.InputGroup([dbc.InputGroupText("Certificate"), dbc.Input(disabled=True)], size="sm"),
                                                    dbc.InputGroup([dbc.InputGroupText("Private Key"), dbc.Input(disabled=True)], size="sm"),
                                                ],
                                                width=11)
                                            ])                                            
                                        ], className="mb-3"),
                                    ], style={'border': '1px solid black', 'padding': '10px'}),
                                ]
                            ),
                            id=body_id),
                        dbc.ModalFooter(
                            [
                                dbc.Button(
                                    "OK",
                                    id=ok_button_id,
                                    className="ms-auto",
                                    n_clicks=0,
                                ),
                                dbc.Button(
                                    "Cancel",
                                    id=cancel_button_id,
                                    className="ms-auto",
                                    n_clicks=0,
                                )
                            ]
                        ),
                    ],
                    id=modal_id,
                    centered=True,
                    is_open=False,
                ),
            ]
        )


class FileTree:
    r"""
    Documentation here
    """
    def __init__(self):
        
        self.data = None

    def render(self, data) -> dmc.Accordion:
        r"""
        Documentation here
        """
        self.data = data
        return dmc.Accordion(
            self.build_tree(self.data),
            multiple=True
        )

    def flatten(self, l):
        r"""
        Documentation here
        """
        return [item for sublist in l for item in sublist]

    def make_file(self, file_name, key):
        r"""
        Documentation here
        """
        return dmc.Text(
            [
                dash.dcc.Checklist(
                    options=[{'label': '', 'value': key}],
                    id={'type': 'file-checklist', 'index': key},
                    style={"display": "inline-block"}
                ),
                DashIconify(icon="akar-icons:file"),
                " ",
                file_name
            ],
            style={"paddingTop": '5px'}
        )

    def make_folder(self, folder_name):
        r"""
        Documentation here
        """
        return [DashIconify(icon="akar-icons:folder"), " ", folder_name]

    def build_tree(self, nodes):
        r"""
        Documentation here
        """
        d = []
        for i, node in enumerate(nodes):
            if node['children']:
                children = self.flatten([self.build_tree(node['children'])])
                d.append(
                    dmc.AccordionItem(
                        children=[
                            dmc.AccordionControl(self.make_folder(node['title'])),
                            dmc.AccordionPanel(children)
                        ],
                        value=f"item-{i}"
                    )
                )
            else:
                d.append(self.make_file(node['title'], node['key']))
        return d


file_tree = FileTree()