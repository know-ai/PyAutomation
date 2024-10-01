import dash
from ...utils import find_differences_between_lists, generate_dropdown_conditional
from ...variables import VARIABLES

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Input("tag_name_input", "value"),
        dash.Input("variable_input", "value"),
        dash.Input("datatype_input", "value"),
        dash.Input("unit_input", "value"),  
        dash.Input("display_unit_input", "value"), 
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
        display_unit:str,
        display_name:str, 
        description:str, 
        opcua_address:str, 
        node_namespace:str
        )->str:
        r"""
        Documentation here
        """
        if dash.ctx.triggered_id.lower()=="variable_input":

            options = [{"label": value, "value": value} for _, value in VARIABLES[variable].items()]
            unit = list(VARIABLES[variable].values())[0]
            
            dash.set_props("unit_input", {'options': options})
            dash.set_props("display_unit_input", {'options': options})
            dash.set_props("unit_input", {'value': unit})
            dash.set_props("unit_input", {'disabled': False})
            dash.set_props("display_unit_input", {'value': unit})
            dash.set_props("display_unit_input", {'disabled': False})

        if name and datatype and unit and variable and display_unit:

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
        dash.Output('opcua_address_input', 'options'),
        dash.Output('tags_datatable', 'dropdown'),
        dash.Output('tags_datatable', 'dropdown_conditional'),
        dash.Input('tags_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        opcua_client_options = [{"label": "", "value": ""}]

        for opcua_client, info in app.automation.get_opcua_clients().items():
            
            opcua_client_options.append({
                "label": opcua_client, "value": info['server_url']
            })
        
        dropdown = {
            'data_type': {
                'options': [
                    {'label': 'Float', 'value': 'float'},
                    {'label': 'Integer', 'value': 'integer'},
                    {'label': 'Boolean', 'value': 'boolean'},
                    {'label': 'String', 'value': 'string'}
                ]
            },
            'opcua_address': {
                'options': opcua_client_options
            }
        }

        dropdown_conditional = generate_dropdown_conditional()

        if pathname=="/tags":
            
            return app.tags_table_data(), opcua_client_options, dropdown, dropdown_conditional
        
        return dash.no_update, opcua_client_options, dropdown, dropdown_conditional
        
    @app.callback(
        dash.Output('node_namespace_input', 'options'),
        dash.Input('opcua_address_input', 'value'),
        prevent_initial_call=True
        )
    def select_opcua_server(server_url):
        r"""
        Documentation here
        """
        opcua_clients = app.automation.get_opcua_clients()
        for client_name, info in opcua_clients.items():

            if server_url==info["server_url"]:

                break

        nodes = [{"label": "None", "value": "None"}]
        tree = app.automation.get_opcua_tree(client_name)
        for node in tree[0]["Objects"][0]["children"]:

            nodes.append(
                {
                    "label": node["title"],
                    "value": node["key"]
                }
            )
        return nodes
        
    @app.callback(
        dash.Output('tags_datatable', 'data', allow_duplicate=True),
        dash.Output('tags_datatable', 'dropdown_conditional', allow_duplicate=True),
        dash.Input('create_tag_button', 'n_clicks'),
        dash.State("tag_name_input", "value"), 
        dash.State("datatype_input", "value"), 
        dash.State("unit_input", "value"),
        dash.State("display_unit_input", "value"), 
        dash.State("variable_input", "value"),
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
        display_unit,
        variable,
        display_name,
        description,
        opcua_address,
        node_namespace,
        scan_time:int|None=None,
        dead_band:float|None=None
        ):
        r"""
        Documentation here
        """
        if "create_tag_button" == dash.ctx.triggered_id:

            if not scan_time:

                scan_time = None
            
            if not dead_band:

                dead_band = None
            
            tag, message = app.automation.create_tag(
                name=tag_name,
                unit=unit,
                display_unit=display_unit,
                data_type=datatype,
                variable=variable,
                description=description,
                display_name=display_name,
                opcua_address=opcua_address,
                node_namespace=node_namespace,
                scan_time=scan_time,
                dead_band=dead_band
            )
            
            if not tag:
                
                dash.set_props("modal-body", {"children": message})
                dash.set_props("modal-centered", {'is_open': True})
            
            return app.tags_table_data(), generate_dropdown_conditional()
        
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
                        message = app.automation.delete_tag(id=_id)
                        
                        if message:
                            dash.set_props("modal-body", {"children": message})
                            dash.set_props("modal-centered", {'is_open': True})
                        
                elif previous and current: # UPDATE TAG DEFINITION
                    to_updates = find_differences_between_lists(previous, current)
                    tag_to_update = to_updates[0]
                    tag_id = tag_to_update.pop("id")
                    tag, message = app.automation.update_tag(id=tag_id, **tag_to_update)
                    
                    if not tag:
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
            