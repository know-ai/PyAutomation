import dash
from ...tags.cvt import CVTEngine
from ...utils import find_differences_between_lists, generate_dropdown_conditional


tag_engine = CVTEngine()

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
        trigger_value:int|float
        )->str:
        r"""
        Documentation here
        """
        if tag:
            _tag = tag_engine.get_tag_by_name(name=tag)
            dash.set_props("alarm_trigger_unit", {'children': _tag.get_display_unit()})

        
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
        dash.Output('alarm_type_input', 'options'),
        dash.Output('alarms_datatable', 'dropdown_conditional'),
        dash.Input('alarms_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/alarms":

            data = app.alarms_table_data()

            dropdown_options_type = [
                {'label': 'HIGH-HIGH', 'value': 'HIGH-HIGH'},
                {'label': 'HIGH', 'value': 'HIGH'},
                {'label': 'LOW', 'value': 'LOW'},
                {'label': 'LOW-LOW', 'value': 'LOW-LOW'},
                {'label': 'BOOL', 'value': 'BOOL'}
            ]
            dropdown_options_tag = [{"label": tag["name"], "value": tag["name"]} for tag in app.automation.cvt.get_tags()]
            dropdown = {
                "alarm_type": {
                    "options": dropdown_options_type,
                    "clearable": False
                },
                "tag": {
                    "options": dropdown_options_tag,
                    "clearable": False
                }
            }

            return data, dropdown_options_tag, dropdown, dropdown_options_type, generate_dropdown_conditional()
        
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    @app.callback(
        dash.Output('alarms_datatable', 'data', allow_duplicate=True),
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
            
            alarm, message = app.automation.create_alarm(
                name=alarm_name,
                tag=tag_name,
                alarm_type=alarm_type,
                trigger_value=float(trigger_value),
                description=alarm_description
            )
            
            if not alarm:
                
                dash.set_props("modal-body-alarm-create", {"children": message})
                dash.set_props("modal-alarm-create", {'is_open': True})
            
            return app.alarms_table_data()
        
    @app.callback(
        dash.Input('alarms_datatable', 'data_timestamp'),
        dash.State('alarms_datatable', 'data_previous'),
        dash.State('alarms_datatable', 'data'),
        )
    def delete_update_alarms(timestamp, previous, current):

        if timestamp:

            if previous and current: # UPDATE TAG DEFINITION
                
                to_updates = find_differences_between_lists(previous, current)
                alarm_to_update = to_updates[0]
                alarm_id = alarm_to_update.pop("id")
                message = f"Do you want to update alarm {alarm_id} To {alarm_to_update}?"

                # OPEN MODAL TO CONFIRM CHANGES
                dash.set_props("modal-update-delete-alarm-body", {"children": message})
                dash.set_props("modal-update-delete-alarm", {'is_open': True})

    @app.callback(
        [
            dash.Output("modal-update-delete-alarm", "is_open"), 
            dash.Output('alarms_datatable', 'data'), 
            dash.Output('alarms_datatable', 'data_timestamp'),
            dash.Output("update-delete-alarm-yes", "n_clicks"),
            dash.Output("update-delete-alarm-no", "n_clicks")
        ],
        [dash.Input("update-delete-alarm-yes", "n_clicks"), dash.Input("update-delete-alarm-no", "n_clicks")],
        [
            dash.State('alarms_datatable', 'data_timestamp'),
            dash.State("modal-update-delete-alarm", "is_open"),
            dash.State('alarms_datatable', 'data_previous'),
            dash.State('alarms_datatable', 'data')
        ]
    )
    def toggle_modal_update_delete_alarm(yes_n, no_n, timestamp, is_open, previous, current):
        r"""
        Documentation here
        """
        
        if yes_n:
            
            if timestamp:
                
                if len(previous) > len(current): # DELETE ALARM

                    removed_rows = [row for row in previous if row not in current]
                    
                    for row in removed_rows:
                        _id = row['id']
                        message = app.automation.delete_alarm(id=_id)
                        
                        if message:
                            dash.set_props("modal-body-alarm-create", {"children": message})
                            dash.set_props("modal-alarm-create", {'is_open': True})
                        
                elif previous and current: # UPDATE TAG DEFINITION
                    to_updates = find_differences_between_lists(previous, current)
                    alarm_to_update = to_updates[0]
                    alarm_id = alarm_to_update.pop("id")
                    message = app.automation.update_alarm(id=alarm_id, **alarm_to_update)
                    
                    if message:
                        dash.set_props("modal-body-alarm-create", {"children": message})
                        dash.set_props("modal-alarm-create", {'is_open': True})
                
                return not is_open, app.alarms_table_data(), None, 0, 0
        
        elif no_n:
            
            return not is_open, app.alarms_table_data(), None, 0, 0

        else:

            return is_open, app.alarms_table_data(), None, 0, 0
        