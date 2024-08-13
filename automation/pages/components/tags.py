import dash
import dash_bootstrap_components as dbc
from automation import PyAutomation
from automation.variables import VARIABLES
from automation.utils import generate_dropdown_conditional

app = PyAutomation()

if hasattr(app, 'dash_app'):

    data = app.dash_app.tags_table_data()

else:

    data = list()

class TagsComponents:

    @classmethod
    def create_tag_form(cls):
        r"""
        Documentation here
        """
        return dash.html.Div(
            [
                dash.dcc.Location(id='tags_page', refresh=False),
                dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            dbc.Row([
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="Tag Name", id="tag_name_input")], size="md"),
                                    dbc.InputGroup(
                                        [
                                            dbc.InputGroupText("Variable"),
                                            dbc.Select(
                                                options=[
                                                    {"label": variable, "value": variable} for variable in VARIABLES.keys()
                                                ],
                                                id="variable_input"
                                            ),
                                            
                                        ],
                                        size="md"
                                    )
                                ],
                                width=3),
                                dbc.Col([
                                    dbc.InputGroup(
                                        [
                                            dbc.InputGroupText("Unit"),
                                            dbc.Select(
                                                options=[],
                                                id="unit_input",
                                                disabled=True
                                            ),
                                        ],
                                        size="md"
                                    ),
                                    dbc.InputGroup(
                                        [
                                            dbc.InputGroupText("Datatype"),
                                            dbc.Select(
                                                options=[
                                                    {'label': 'Float', 'value': 'float'},
                                                    {'label': 'Integer', 'value': 'integer'},
                                                    {'label': 'Boolean', 'value': 'boolean'},
                                                    {'label': 'String', 'value': 'string'}
                                                ],
                                                id="datatype_input"
                                            ),
                                            
                                        ],
                                        size="md"
                                    ),
                                ],
                                width=3),
                                dbc.Col([
                                    dbc.InputGroup([dbc.InputGroupText(dbc.RadioButton(id="description_radio_button"), class_name="radiobutton-box"), dbc.Input(placeholder="Description (Optional)", id="description_input", disabled=True)], size="md"),
                                    dbc.InputGroup([dbc.InputGroupText(dbc.RadioButton(id="display_name_radio_button"), className="radiobutton-box"), dbc.Input(placeholder="Display Name (Optional)", id="display_name_input", disabled=True)], size="md")
                                ],
                                width=3),
                                dbc.Col([
                                    dbc.InputGroup(
                                        [
                                            dbc.InputGroupText("OPCUA"),
                                            dbc.Select(
                                                options=[
                                                    {'label': 'None', 'value': ''},
                                                    {'label': 'Server 1', 'value': 'Server 1'},
                                                    {'label': 'Server 2', 'value': 'Server 2'},
                                                    {'label': 'Server 3', 'value': 'Server 3'},
                                                    {'label': 'Server 4', 'value': 'Server 4'}
                                                ],
                                                id="opcua_address_input"
                                            ),
                                            
                                        ],
                                        size="md"
                                    ),
                                    dbc.InputGroup(
                                        [
                                            dbc.InputGroupText("Node"),
                                            dbc.Select(
                                                options=[
                                                    {'label': 'None', 'value': ''},
                                                    {'label': 'ns=2;i=1', 'value': 'ns=2;i=1'},
                                                    {'label': 'ns=2;i=2', 'value': 'ns=2;i=2'},
                                                    {'label': 'ns=2;i=3', 'value': 'ns=2;i=3'},
                                                    {'label': 'ns=2;i=4', 'value': 'ns=2;i=4'}
                                                ],
                                                id="node_namespace_input",
                                                disabled=True
                                            ),
                                            
                                        ],
                                        size="md",
                                    )
                                ],
                                width=3)
                            ]),
                            dbc.Button("Create", color="primary", outline=True, disabled=True, id="create_tag_button"),
                        ],
                        title="Create Tag",
                    )
                ],
                start_collapsed=True,
                )
            ]
        )

    @classmethod
    def tags_table(cls)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """

        return dash.dash_table.DataTable(
            data=data,
            columns=[
                {'name': 'id', 'id': 'id', 'editable': False}, 
                {'name': 'name', 'id': 'name'}, 
                {'name': 'unit', 'id': 'unit', 'presentation': 'dropdown'}, 
                {'name': 'data_type', 'id': 'data_type', 'presentation': 'dropdown'}, 
                {'name': 'description', 'id': 'description'}, 
                {'name': 'display_name', 'id': 'display_name'}, 
                {'name': 'opcua_address', 'id': 'opcua_address', 'presentation': 'dropdown'}, 
                {'name': 'node_namespace', 'id': 'node_namespace', 'presentation': 'dropdown'}
            ],
            id="tags_datatable",
            filter_action="native",
            sort_action="native",
            sort_mode="multi",
            row_deletable=True,
            selected_columns=[],
            page_action="native",
            page_current= 0,
            page_size= 10,
            persistence=True,
            editable=True,
            dropdown={
                'data_type': {
                    'options': [
                        {'label': 'Float', 'value': 'float'},
                        {'label': 'Integer', 'value': 'integer'},
                        {'label': 'Boolean', 'value': 'boolean'},
                        {'label': 'String', 'value': 'string'}
                    ]
                },
                'opcua_address': {
                    'options': [
                        {'label': 'None', 'value': ''},
                        {'label': 'Server 1', 'value': 'Server 1'},
                        {'label': 'Server 2', 'value': 'Server 2'},
                        {'label': 'Server 3', 'value': 'Server 3'},
                        {'label': 'Server 4', 'value': 'Server 4'}
                    ]
                },
                'node_namespace':{
                    'options': [
                        {'label': 'None', 'value': ''},
                        {'label': 'ns=2;i=1', 'value': 'ns=2;i=1'},
                        {'label': 'ns=2;i=2', 'value': 'ns=2;i=2'},
                        {'label': 'ns=2;i=3', 'value': 'ns=2;i=3'},
                        {'label': 'ns=2;i=4', 'value': 'ns=2;i=4'}
                    ]
                }
            },
            dropdown_conditional=generate_dropdown_conditional(),
            persisted_props=['data'],
            export_format='xlsx',
            export_headers='display',
        )