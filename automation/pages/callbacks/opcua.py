import dash


def init_callback(app:dash.Dash):



    @app.callback(
        # dash.Output('selected-file-output', 'children'),
        [dash.Input({'type': 'file-checklist', 'index': dash.dependencies.ALL}, 'value')]
    )
    def display_selected_file(selected_files):

        files = list()

        for file in selected_files:

            if file:

                files.append(file[0])
        print(f"Files: {files}")

    @app.callback(
        dash.Output("add_server_modal", "is_open"),
        dash.Input("add_server_button", "n_clicks"),
        [dash.State("add_server_modal", "is_open")],
    )
    def add_server_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("add_server_modal", "is_open", allow_duplicate=True),
        dash.Input("add_server_ok_button_modal", "n_clicks"),
        dash.State("opcua_client_name_input", "value"),
        dash.State("opcua_client_host_input", "value"),
        dash.State("opcua_client_port_input", "value")
    )
    def ok_add_server_button(n, client_name:str, host:str="127.0.0.1", port:int=4840):
        r"""
        Documentation here
        """
        resp = app.automation.add_opcua_client(client_name=client_name, host=host, port=port)
        clients = app.automation.get_opcua_clients()

        print(f"clients: {clients}")

        return False
    
    @app.callback(
        dash.Output("add_server_modal", "is_open", allow_duplicate=True),
        dash.Input("add_server_cancel_button_modal", "n_clicks"),
    )
    def cancel_add_server_button(n):
        r"""
        Documentation here
        """
        return False