import dash
import dash_bootstrap_components as dbc
from ... import PyAutomation

app = PyAutomation()

class AlarmsComponents:

    @classmethod
    def create_alarm_form(cls):
        r"""
        Documentation here
        """
        return dash.html.Div(
            [
                dash.dcc.Location(id='alarms_page', refresh=False),
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.InputGroup(
                                                [
                                                    dbc.InputGroupText("Tag"),
                                                    dbc.Select(
                                                        options=[
                                                            {"label": tag["name"], "value": tag["name"]} for tag in app.cvt.get_tags()
                                                        ],
                                                        id="tag_alarm_input"
                                                    ),   
                                                ],
                                                size="md",
                                            ),
                                            width=12,
                                            className="col-sm-12 col-md-3"
                                        ),
                                        
                                        dbc.Col(
                                            dbc.InputGroup(
                                                [
                                                    dbc.Input(placeholder="Alarm Name", id="alarm_name_input"),
                                                ], 
                                                size="md"
                                            ),
                                            width=12,
                                            className="col-sm-12 col-md-3"
                                        ),
                                        
                                        dbc.Col(
                                            dbc.InputGroup(
                                                [
                                                    dbc.InputGroupText(dbc.RadioButton(id="alarm_description_radio_button"), class_name="radiobutton-box"), 
                                                    dbc.Input(placeholder="Alarm Description (Optional)", id="alarm_description_input", disabled=True),
                                                ], 
                                                size="md"
                                            ),
                                            width=12,
                                            className="col-sm-12 col-md-6"
                                        ),

                                        dbc.Col(
                                            dbc.InputGroup(
                                                [
                                                    dbc.InputGroupText("Type"), dbc.Select(options=[], id="alarm_type_input"),
                                                ],
                                                size="md"
                                            ),
                                            width=12,
                                            className="col-sm-12 col-md-3"
                                        ),

                                        dbc.Col(
                                            dbc.InputGroup(
                                                [
                                                    dbc.Input(placeholder="Trigger Value", id="alarm_trigger_value_input"), 
                                                    dbc.InputGroupText('', id="alarm_trigger_unit")
                                                ], 
                                                size="md"
                                            ),
                                            width=12,
                                            className="col-sm-12 col-md-3"
                                        ),

                                        dbc.Col(
                                            dbc.Button(
                                                "Create", 
                                                color="primary", 
                                                outline=True, 
                                                disabled=True, 
                                                id="create_alarm_button",
                                                className="w-100"
                                            ),
                                            width="auto",
                                            className="d-flex justify-content-center align-items-center"
                                        ),
                                    ],
                                    className="form g-3" 
                                ),
                            ],
                            title="Create Alarm",
                            className="my-3"
                        )
                    ],
                    start_collapsed=True,
                )
            ]
        )

    @classmethod
    def alarms_table(cls)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """       
        return dbc.Container(
            dbc.Row(
                dbc.Col(
                    dash.dash_table.DataTable(
                        data=[],
                        columns=[
                            {'name': 'id', 'id': 'id', 'editable': False}, 
                            {'name': 'name', 'id': 'name'}, 
                            {'name': 'tag', 'id': 'tag', 'presentation': 'dropdown'},
                            {'name': 'state', 'id': 'state', 'editable': False},  
                            {'name': 'description', 'id': 'description'}, 
                            {'name': 'alarm_type', 'id': 'alarm_type', 'presentation': 'dropdown'}, 
                            {'name': 'trigger_value', 'id': 'trigger_value', 'type': "numeric"},
                            {'name': 'operations', 'id': 'operations', 'presentation': 'dropdown'}
                        ],
                        id="alarms_datatable",
                        filter_action="native",
                        sort_action="native",
                        sort_mode="multi",
                        row_deletable=False,
                        selected_columns=[],
                        page_action="native",
                        page_current= 0,
                        page_size= 10,
                        persistence=True,
                        editable=True,
                        persisted_props=['data'],
                        export_format='xlsx',
                        export_headers='display',
                        style_table={'overflowX': 'auto'},
                    ),
                    width=12,
                )
            ),
            fluid=True,
            className="mx-0 px-0"
        )