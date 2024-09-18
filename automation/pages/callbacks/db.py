import dash

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Input("db_type_input", "value"),
        dash.Input("db_name_input", "value"),
        dash.Input("db_host_input", "value"),
        dash.Input("db_port_input", "value"),
        dash.Input("db_user_input", "value")
        )
    def connection(
        db_type_value:str, 
        db_name_value:str, 
        db_host_value:str, 
        db_port_value:str, 
        db_user_value:str 
        )->str:
        r"""
        Documentation here
        """
        
        if db_type_value.lower()=="sqlite":

            dash.set_props("db_host_input", {'disabled': True})
            dash.set_props("db_port_input", {'disabled': True})
            dash.set_props("db_user_input", {'disabled': True})
            dash.set_props("db_password_input", {'disabled': True})

            if db_name_value:

                dash.set_props("connect_disconnect_db_button", {'disabled': False})

            else:
            
                dash.set_props("connect_disconnect_db_button", {'disabled': True})

        else:

            dash.set_props("db_host_input", {'disabled': False})
            dash.set_props("db_port_input", {'disabled': False})
            dash.set_props("db_user_input", {'disabled': False})
            dash.set_props("db_password_input", {'disabled': False})

            if db_name_value and db_host_value and db_port_value and db_user_value:

                dash.set_props("connect_disconnect_db_button", {'disabled': False})

            else:
            
                dash.set_props("connect_disconnect_db_button", {'disabled': True})

    @app.callback(
        dash.Input('connect_disconnect_db_button', 'n_clicks'),
        dash.State('connect_disconnect_db_button', 'children'),
        dash.State("db_type_input", "value"),
        dash.State("db_name_input", "value"),
        dash.State("db_host_input", "value"),
        dash.State("db_port_input", "value"),
        dash.State("db_user_input", "value"),
        dash.State("db_password_input", "value")
        )
    def connect_button(
        btn1,
        connect_action:str,
        db_type_value:str, 
        db_name_value:str, 
        db_host_value:str="127.0.0.1", 
        db_port_value:str="5432", 
        db_user_value:str="", 
        db_password_value:str=""
        )->str:
        r"""
        Documentation here
        """
        
        if connect_action.lower()=="connect":
            app.automation.set_db_config(
                dbtype=db_type_value,
                dbfile=db_name_value,
                user=db_user_value,
                password=db_password_value,
                host=db_host_value,
                port=db_port_value,
                name=db_name_value
            )
            app.automation.connect_to_db()
            if app.automation.is_db_connected():

                message = f"Connection to db was successfully?"

                # OPEN MODAL TO CONFIRM CHANGES
                dash.set_props("modal-body-db-connection", {"children": message})
                dash.set_props("modal-db-connection", {'is_open': True})
        else:
            
            db_config = app.automation.get_db_config()
            app.automation.disconnect_to_db()
            
            if db_config['dbtype']=="sqlite":
                
                dash.set_props("db_type_input", {'value': ""})
                dash.set_props("db_name_input", {'value': ""})
                dash.set_props("db_type_input", {'disabled': False})
                dash.set_props("db_name_input", {'disabled': False})
            
            else:

                dash.set_props("db_type_input", {'value': ""})
                dash.set_props("db_name_input", {'value': db_config['name']})
                dash.set_props("db_host_input", {'value': db_config['host']})
                dash.set_props("db_port_input", {'value': db_config['port']})
                dash.set_props("db_user_input", {'value': db_config['user']})
                dash.set_props("db_password_input", {'value': db_config['password']})


                dash.set_props("db_type_input", {'disabled': False})
                dash.set_props("db_name_input", {'disabled': False})
                dash.set_props("db_host_input", {'disabled': False})
                dash.set_props("db_port_input", {'disabled': False})
                dash.set_props("db_user_input", {'disabled': False})
                dash.set_props("db_password_input", {'disabled': False})


    @app.callback(
        dash.Output("modal-db-connection", "is_open"),
        dash.Input("close-model-db-connection", "n_clicks"),
        [dash.State("modal-db-connection", "is_open")],
    )
    def toggle_modal(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        # dash.Output("modal-db-connection", "is_open"),
        dash.Input('timestamp-interval', 'n_intervals')
    )
    def connection_notification(n_interval):
        r"""
        Documentation here
        """
        if app.automation.is_db_connected():

            dash.set_props("connect_disconnect_db_button", {'children': "Disconnect"})
            db_config = app.automation.get_db_config()
            
            if db_config['dbtype']=="sqlite":
                
                dash.set_props("db_type_input", {'value': "sqlite"})
                dash.set_props("db_name_input", {'value': db_config['dbfile']})
                dash.set_props("db_type_input", {'disabled': True})
                dash.set_props("db_name_input", {'disabled': True})
            
            else:

                dash.set_props("db_type_input", {'value': db_config['dbtype']})
                dash.set_props("db_name_input", {'value': db_config['name']})
                dash.set_props("db_host_input", {'value': db_config['host']})
                dash.set_props("db_port_input", {'value': db_config['port']})
                dash.set_props("db_user_input", {'value': db_config['user']})
                dash.set_props("db_password_input", {'value': db_config['password']})


                dash.set_props("db_type_input", {'disabled': True})
                dash.set_props("db_name_input", {'disabled': True})
                dash.set_props("db_host_input", {'disabled': True})
                dash.set_props("db_port_input", {'disabled': True})
                dash.set_props("db_user_input", {'disabled': True})
                dash.set_props("db_password_input", {'disabled': True})
        
        else:

            dash.set_props("connect_disconnect_db_button", {'children': "Connect"})
            dash.set_props("db_type_input", {'disabled': False})
            dash.set_props("db_name_input", {'disabled': False})
            dash.set_props("db_host_input", {'disabled': False})
            dash.set_props("db_port_input", {'disabled': False})
            dash.set_props("db_user_input", {'disabled': False})
            dash.set_props("db_password_input", {'disabled': False})