import dash
import dash_bootstrap_components as dbc
from automation.models import StringType


class MachinesComponents:

    @classmethod
    def machine_actions(cls):
        r"""
        Documentation here
        """

        return dash.html.Div([
            dash.dcc.Location(id='machine_actions_page', refresh=False),
            dbc.Row([
                dbc.Col([
                    dbc.InputGroup(
                        [
                            dbc.InputGroupText(id="machine_state_input"),
                            dbc.Select(
                                options=[],
                                id="machine_actions_input"
                            ),
                        ],
                        size="md"
                    )
                ],
                width=12,
                className="col-sm-12 col-md-12")
            ])
        ])

    @classmethod
    def subscription_tag_form(cls, app, machine_name:str):
        r"""
        Documentation here
        """
        machine = app.get_machine(name=StringType(machine_name))
        internal_variables = machine.get_read_only_process_type_variables()
        subscribed_tags_machine = [{"label": "", "value": ""}]
        not_subscribed = [{"label": "", "value": ""}]
        available_tags = [{"label": "", "value": ""}]
        tags = app.cvt._cvt.get_field_tags_names()
        for _tag_name, value in internal_variables.items():

            if value.tag:
                subscribed_tags_machine.append({
                    "label": f"{value.tag.name}->{_tag_name}", "value": value.tag.name
                    })
                tags.remove(value.tag.name)
                
            else:

                not_subscribed.append({
                    "label": _tag_name, "value": _tag_name
                })

        for tag in tags:

            available_tags.append({
                "label": tag, "value": tag
            })

        return dash.html.Div(
            [
                dash.dcc.Location(id='tags_machine_subscription_page', refresh=False),
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.InputGroupText("Subscribed"),
                                                        dbc.Select(
                                                            options=subscribed_tags_machine,
                                                            id="subscribed_tag_machine_input"
                                                        ),
                                                    ],
                                                    size="md"
                                                )
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-12"
                                        )
                                    ],
                                    className="form g-3"
                                ),
                                dbc.Row([
                                    dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.InputGroupText("Field"), dbc.Select(options=available_tags, id="field_tag_input" )
                                                    ],
                                                    size="md",
                                                    className="mb-6"
                                                )
                                            
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-6"
                                        ),
                                        
                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.InputGroupText("Tag"), 
                                                        dbc.Select(options=not_subscribed, id="internal_tag_input")
                                                    ],
                                                    size="md",
                                                    className="mb-6"
                                                )
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-6"
                                        ),
                                ]),
                                dbc.Row([
                                    dbc.Col(
                                        dbc.Button(
                                            "Subscribe",
                                            color="primary",
                                            outline=True,
                                            disabled=True,
                                            id="subscribe_tag_machine_button",
                                            className="w-100"
                                        ),
                                        width="auto",
                                        className="d-flex justify-content-center align-items-center"
                                    ),
                                    dbc.Col(
                                        dbc.Button(
                                            "Unsubscribe",
                                            color="danger",
                                            outline=True,
                                            disabled=True,
                                            id="unsubscribe_tag_machine_button",
                                            className="w-100"
                                        ),
                                        width="auto",
                                        className="d-flex justify-content-center align-items-center"
                                    ),
                                ])
                            ],
                            title="Tags - Machine Subscription",
                            className="my-3"
                        )
                    ],
                    start_collapsed=False,
                )
            ]
        )

    @classmethod
    def machines_table(cls)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        return dbc.Container(
            dbc.Row(
                dbc.Col(
                    dash.dash_table.DataTable(
                        data=[],
                        columns=[
                            {'name': 'name', 'id': 'name', 'editable': False}, 
                            {'name': 'sampling_time', 'id': 'sampling_time', 'editable': False}, 
                            {'name': 'description', 'id': 'description', 'editable': False}, 
                            {'name': 'state', 'id': 'state', 'editable': False}, 
                            {'name': 'criticity', 'id': 'criticity', 'editable': False}, 
                            {'name': 'priority', 'id': 'priority', 'editable': False},
                            {'name': 'classification', 'id': 'classification', 'editable': False},
                        ],
                        id="machines_datatable",
                        filter_action="native",
                        sort_action="native",
                        sort_mode="multi",
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
    
    @classmethod
    def machines_tabs(cls):

        return dash.html.Div(
            [
                dbc.Tabs(
                    [
                        dbc.Tab(label="No Advanced Machine", tab_id="tab-1"),
                    ],
                    id="machines_detailed_tabs",
                    active_tab="tab-1",
                ),
                dash.html.Div(id="machine_detailed_content"),
            ]
        )
    
    @classmethod
    def machine_tab_datatable_content(cls, app, machine_name:str)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        def flatten_dict(d, parent_key='', sep='.'): 
            items = [] 
            for k, v in d.items(): 
                
                new_key = f"{parent_key}{sep}{k}" if parent_key else k 
                if isinstance(v, dict): 
                    items.extend(flatten_dict(v, new_key, sep=sep).items()) 
                else: 
                    items.append((new_key, v)) 
                    
            return dict(items)

        machine = app.get_machine(name=StringType(machine_name))
        data = list()
        serialized_data = machine.serialize()
        flattened_data = flatten_dict(serialized_data)
        for key, value in flattened_data.items():

            if isinstance(value, (bool, int, str, float)):

                data.append({"name": key, "value": value})

        return dash.dash_table.DataTable(
                data=data,
                columns=[
                    {'name': 'name', 'id': 'name', 'editable': False}, 
                    {'name': 'value', 'id': 'value', 'editable': False}, 
                ],
                id="machines_detailed_datatable",
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                row_deletable=False,
                selected_columns=[],
                page_action="native",
                page_size=10,
                persistence=True,
                editable=False,
                persisted_props=['data'],
                export_format='xlsx',
                export_headers='display',
                style_table={'overflowX': 'auto'},
            )
    
    @classmethod
    def machine_tab_content(cls, app, machine_name:str):

        return dash.html.Div(
            [
                dbc.Row([
                    dbc.Col(
                        [
                            dbc.Container(
                            dbc.Row(
                                dbc.Col(
                                    cls.machine_tab_datatable_content(app=app, machine_name=machine_name),
                                    width=12,
                                )
                            ),
                            fluid=True,
                            className="mx-0 px-0"
                        )
                        ],
                        width=6,
                        className="col-sm-12 col-md-6"
                    ),  
                    dbc.Col(
                        [
                            dbc.Row([
                                cls.subscription_tag_form(app=app, machine_name=machine_name)
                            ]),
                            dbc.Row([
                                cls.machine_actions()
                            ])
                        ],
                        width=6,
                        className="col-sm-12 col-md-6"
                    )
                ])
            ]
        )