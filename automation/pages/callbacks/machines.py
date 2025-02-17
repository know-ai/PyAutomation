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

            data = app.machines_table_data()
            return data
        
        return dash.no_update
    
    @app.callback(
        dash.Output('machines_datatable', 'data', allow_duplicate=True),
        dash.Input('timestamp-interval', 'n_intervals'),
        prevent_initial_call=False
    )
    def update_table( n_intervals):
        
        data = app.machines_table_data()
        return data