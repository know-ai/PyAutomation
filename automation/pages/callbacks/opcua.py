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