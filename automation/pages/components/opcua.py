import dash
from automation.singleton import Singleton
import dash_mantine_components as dmc
import dash_bootstrap_components as dbc
from dash_iconify import DashIconify


class FileTree:
    r"""
    Documentation here
    """
    def __init__(self):
        
        self.data = None
        self.folder_name = None

    def render(self, data) -> dmc.Accordion:
        r"""
        Documentation here
        """
        self.data = data
        return dmc.Accordion(
            self.build_tree(self.data),
            multiple=True,
            id="opcua_server_tree"
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
                    options=[{'label': '', 'value': f"{self.folder_name}/{key}"}],
                    id={'type': 'file-checklist', 'index': f"{self.folder_name}/{key}"},
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
                self.folder_name = node['title']
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


class OPCUAComponents(Singleton):

    @classmethod
    def add_server(cls, title:str, modal_id:str, body_id:str, ok_button_id:str, cancel_button_id:str):

        return dash.html.Div(
            [
                dash.dcc.Location(id='communications_page', refresh=False),
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
    
    @classmethod
    def get_opcua_tree(cls, app):

        clients = app.automation.get_opcua_clients()
        data = list()
        for client_name, _ in clients.items():
            
            opcua_tree = app.automation.get_opcua_tree(client_name=client_name)
            opcua_tree = opcua_tree[0]['Objects'][0]
            opcua_tree["title"] = client_name
            data.append(opcua_tree)

        data = file_tree.render(data)

        return data

    def data_access_view_table(self, data:list=[])->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        self.data = data
        return dash.dash_table.DataTable(
            data=self.data,
            columns=[ 
                {'name': 'server', 'id': 'server', 'editable': False}, 
                {'name': 'namespace', 'id': 'namespace', 'editable': False}, 
                {'name': 'data_type', 'id': 'data_type', 'editable': False}, 
                {'name': 'display_name', 'id': 'display_name', 'editable': False}, 
                {'name': 'value', 'id': 'value', 'editable': False},
                {'name': 'source_timestamp', 'id': 'source_timestamp', 'editable': False},
                {'name': 'status_code', 'id': 'status_code', 'editable': False}
            ],
            id="data_access_view_datatable",
            # row_selectable='single',
            page_action="native",
            page_current= 0,
            page_size= 10,
            persistence=True,
            editable=False,
            persisted_props=['data'],
            export_format='xlsx',
            export_headers='display',
        )
    
    def update_data_access_view(self, namespace, value, timestamp)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        _data = self.data.copy()
        for counter, data in enumerate(_data):

            if namespace==data["namespace"]:

                self.data[counter]["value"] = value
                self.data[counter]["source_timestamp"] = timestamp
        
        return self.data