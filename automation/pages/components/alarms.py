import dash
import dash_bootstrap_components as dbc
from automation import PyAutomation
from automation.variables import VARIABLES
from automation.utils import generate_dropdown_conditional

app = PyAutomation()

if hasattr(app, 'dash_app'):

    data = app.dash_app.alarms_table_data()

else:

    data = list()

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
                            dbc.Row([
                                dbc.Col([
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
                                        size="md"
                                    )
                                ],
                                width=2),
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="Alarm Name", id="alarm_name_input")], size="md"),
                                ],
                                width=2),
                                dbc.Col([
                                    dbc.InputGroup([dbc.InputGroupText(dbc.RadioButton(id="alarm_description_radio_button"), class_name="radiobutton-box"), dbc.Input(placeholder="Alarm Description (Optional)", id="alarm_description_input", disabled=True)], size="md")
                                ],
                                width=4),
                                dbc.Col([
                                    dbc.InputGroup([dbc.InputGroupText("Type"), dbc.Select(options=[
                                        {'label': 'HIGH-HIGH', 'value': 'HIGH-HIGH'},
                                        {'label': 'HIGH', 'value': 'HIGH'},
                                        {'label': 'LOW', 'value': 'LOW'},
                                        {'label': 'LOW-LOW', 'value': 'LOW-LOW'},
                                        {'label': 'BOOL', 'value': 'BOOL'}
                                    ], id="alarm_type_input")],
                                        size="md"
                                    )
                                ],
                                width=2),
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="Trigger Value", type="number", step=0.1, id="alarm_trigger_value_input"), dbc.InputGroupText('', id="dead_band_unit")], size="md")
                                ],
                                width=2)
                            ]),
                            dbc.Button("Create", color="primary", outline=True, disabled=True, id="create_alarm_button"),
                        ],
                        title="Create Alarm",
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

        return dash.dash_table.DataTable(
            data=data,
            columns=[
                {'name': 'id', 'id': 'id', 'editable': False}, 
                {'name': 'name', 'id': 'name'}, 
                {'name': 'tag', 'id': 'tag', 'presentation': 'dropdown'},
                {'name': 'state', 'id': 'state', 'editable': False},  
                {'name': 'description', 'id': 'description'}, 
                {'name': 'type', 'id': 'type', 'presentation': 'dropdown'}, 
                {'name': 'trigger_value', 'id': 'trigger_value'}
            ],
            id="alarms_datatable",
            filter_action="native",
            sort_action="native",
            sort_mode="multi",
            row_deletable=True,
            selected_columns=[],
            # dropdown = {
            #     'type': {
            #         'options': 
            #     }
            # },
            page_action="native",
            page_current= 0,
            page_size= 10,
            persistence=True,
            editable=True,
            persisted_props=['data'],
            export_format='xlsx',
            export_headers='display',
        )