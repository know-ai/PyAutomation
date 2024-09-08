import dash

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Input("tag_alarm_input", "value"),
        dash.Input("alarm_name_input", "value"), 
        dash.Input("alarm_type_input", "value"),
        dash.Input("alarm_trigger_value_input", "value")
        )
    def create_tag(
        tag:str,
        name:str,  
        type:str, 
        trigger_value:str
        )->str:
        r"""
        Documentation here
        """

        if name and tag and type and trigger_value:

            dash.set_props("create_alarm_button", {'disabled': False})

        else:
            
            dash.set_props("create_alarm_button", {'disabled': True})

    @app.callback(
        dash.Output("modal-alarm-create", "is_open"),
        dash.Input("close-model-alarm-create", "n_clicks"),
        [dash.State("modal-alarm-create", "is_open")],
    )
    def toggle_modal(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open

    @app.callback(
        dash.Output("alarm_description_input", "value"),
        dash.Input("alarm_description_radio_button", "value")
    )
    def enable_description(enable:bool):
        r"""
        Documentation here
        """
        dash.set_props("alarm_description_input", {'disabled': not enable})
        return ""

    @app.callback(
        dash.Output('alarms_datatable', 'data', allow_duplicate=True),
        dash.Output('tag_alarm_input', 'options'),
        dash.Output('alarms_datatable', 'dropdown'),
        dash.Input('alarms_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/alarms":

            data = [{
                "id": alarm["id"],
                "tag": alarm["tag"], 
                "name": alarm["name"],
                "description": alarm["description"],
                "state": alarm["state"],
                "type": alarm["type"],
                "trigger_value": alarm["trigger_value"]
                } for alarm in app.automation.alarm_manager.serialize()]

            dropdown_options_type = [
                {'label': 'HIGH-HIGH', 'value': 'HIGH-HIGH'},
                {'label': 'HIGH', 'value': 'HIGH'},
                {'label': 'LOW', 'value': 'LOW'},
                {'label': 'LOW-LOW', 'value': 'LOW-LOW'},
                {'label': 'BOOL', 'value': 'BOOL'}
            ]
            dropdown_options_tag = [{"label": tag["name"], "value": tag["name"]} for tag in app.automation.cvt.get_tags()]
            dropdown = {
                "type": {
                    "options": dropdown_options_type,
                },
                "tag": {
                    "options": dropdown_options_tag
                }
            }

            return data, dropdown_options_tag, dropdown
        
        return dash.no_update, dash.no_update, dash.no_update
    
    @app.callback(
        dash.Output('alarms_datatable', 'data'),
        dash.Input('create_alarm_button', 'n_clicks'),
        dash.State("tag_alarm_input", "value"),
        dash.State("alarm_name_input", "value"), 
        dash.State("alarm_description_input", "value"),
        dash.State("alarm_type_input", "value"),
        dash.State("alarm_trigger_value_input", "value"),
        prevent_initial_call=True
    )
    def CreateAlarmButton(
        btn1, 
        tag_name,
        alarm_name,
        alarm_description,
        alarm_type,
        trigger_value
        ):
        r"""
        Documentation here
        """
        if "create_alarm_button" == dash.ctx.triggered_id:
            
            message = app.automation.alarm_manager.append_alarm(
                name=alarm_name,
                tag=tag_name,
                type=alarm_type,
                trigger_value=trigger_value,
                description=alarm_description
            )
            
            if message:
                
                dash.set_props("modal-body-alarm-create", {"children": message})
                dash.set_props("modal-alarm-create", {'is_open': True})

            return [{
                "id": alarm["id"],
                "tag": alarm["tag"], 
                "name": alarm["name"],
                "description": alarm["description"],
                "state": alarm["state"],
                "type": alarm["type"],
                "trigger_value": alarm["trigger_value"]
                } for alarm in app.automation.alarm_manager.serialize()]