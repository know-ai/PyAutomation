import dash

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Output('machines_datatable', 'data'),
        dash.Input('machines_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/machines":

            data = app.automation.machine_manager.serialize_machines()

            return data
        
        return dash.no_update