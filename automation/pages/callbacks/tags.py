import dash
from automation.utils import find_differences_between_lists, find_keys_values_by_unit
from automation.variables import VARIABLES

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
    def create_tag(
        name:str, 
        variable:str, 
        datatype:str, 
        unit:str, 
        display_name:str, 
        description:str, 
        opcua_address:str, 
        node_namespace:str
        )->str:
        r"""
        Documentation here
        """
        if dash.ctx.triggered_id.lower()=="variable_input":
            
            dash.set_props("unit_input", {'options': [
                {"label": value, "value": value} for _, value in VARIABLES[variable].items()
            ]})
            
            unit = list(VARIABLES[variable].values())[0]
            dash.set_props("unit_input", {'value': unit})
            dash.set_props("unit_input", {'disabled': False})

        if name and datatype and unit and variable:

            dash.set_props("create_tag_button", {'disabled': False})
            dash.set_props("create_tag_button", {'disabled': False})

        else:
            
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
        dash.Output("node_namespace_input", "value"),
        dash.Input("opcua_address_input", "value")
    )
    def enable_node_namespace(opcua_server:str):
        r"""
        Documentation here
        """
        if opcua_server:

            dash.set_props("node_namespace_input", {'disabled': False})

        else:

            dash.set_props("node_namespace_input", {'disabled': True})

        return ""
    
    @app.callback(
        dash.Output('scan_time_input', 'value'),
        dash.Output('dead_band_input', 'value'),
        dash.Input("node_namespace_input", "value")
    )
    def enable_scan_time_and_dead_band(node_namespace:str):
        r"""
        Documentation here
        """
        if node_namespace:

            dash.set_props("scan_time_input", {'disabled': False})
            dash.set_props("dead_band_input", {'disabled': False})

        else:

            dash.set_props("scan_time_input", {'disabled': True})
            dash.set_props("dead_band_input", {'disabled': True})

        return "", ""
    
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
        dash.Output("dead_band_unit", "children"),
        dash.Input("unit_input", "value")
    )
    def update_unit(unit:str):
        r"""
        Documentation here
        """
        return unit
    
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
        dash.State("scan_time_input", "value"),
        dash.State("dead_band_input", "value"),
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
        scan_time,
        dead_band
        ):
        r"""
        Documentation here
        """
        if "create_tag_button" == dash.ctx.triggered_id:

            message = app.automation.cvt.set_tag(
                name=tag_name,
                unit=unit,
                data_type=datatype,
                description=description,
                display_name=display_name,
                opcua_address=opcua_address,
                node_namespace=node_namespace,
                scan_time=scan_time,
                dead_band=dead_band
            )
            
            if message:
                
                dash.set_props("modal-body", {"children": message})
                dash.set_props("modal-centered", {'is_open': True})
        
            return app.tags_table_data()
        
    @app.callback(
        dash.Input('tags_datatable', 'data_timestamp'),
        dash.State('tags_datatable', 'data_previous'),
        dash.State('tags_datatable', 'data'),
        )
    def delete_update_tags(timestamp, previous, current):

        if timestamp:
            
            if len(previous) > len(current): # DELETE TAG

                removed_rows = [row for row in previous if row not in current]
                
                for row in removed_rows:
                    
                    _id = row['id']
                    message = f"Do you want to delete Tag ID: {_id}?"
                    # OPEN MODAL TO CONFIRM CHANGES
                    dash.set_props("modal-update-delete-tag-body", {"children": message})
                    dash.set_props("modal-update_delete-centered", {'is_open': True})

            elif previous and current: # UPDATE TAG DEFINITION
                
                to_updates = find_differences_between_lists(previous, current)
                tag_to_update = to_updates[0]
                tag_id = tag_to_update.pop("id")
                message = f"Do you want to update tag {tag_id} To {tag_to_update}?"

                # OPEN MODAL TO CONFIRM CHANGES
                dash.set_props("modal-update-delete-tag-body", {"children": message})
                dash.set_props("modal-update_delete-centered", {'is_open': True})

    @app.callback(
        dash.Output("modal-centered", "is_open"),
        dash.Input("close-centered", "n_clicks"),
        [dash.State("modal-centered", "is_open")],
    )
    def toggle_modal(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        [
            dash.Output("modal-update_delete-centered", "is_open"), 
            dash.Output('tags_datatable', 'data'), 
            dash.Output('tags_datatable', 'data_timestamp'),
            dash.Output("update-delete-tag-yes", "n_clicks"),
            dash.Output("update-delete-tag-no", "n_clicks")
        ],
        [dash.Input("update-delete-tag-yes", "n_clicks"), dash.Input("update-delete-tag-no", "n_clicks")],
        [
            dash.State('tags_datatable', 'data_timestamp'),
            dash.State("modal-update_delete-centered", "is_open"),
            dash.State('tags_datatable', 'data_previous'),
            dash.State('tags_datatable', 'data')
        ]
    )
    def toggle_modal_update_delete_tag(yes_n, no_n, timestamp, is_open, previous, current):
        r"""
        Documentation here
        """
        
        if yes_n:
            
            if timestamp:
                
                if len(previous) > len(current): # DELETE TAG

                    removed_rows = [row for row in previous if row not in current]
                    
                    for row in removed_rows:
                        _id = row['id']
                        message = app.automation.cvt.delete_tag(id=_id)
                        
                        if message:
                            dash.set_props("modal-body", {"children": message})
                            dash.set_props("modal-centered", {'is_open': True})
                        
                elif previous and current: # UPDATE TAG DEFINITION
                    to_updates = find_differences_between_lists(previous, current)
                    tag_to_update = to_updates[0]
                    tag_id = tag_to_update.pop("id")
                    message = app.automation.cvt.update_tag(id=tag_id, **tag_to_update)
                    
                    if message:
                        dash.set_props("modal-body", {"children": message})
                        dash.set_props("modal-centered", {'is_open': True})

                return not is_open, app.tags_table_data(), None, 0, 0
        
        elif no_n:
            
            return not is_open, app.tags_table_data(), None, 0, 0

        else:

            return is_open, app.tags_table_data(), None, 0, 0
        
    @app.callback(
        [
            dash.Output('alert', 'is_open'),
            dash.Output('alert', 'children'),
            dash.Output('output', 'children')
        ],
        [
            dash.Input('scan_time_input', 'value')
        ],
        [
            dash.State('scan_time_input', 'min'), 
            dash.State('scan_time_input', 'max')
        ]
    )
    def update_scan_time(value, min_value, max_value):
        r"""
        Documentation here
        """
        if value is None:
            
            return False, '', min_value
        
        if value < min_value:

            return True, f'Value {value} is out of range ({min_value}-{max_value})', min_value
        
        if value > max_value:
            
            return True, f'Value {value} is out of range ({min_value}-{max_value})', max_value
        
        return False, '', f'Current value: {value} ms'
            