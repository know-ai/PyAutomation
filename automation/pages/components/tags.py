import dash
import dash_bootstrap_components as dbc
from automation import PyAutomation

app = PyAutomation()

if hasattr(app, 'dash_app'):

    data = app.dash_app.tags_table_data()

else:

    data = list()

create_tag_form = dash.html.Div(
        [
            dash.dcc.Location(id='tags_page', refresh=False),
            dbc.Accordion(
            [
                dbc.AccordionItem(
                    [
                        dbc.Row([
                            dbc.Col([
                                dbc.InputGroup([dbc.Input(placeholder="Tag Name", id="tag_name_input")], size="sm"),
                                dbc.InputGroup(
                                    [
                                        dbc.InputGroupText("Variable"),
                                        dbc.Select(
                                            options=[
                                                {"label": "Pressure", "value": 1},
                                                {"label": "Mass Flow", "value": 2},
                                                {"label": "Temperature", "value": 3},
                                                {"label": "Density", "value": 4},
                                            ],
                                            id="variable_input"
                                        ),
                                        
                                    ],
                                    size="sm"
                                )
                            ],
                            width=3),
                            dbc.Col([
                                dbc.InputGroup(
                                    [
                                        dbc.InputGroupText("Unit"),
                                        dbc.Select(
                                            options=[
                                                {"label": "Pa", "value": "Pa"},
                                                {"label": "kPa", "value": "kPa"},
                                                {"label": "Psi", "value": "psi"},
                                                {"label": "bar", "value": "bar"},
                                            ],
                                            id="unit_input",
                                            disabled=True
                                        ),
                                    ],
                                    size="sm"
                                ),
                                dbc.InputGroup(
                                    [
                                        dbc.InputGroupText("Datatype"),
                                        dbc.Select(
                                            options=[
                                                {"label": "Float", "value": 'float'},
                                                {"label": "Integer", "value": 'integer'},
                                                {"label": "String", "value": 'string'}
                                            ],
                                            id="datatype_input"
                                        ),
                                        
                                    ],
                                    size="sm"
                                ),
                            ],
                            width=3),
                            dbc.Col([
                                dbc.InputGroup([dbc.InputGroupText(dbc.Checkbox(id="description_radio_button")), dbc.Input(placeholder="Description (Optional)", id="description_input", disabled=True)], size="sm"),
                                dbc.InputGroup([dbc.InputGroupText(dbc.Checkbox(id="display_name_radio_button")), dbc.Input(placeholder="Display Name (Optional)", id="display_name_input", disabled=True)], size="sm")
                            ],
                            width=3),
                            dbc.Col([
                                dbc.InputGroup([dbc.InputGroupText(dbc.Checkbox(id="opcua_radio_button")), dbc.Input(placeholder="opc.tcp://url:port/ (Optional)", id="opcua_address_input", disabled=True)], size="sm"),
                                dbc.InputGroup(
                                    [
                                        dbc.InputGroupText("Namespace"),
                                        dbc.Select(
                                            options=[
                                                {"label": "ns=2;i=1", "value": "ns=2;i=1"},
                                                {"label": "ns=2;i=2", "value": "ns=2;i=2"},
                                                {"label": "ns=2;i=3", "value": "ns=2;i=2"}
                                            ],
                                            id="node_namespace_input",
                                            disabled=True
                                        ),
                                        
                                    ],
                                    size="sm"
                                )
                            ],
                            width=3)
                        ]),
                        dbc.Button("Create", color="success", outline=True, disabled=True, id="create_tag_button"),
                    ],
                    title="Create Tag",
                )
            ],
            start_collapsed=True,
        )
    ]
    )

tags_table = dash.dash_table.DataTable(
        data,
        [{'name': 'id', 'id': 'id', 'editable': False}, {'name': 'name', 'id': 'name'}, {'name': 'unit', 'id': 'unit'}, {'name': 'data_type', 'id': 'data_type'}, {'name': 'description', 'id': 'description'}, {'name': 'display_name', 'id': 'display_name'}, {'name': 'opcua_address', 'id': 'opcua_address'}, {'name': 'node_namespace', 'id': 'node_namespace'}],
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
        persisted_props=['data'],
        export_format='xlsx',
        export_headers='display',
    )