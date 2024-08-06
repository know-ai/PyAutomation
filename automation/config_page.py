import dash
import dash_bootstrap_components as dbc
import pandas as pd


class ConfigView(dash.Dash):

    def __init__(self, **kwargs):
    
        super().__init__(__name__, **kwargs)

        navbar = dbc.NavbarSimple(
            children=[
                dbc.NavItem(dbc.NavLink("Monitor", href="/")),
                dbc.NavItem(dbc.NavLink("Database", href="/database")),
                dbc.DropdownMenu(
                    children=[
                        dbc.DropdownMenuItem("Tags", header=True),
                        dbc.DropdownMenuItem("Definition", href="/tags", id="tags_definition_link"),
                        dbc.DropdownMenuItem("Trends", href="/trends"),
                    ],
                    nav=True,
                    in_navbar=True,
                    label="Tags",
                ),
                dbc.DropdownMenu(
                    children=[
                        dbc.DropdownMenuItem("Alarms", header=True),
                        dbc.DropdownMenuItem("Definition", href="/alarms"),
                        dbc.DropdownMenuItem("History", href="/alarms-history"),
                    ],
                    nav=True,
                    in_navbar=True,
                    label="Alarms",
                )
            ],
            brand="PyAutomation Configuration",
            color="primary",
            dark=True,
        )
        self.layout = dash.html.Div([
            navbar,
            dash.page_container
        ])

        ## DEFINE YOUR CALLBACKS FROM HERE
        @self.callback(
            dash.Input("tag_name_input", "value"), 
            dash.Input("variable_input", "value"), 
            dash.Input("datatype_input", "value"), 
            dash.Input("unit_input", "value"), 
            dash.Input("display_name_input", "value"), 
            dash.Input("description_input", "value"),
            dash.Input("opcua_address_input", "value"),
            dash.Input("node_namespace_input", "value")
            )
        def create_tag_callback(name, variable, datatype, unit, display_name, description, opcua_address, node_namespace):

            if variable:

                dash.set_props("unit_input", {'disabled': False})
                if name and datatype and unit:

                    dash.set_props("create_tag_button", {'disabled': False})
                    dash.set_props("create_tag_button", {'disabled': False})

                else:
                    
                    dash.set_props("create_tag_button", {'disabled': True})
            
            else:

                dash.set_props("unit_input", {'disabled': True})
                dash.set_props("create_tag_button", {'disabled': True})

        @self.callback(
            dash.Output("description_input", "value"),
            dash.Input("description_radio_button", "value")
        )
        def enable_description(enable:bool):

            dash.set_props("description_input", {'disabled': not enable})
            return ""
        
        @self.callback(
            dash.Output("opcua_address_input", "value"),
            dash.Input("opcua_radio_button", "value")
        )
        def enable_opcua(enable:bool):

            dash.set_props("opcua_address_input", {'disabled': not enable})
            return ""
        
        @self.callback(
            dash.Output("display_name_input", "value"),
            dash.Input("display_name_radio_button", "value")
        )
        def enable_display(enable:bool):
            dash.set_props("display_name_input", {'disabled': not enable})
            return ""
        
        @self.callback(
            dash.Output('tags_datatable', 'data', allow_duplicate=True),
            dash.Input('tags_page', 'pathname'),
            prevent_initial_call=True
            )
        def display_page(pathname):
            
            if pathname=="/tags":
                
                return self.tags_table_data()
        
        @self.callback(
            dash.Output('tags_datatable', 'data', allow_duplicate=True),
            dash.Input('create_tag_button', 'n_clicks'),
            dash.State("tag_name_input", "value"), 
            dash.State("datatype_input", "value"), 
            dash.State("unit_input", "value"), 
            dash.State("display_name_input", "value"), 
            dash.State("description_input", "value"),
            dash.State("opcua_address_input", "value"),
            dash.State("node_namespace_input", "value"),
            prevent_initial_call=True
        )
        def displayClick(
            btn1, 
            tag_name,
            datatype,
            unit,
            display_name,
            description,
            opcua_address,
            node_namespace,
            allow_duplicate=True
            ):
            if "create_tag_button" == dash.ctx.triggered_id:

                self.automation.cvt.set_tag(
                    name=tag_name,
                    unit=unit,
                    data_type=datatype,
                    description=description,
                    display_name=display_name,
                    opcua_address=opcua_address,
                    node_namespace=node_namespace
                )
                return self.tags_table_data()
            
        @self.callback(
            dash.Input('tags_datatable', 'data_previous'),
            dash.State('tags_datatable', 'data')
        )
        def show_removed_rows(previous, current):
            if previous is None:
                dash.exceptions.PreventUpdate()
            else:
                removed_rows = [row for row in previous if row not in current]
                for row in removed_rows:
                    _id = row['id']
                    self.automation.cvt.delete_tag(id=_id)
            
        # @self.callback(
        #     dash.Input('tags_datatable', 'selected_row')
        # )
        # def update_graphs(active_cell):
        #     print(f"Active Cell: {active_cell}")

    def set_automation_app(self, automation_app):

        self.automation = automation_app
        
    def tags_table_data(self):

        tags = pd.DataFrame(self.automation.cvt.get_tags())
        columns_allowed = ["id", "name", "unit", "data_type", "description", "display_name", "opcua_address", "node_namespace"]
        records=tags.to_dict("records")
        data = list()
        # print(f"Tags: {records}")
        for record in records:
            
            data.append({ key : value for (key, value) in record.items() if key in columns_allowed })

        return data