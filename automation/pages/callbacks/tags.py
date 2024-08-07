import dash

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Input("tag_name_input", "value"), 
        dash.Input("variable_input", "value"), 
        dash.Input("datatype_input", "value"), 
        dash.Input("unit_input", "value"), 
        dash.Input("display_name_input", "value"), 
        dash.Input("description_input", "value"),
        dash.Input("opcua_address_input", "value"),
        dash.Input("node_namespace_input", "value")
        )
    def create_tag(name, variable, datatype, unit, display_name, description, opcua_address, node_namespace):
        r"""
        Documentation here
        """

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

    @app.callback(
        dash.Output("description_input", "value"),
        dash.Input("description_radio_button", "value")
    )
    def enable_description(enable:bool):
        r"""
        Documentation here
        """
        dash.set_props("description_input", {'disabled': not enable})
        return ""
    
    @app.callback(
        dash.Output("opcua_address_input", "value"),
        dash.Input("opcua_radio_button", "value")
    )
    def enable_opcua(enable:bool):
        r"""
        Documentation here
        """
        dash.set_props("opcua_address_input", {'disabled': not enable})
        return ""
    
    @app.callback(
        dash.Output("display_name_input", "value"),
        dash.Input("display_name_radio_button", "value")
    )
    def enable_display(enable:bool):
        r"""
        Documentation here
        """
        dash.set_props("display_name_input", {'disabled': not enable})
        return ""
    
    @app.callback(
        dash.Output('tags_datatable', 'data', allow_duplicate=True),
        dash.Input('tags_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/tags":
            
            return app.tags_table_data()
        
    @app.callback(
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
        r"""
        Documentation here
        """
        if "create_tag_button" == dash.ctx.triggered_id:

            try:

                app.automation.cvt.set_tag(
                    name=tag_name,
                    unit=unit,
                    data_type=datatype,
                    description=description,
                    display_name=display_name,
                    opcua_address=opcua_address,
                    node_namespace=node_namespace
                )
            
            except Exception as err:

                print(f"Error Message: {err.message}")
                
            return app.tags_table_data()
        
    @app.callback(
        dash.Input('tags_datatable', 'data_previous'),
        dash.State('tags_datatable', 'data')
    )
    def show_removed_rows(previous, current):
        r"""
        Documentation here
        """
        if previous is None:
            dash.exceptions.PreventUpdate()
        else:
            removed_rows = [row for row in previous if row not in current]
            for row in removed_rows:
                _id = row['id']
                app.automation.cvt.delete_tag(id=_id)
        
    # @self.callback(
    #     dash.Input('tags_datatable', 'selected_row')
    # )
    # def update_graphs(active_cell):
    #     print(f"Active Cell: {active_cell}")